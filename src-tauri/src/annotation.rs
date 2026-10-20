//! TASK-04 §5.7: fixed annotation operations, never a general HTTP bridge.
pub use crate::datasets_dev::ForwardError;
use crate::handshake::Handshake;
use reqwest::{Method, Url, blocking::Client};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::{io::Read, time::Duration};

// Same transport limit as datasets_dev; TASK-04 §5.7 preserves the #02 boundary.
pub const MAX_RESPONSE_BYTES: u64 = 8 * 1024 * 1024;

#[derive(Deserialize, Serialize)]
#[serde(untagged, deny_unknown_fields)]
pub enum Seed {
    Point { point: [i64; 2] },
    Box { r#box: [i64; 4] },
    Doodle { doodle: Vec<[i64; 2]> },
}

#[derive(Deserialize, Serialize)]
#[serde(untagged, deny_unknown_fields)]
pub enum Geometry {
    Superpixels { superpixels: Vec<u32> },
    Polygon { polygon: Vec<[f64; 2]> },
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Action {
    Confirm,
    Erase,
    Uncertain,
}

// Missing optional parameters are omitted from HTTP bodies: the Python request
// models remain the authority for defaults (no second set of defaults in Rust).
// Explicit null is only permitted for label_id/note, as in those request models.
fn optional_present<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(deserializer).map(Some)
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum AnnotationRequest {
    Superpixels {
        id: String,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        n_segments: Option<u32>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        compactness: Option<f64>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        pca_components: Option<u32>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        force: Option<bool>,
    },
    Diffuse {
        id: String,
        seed: Seed,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        threshold: Option<f64>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        queue_min_similarity: Option<f64>,
    },
    Regions {
        id: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        label_id: Option<String>,
        geometry: Geometry,
        action: Action,
    },
    Undo {
        id: String,
    },
    Working {
        id: String,
    },
    Validate {
        id: String,
    },
    Save {
        id: String,
        #[serde(skip_serializing_if = "Option::is_none")]
        note: Option<String>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        overwrite: Option<bool>,
        #[serde(
            default,
            deserialize_with = "optional_present",
            skip_serializing_if = "Option::is_none"
        )]
        confirm: Option<bool>,
    },
    Versions {
        id: String,
    },
    VersionOverlay {
        id: String,
        version: String,
    },
}

fn uuid(value: &str, code: &str) -> Result<(), ForwardError> {
    if value.len() != 36
        || !value.bytes().enumerate().all(|(i, c)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                c == b'-'
            } else {
                c.is_ascii_hexdigit()
            }
        })
    {
        return Err(ForwardError::new(code, "路径标识必须为规范UUID"));
    }
    Ok(())
}

fn invalid_request() -> ForwardError {
    // Never include serde's error text: unknown keys/values can contain secrets.
    ForwardError::new("INVALID_REQUEST", "标注请求字段、类型或取值非法")
}

// The command accepts JSON only to convert deserialization failures to the
// existing structured envelope. No unvalidated Value reaches the transport.
pub fn parse_request(value: Value) -> Result<AnnotationRequest, ForwardError> {
    let request: AnnotationRequest =
        serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl AnnotationRequest {
    fn id(&self) -> &str {
        match self {
            Self::Superpixels { id, .. }
            | Self::Diffuse { id, .. }
            | Self::Regions { id, .. }
            | Self::Undo { id }
            | Self::Working { id }
            | Self::Validate { id }
            | Self::Save { id, .. }
            | Self::Versions { id }
            | Self::VersionOverlay { id, .. } => id,
        }
    }

    fn validate(&self) -> Result<(), ForwardError> {
        uuid(self.id(), "INVALID_DATASET_ID")?;
        let valid = match self {
            Self::Superpixels {
                n_segments,
                compactness,
                pca_components,
                ..
            } => {
                n_segments.is_none_or(|v| v > 0)
                    && pca_components.is_none_or(|v| v > 0)
                    && compactness.is_none_or(|v| v.is_finite() && v > 0.0)
            }
            Self::Diffuse {
                seed,
                threshold,
                queue_min_similarity,
                ..
            } => {
                !matches!(seed, Seed::Doodle { doodle } if doodle.is_empty())
                    && [threshold, queue_min_similarity]
                        .into_iter()
                        .all(|v| v.is_none_or(|v| v.is_finite() && (-1.0..=1.0).contains(&v)))
            }
            Self::Regions { geometry, .. } => match geometry {
                Geometry::Superpixels { superpixels } => !superpixels.is_empty(),
                Geometry::Polygon { polygon } => {
                    polygon.len() >= 3 && polygon.iter().flatten().all(|v| v.is_finite())
                }
            },
            // TASK-04 R19: note <= 2000 Unicode characters, matching Pydantic.
            Self::Save { note, .. } => note.as_ref().is_none_or(|v| v.chars().count() <= 2000),
            Self::VersionOverlay { version, .. } => {
                uuid(version, "INVALID_VERSION_ID")?;
                true
            }
            _ => true,
        };
        if !valid {
            return Err(invalid_request());
        }
        Ok(())
    }

    fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (suffix, method, has_body) = match self {
            Self::Superpixels { .. } => ("superpixels".to_owned(), Method::POST, true),
            Self::Diffuse { .. } => ("diffuse".to_owned(), Method::POST, true),
            Self::Regions { .. } => ("annotations/regions".to_owned(), Method::POST, true),
            Self::Undo { .. } => ("annotations/undo".to_owned(), Method::POST, false),
            Self::Working { .. } => ("annotations/working".to_owned(), Method::GET, false),
            Self::Validate { .. } => ("annotations/validate".to_owned(), Method::POST, false),
            Self::Save { .. } => ("annotations/save".to_owned(), Method::POST, true),
            Self::Versions { .. } => ("annotations".to_owned(), Method::GET, false),
            Self::VersionOverlay { version, .. } => {
                (format!("annotations/{version}/overlay"), Method::GET, false)
            }
        };
        let mut url = Url::parse("http://127.0.0.1/")
            .map_err(|_| ForwardError::new("TRANSPORT", "本机地址构造失败"))?;
        if port == 0 || url.set_port(Some(port)).is_err() {
            return Err(ForwardError::new("TRANSPORT", "握手端口非法"));
        }
        url.set_path(&format!("/api/v1/datasets/{}/{suffix}", self.id()));
        let body = if has_body {
            let mut value = serde_json::to_value(self).map_err(|_| invalid_request())?;
            let object = value.as_object_mut().ok_or_else(invalid_request)?;
            object.remove("op");
            object.remove("id");
            Some(value)
        } else {
            None
        };
        Ok((url, method, body))
    }
}

pub fn forward(identity: &Handshake, request: &AnnotationRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    let client = Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(30))
        .build()
        .map_err(|_| ForwardError::new("TRANSPORT", "本机请求初始化失败"))?;
    let mut outgoing = client.request(method, url).bearer_auth(identity.token());
    if let Some(body) = body {
        outgoing = outgoing.json(&body);
    }
    let response = outgoing
        .send()
        .map_err(|_| ForwardError::new("TRANSPORT", "数据引擎请求失败或超时"))?;
    // Identity is checked before status and body, including errors and redirects.
    let header = |key| response.headers().get(key).and_then(|v| v.to_str().ok());
    if header("X-SpectrumAgent-Boot-Id") != Some(identity.boot_id.as_str())
        || header("X-SpectrumAgent-Pid") != Some(identity.pid.to_string().as_str())
    {
        return Err(ForwardError::new(
            "DATASET_IDENTITY_MISMATCH",
            "数据响应与本代引擎身份不匹配",
        ));
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_RESPONSE_BYTES)
    {
        return Err(ForwardError::new(
            "RESPONSE_TOO_LARGE",
            "数据响应超过8MiB上限",
        ));
    }
    let status = response.status();
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ForwardError::new("TRANSPORT", "读取数据响应失败"))?;
    if bytes.len() as u64 > MAX_RESPONSE_BYTES {
        return Err(ForwardError::new(
            "RESPONSE_TOO_LARGE",
            "数据响应超过8MiB上限",
        ));
    }
    if bytes
        .windows(identity.token().len())
        .any(|slice| slice == identity.token().as_bytes())
    {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "数据响应包含敏感身份信息，已拒绝转发",
        ));
    }
    let value: Value = serde_json::from_slice(&bytes)
        .map_err(|_| ForwardError::new("INVALID_BODY", "数据响应不是有效JSON"))?;
    // JSON escapes must not let a reflected credential cross the bridge either.
    let canonical = serde_json::to_vec(&value)
        .map_err(|_| ForwardError::new("INVALID_BODY", "数据响应无法序列化"))?;
    if canonical
        .windows(identity.token().len())
        .any(|slice| slice == identity.token().as_bytes())
    {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "数据响应包含敏感身份信息，已拒绝转发",
        ));
    }
    if !status.is_success() {
        return Err(serde_json::from_value(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "数据引擎返回错误")));
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::{
        io::{self, Write},
        net::TcpListener,
        thread,
        time::Instant,
    };

    fn exchange(
        status: &str,
        headers: &str,
        body: Vec<u8>,
        length: Option<u64>,
    ) -> Result<Result<Value, ForwardError>, Box<dyn std::error::Error>> {
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        let port = listener.local_addr()?.port();
        listener.set_nonblocking(true)?;
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,
            "token":"0123456789abcdef0123456789abcdef","protocol":1,"version":"0.1.0",
            "process_created_at":"2026-10-19T00:00:00.000Z","started_at":"2026-10-19T00:00:00.000Z"
        }))?)?;
        let mut response = format!("HTTP/1.1 {status}\r\nConnection: close\r\n{headers}");
        if let Some(length) = length {
            response.push_str(&format!("Content-Length: {length}\r\n"));
        }
        response.push_str("\r\n");
        let server = thread::spawn(move || -> io::Result<()> {
            let deadline = Instant::now() + Duration::from_secs(5);
            let mut socket = loop {
                match listener.accept() {
                    Ok((socket, _)) => break socket,
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                        if Instant::now() >= deadline {
                            return Err(io::Error::new(
                                io::ErrorKind::TimedOut,
                                "stub server: accept timeout",
                            ));
                        }
                        thread::sleep(Duration::from_millis(2));
                    }
                    Err(error) => return Err(error),
                }
            };
            socket.set_nonblocking(false)?;
            socket.set_read_timeout(Some(Duration::from_secs(3)))?;
            let mut incoming = Vec::new();
            let mut buffer = [0u8; 1024];
            while !incoming.windows(4).any(|part| part == b"\r\n\r\n") {
                let n = socket.read(&mut buffer)?;
                if n == 0 || incoming.len() > 16384 {
                    return Err(io::Error::other("invalid request"));
                }
                incoming.extend_from_slice(&buffer[..n]);
            }
            let incoming = String::from_utf8_lossy(&incoming);
            assert!(incoming.starts_with(
                "GET /api/v1/datasets/00000000-0000-0000-0000-000000000001/annotations/working HTTP/1.1"
            ));
            assert!(
                incoming
                    .to_ascii_lowercase()
                    .contains("authorization: bearer ")
            );
            socket.write_all(response.as_bytes())?;
            // The bounded reader may close deliberately before this finishes.
            let _ = socket.write_all(&body);
            Ok(())
        });
        let result = forward(
            &identity,
            &AnnotationRequest::Working {
                id: "00000000-0000-0000-0000-000000000001".into(),
            },
        );
        server
            .join()
            .map_err(|_| io::Error::other("stub thread failed"))??;
        Ok(result)
    }

    const IDENTITY: &str = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";

    #[test]
    fn response_identity_precedes_status_and_body() -> Result<(), Box<dyn std::error::Error>> {
        for headers in [
            "",
            "X-SpectrumAgent-Boot-Id: deadbeef\r\nX-SpectrumAgent-Pid: 123\r\n",
            "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: abc\r\n",
        ] {
            let result = exchange("500 Error", headers, b"not json".to_vec(), Some(8))?;
            assert_eq!(
                result.err().map(|e| e.error),
                Some("DATASET_IDENTITY_MISMATCH".into())
            );
        }
        let value = exchange(
            "200 OK",
            "x-sPectrumAgent-bOoT-iD: 1234abcd\r\nx-spectrumagent-pid: 123\r\n",
            b"{\"ok\":true}".to_vec(),
            Some(11),
        )??;
        assert_eq!(value, json!({"ok":true}));
        Ok(())
    }

    #[test]
    fn declared_and_streaming_response_limits_are_enforced()
    -> Result<(), Box<dyn std::error::Error>> {
        for length in [Some(MAX_RESPONSE_BYTES + 1), None] {
            let body = if length.is_none() {
                vec![b' '; (MAX_RESPONSE_BYTES + 1) as usize]
            } else {
                Vec::new()
            };
            let result = exchange("200 OK", IDENTITY, body, length)?;
            assert_eq!(
                result.err().map(|e| e.error),
                Some("RESPONSE_TOO_LARGE".into())
            );
        }
        Ok(())
    }

    #[test]
    fn redirects_are_not_followed_and_sensitive_bodies_never_leave_rust()
    -> Result<(), Box<dyn std::error::Error>> {
        let result = exchange(
            "307 Redirect",
            &format!("{IDENTITY}Location: http://127.0.0.1:1/forbidden\r\n"),
            b"{}".to_vec(),
            Some(2),
        )?;
        assert_eq!(result.err().map(|e| e.error), Some("HTTP_ERROR".into()));
        let result = exchange(
            "200 OK",
            IDENTITY,
            b"\"0123456789abcdef0123456789abcdef\"".to_vec(),
            Some(34),
        )?;
        let error = result
            .err()
            .ok_or_else(|| io::Error::other("expected sensitive rejection"))?;
        assert_eq!(error.error, "SENSITIVE_RESPONSE");
        assert!(!serde_json::to_string(&error)?.contains("0123456789abcdef"));
        let escaped = format!(
            "\"{}\"",
            "0123456789abcdef0123456789abcdef"
                .chars()
                .map(|c| format!("\\u{:04x}", c as u32))
                .collect::<String>()
        )
        .into_bytes();
        let length = escaped.len() as u64;
        let error = exchange("200 OK", IDENTITY, escaped, Some(length))?
            .err()
            .ok_or_else(|| io::Error::other("expected escaped credential rejection"))?;
        assert_eq!(error.error, "SENSITIVE_RESPONSE");
        Ok(())
    }

    #[test]
    fn structured_sidecar_errors_are_preserved_after_identity_validation()
    -> Result<(), Box<dyn std::error::Error>> {
        let body =
            br#"{"error":"FILE_NOT_FOUND","detail":"source missing","context":{"path":"C:/data"}}"#
                .to_vec();
        let length = body.len() as u64;
        let error = exchange("400 Bad Request", IDENTITY, body, Some(length))?
            .err()
            .ok_or_else(|| io::Error::other("expected error"))?;
        assert_eq!(error.error, "FILE_NOT_FOUND");
        assert_eq!(error.context["path"], "C:/data");
        Ok(())
    }

    const ID: &str = "00000000-0000-0000-0000-000000000001";
    const VERSION: &str = "00000000-0000-0000-0000-000000000002";

    #[test]
    fn all_nine_operations_have_exact_paths_methods_and_bodies() -> Result<(), ForwardError> {
        let cases = [
            (
                json!({"op":"superpixels","id":ID,"n_segments":800,"compactness":0.5,"pca_components":3,"force":true}),
                "superpixels".into(),
                Method::POST,
                Some(json!({"n_segments":800,"compactness":0.5,"pca_components":3,"force":true})),
            ),
            (
                json!({"op":"diffuse","id":ID,"seed":{"point":[1,2]},"threshold":0.92,"queue_min_similarity":0.8}),
                "diffuse".into(),
                Method::POST,
                Some(json!({"seed":{"point":[1,2]},"threshold":0.92,"queue_min_similarity":0.8})),
            ),
            (
                json!({"op":"regions","id":ID,"geometry":{"superpixels":[0,1]},"action":"confirm","label_id":"label"}),
                "annotations/regions".into(),
                Method::POST,
                Some(
                    json!({"geometry":{"superpixels":[0,1]},"action":"confirm","label_id":"label"}),
                ),
            ),
            (
                json!({"op":"undo","id":ID}),
                "annotations/undo".into(),
                Method::POST,
                None,
            ),
            (
                json!({"op":"working","id":ID}),
                "annotations/working".into(),
                Method::GET,
                None,
            ),
            (
                json!({"op":"validate","id":ID}),
                "annotations/validate".into(),
                Method::POST,
                None,
            ),
            (
                json!({"op":"save","id":ID,"note":"备注","overwrite":true,"confirm":true}),
                "annotations/save".into(),
                Method::POST,
                Some(json!({"note":"备注","overwrite":true,"confirm":true})),
            ),
            (
                json!({"op":"versions","id":ID}),
                "annotations".into(),
                Method::GET,
                None,
            ),
            (
                json!({"op":"version_overlay","id":ID,"version":VERSION}),
                format!("annotations/{VERSION}/overlay"),
                Method::GET,
                None,
            ),
        ];
        for (input, suffix, method, body) in cases {
            let (url, actual_method, actual_body) = parse_request(input)?.destination(4321)?;
            assert_eq!(url.scheme(), "http");
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(4321));
            assert_eq!(url.path(), format!("/api/v1/datasets/{ID}/{suffix}"));
            assert_eq!(url.query(), None);
            assert_eq!(url.fragment(), None);
            assert_eq!(actual_method, method);
            assert_eq!(actual_body, body);
        }
        Ok(())
    }

    #[test]
    fn omitted_parameters_stay_omitted_and_all_prompt_geometries_are_typed()
    -> Result<(), ForwardError> {
        for (input, expected) in [
            (json!({"op":"superpixels","id":ID}), json!({})),
            (json!({"op":"save","id":ID}), json!({})),
            (
                json!({"op":"diffuse","id":ID,"seed":{"box":[0,2,0,3]}}),
                json!({"seed":{"box":[0,2,0,3]}}),
            ),
            (
                json!({"op":"diffuse","id":ID,"seed":{"doodle":[[0,0],[2,3]]}}),
                json!({"seed":{"doodle":[[0,0],[2,3]]}}),
            ),
            (
                json!({"op":"regions","id":ID,"geometry":{"polygon":[[0,0],[1,0],[0,1]]},"action":"uncertain"}),
                json!({"geometry":{"polygon":[[0.0,0.0],[1.0,0.0],[0.0,1.0]]},"action":"uncertain"}),
            ),
            (
                json!({"op":"regions","id":ID,"geometry":{"superpixels":[1]},"action":"erase"}),
                json!({"geometry":{"superpixels":[1]},"action":"erase"}),
            ),
        ] {
            assert_eq!(parse_request(input)?.destination(4321)?.2, Some(expected));
        }
        Ok(())
    }

    #[test]
    fn unknown_operations_and_fields_are_structured_and_never_reflect_input()
    -> Result<(), Box<dyn std::error::Error>> {
        for input in [
            json!({"op":"proxy","url":"https://example.com"}),
            json!({"op":"working","id":ID,"body":{}}),
            json!({"op":"superpixels","id":ID,"convert2lab":true}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0],"box":[0,1,0,1]}}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0],"width":2}}),
            json!({"op":"regions","id":ID,"geometry":{"superpixels":[1],"polygon":[[0,0],[1,0],[0,1]]},"action":"uncertain"}),
            json!({"op":"regions","id":ID,"geometry":{"superpixels":[1],"dilate":1},"action":"erase"}),
            json!({"op":"working","id":ID,"0123456789abcdef0123456789abcdef":true}),
        ] {
            let error = parse_request(input)
                .err()
                .ok_or_else(|| io::Error::other("expected rejection"))?;
            assert_eq!(error.error, "INVALID_REQUEST");
            let value = serde_json::to_value(error)?;
            assert!(value["detail"].is_string());
            assert_eq!(value["context"], json!({}));
            assert!(!value.to_string().contains("0123456789abcdef"));
        }
        Ok(())
    }

    #[test]
    fn no_free_url_host_port_path_or_method_can_enter_any_operation() -> Result<(), ForwardError> {
        for op in [
            "superpixels",
            "diffuse",
            "regions",
            "undo",
            "working",
            "validate",
            "save",
            "versions",
            "version_overlay",
        ] {
            let mut input = json!({"op":op,"id":ID});
            match op {
                "diffuse" => input["seed"] = json!({"point":[0,0]}),
                "regions" => {
                    input["geometry"] = json!({"superpixels":[0]});
                    input["action"] = json!("uncertain");
                }
                "version_overlay" => input["version"] = json!(VERSION),
                _ => {}
            }
            parse_request(input.clone())?;
            for field in ["url", "host", "port", "path", "method"] {
                let mut bad = input.clone();
                bad[field] = json!("http://example.com/../../health");
                assert!(parse_request(bad).is_err());
            }
        }
        Ok(())
    }

    #[test]
    fn identifiers_cannot_escape_and_version_numbers_are_not_uuids() {
        for bad in [
            "../../health",
            "http://127.0.0.1:1234/",
            "1",
            "",
            "00000000-0000-0000-0000-000000000001/..",
            "%2fhealth",
        ] {
            let dataset = parse_request(json!({"op":"working","id":bad}));
            assert_eq!(
                dataset.err().map(|e| e.error),
                Some("INVALID_DATASET_ID".into())
            );
            let version = parse_request(json!({"op":"version_overlay","id":ID,"version":bad}));
            assert_eq!(
                version.err().map(|e| e.error),
                Some("INVALID_VERSION_ID".into())
            );
        }
    }

    #[test]
    fn bad_types_lengths_and_out_of_range_parameters_are_rejected() {
        for input in [
            json!(null),
            json!([]),
            json!({"op":"save"}),
            json!({"op":"superpixels","id":ID,"n_segments":0}),
            json!({"op":"superpixels","id":ID,"n_segments":-1}),
            json!({"op":"superpixels","id":ID,"n_segments":4294967296_u64}),
            json!({"op":"superpixels","id":ID,"n_segments":3.5}),
            json!({"op":"superpixels","id":ID,"pca_components":0}),
            json!({"op":"superpixels","id":ID,"compactness":0}),
            json!({"op":"superpixels","id":ID,"force":"true"}),
            json!({"op":"superpixels","id":ID,"force":null}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0]},"threshold":1.01}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0]},"queue_min_similarity":-1.01}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0]},"threshold":null}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[true,0]}}),
            json!({"op":"diffuse","id":ID,"seed":{"point":[0,0,0]}}),
            json!({"op":"diffuse","id":ID,"seed":{"box":[0,1,0]}}),
            json!({"op":"diffuse","id":ID,"seed":{"doodle":[]}}),
            json!({"op":"regions","id":ID,"geometry":{"superpixels":[]},"action":"erase"}),
            json!({"op":"regions","id":ID,"geometry":{"superpixels":[-1]},"action":"erase"}),
            json!({"op":"regions","id":ID,"geometry":{"polygon":[[0,0],[1,1]]},"action":"erase"}),
            json!({"op":"regions","id":ID,"geometry":{"superpixels":[1]},"action":"automatic"}),
            json!({"op":"save","id":ID,"confirm":1}),
            json!({"op":"save","id":ID,"note":true}),
            json!({"op":"save","id":ID,"note":"字".repeat(2001)}),
        ] {
            assert_eq!(
                parse_request(input).err().map(|e| e.error),
                Some("INVALID_REQUEST".into())
            );
        }
    }

    #[test]
    fn parameter_edges_and_unicode_note_match_http_contract() -> Result<(), ForwardError> {
        parse_request(json!({"op":"save","id":ID,"note":"字".repeat(2000)}))?;
        parse_request(json!({"op":"save","id":ID,"note":null}))?;
        for threshold in [-1.0, 1.0] {
            parse_request(
                json!({"op":"diffuse","id":ID,"seed":{"point":[0,0]},"threshold":threshold,"queue_min_similarity":threshold}),
            )?;
        }
        Ok(())
    }

    #[test]
    fn only_the_supplied_nonzero_handshake_port_is_used() -> Result<(), ForwardError> {
        let request = parse_request(json!({"op":"working","id":ID}))?;
        assert_eq!(
            request.destination(0).err().map(|e| e.error),
            Some("TRANSPORT".into())
        );
        for port in [1, 80, 4321, u16::MAX] {
            let url = request.destination(port)?.0;
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port_or_known_default(), Some(port));
            assert_eq!(url.username(), "");
            assert_eq!(url.password(), None);
        }
        assert_eq!(MAX_RESPONSE_BYTES, crate::datasets_dev::MAX_RESPONSE_BYTES);
        Ok(())
    }

    #[test]
    fn an_exactly_eight_mib_json_response_is_allowed() -> Result<(), Box<dyn std::error::Error>> {
        let mut body = b"{\"ok\":true}".to_vec();
        body.resize(MAX_RESPONSE_BYTES as usize, b' ');
        assert_eq!(
            exchange("200 OK", IDENTITY, body, Some(MAX_RESPONSE_BYTES))??,
            json!({"ok":true})
        );
        Ok(())
    }
}
