//! TASK-05 11.5/R13/R14: fixed preprocessing operations, not a general proxy.
use crate as spectrum_agent;
pub use crate::annotation::ForwardError;
use crate::{handshake::Handshake, state::Phase, supervisor::Snapshot};
use reqwest::{
    Method, Url,
    blocking::{Client, ClientBuilder},
};
use serde::Deserialize;
use serde_json::{Value, json};
use spectrum_agent::annotation::MAX_RESPONSE_BYTES;
use std::{io::Read, time::Duration};

#[derive(Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactKind {
    SampleSpectra,
    Report,
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum PreprocessRequest {
    ListRecipes,
    CreateRecipe {
        body: Value,
    },
    GetRecipe {
        id: String,
    },
    AddVersion {
        id: String,
        body: Value,
    },
    SelectRecipe {
        project_id: String,
        recipe_id: String,
    },
    DeselectRecipe {
        project_id: String,
        recipe_id: String,
    },
    ListProjectRecipes {
        project_id: String,
    },
    CreateRun {
        dataset_id: String,
        body: Value,
    },
    ListRuns {
        dataset_id: String,
    },
    GetRun {
        id: String,
    },
    Compare {
        dataset_id: String,
        body: Value,
    },
    GetArtifact {
        run_id: String,
        kind: ArtifactKind,
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
    // Caller-controlled serde diagnostics must never reflect a credential.
    ForwardError::new("INVALID_REQUEST", "预处理请求字段、类型或取值非法")
}

pub fn parse_request(value: Value) -> Result<PreprocessRequest, ForwardError> {
    // Serde's internally tagged UNIT variant ignores surplus keys even with
    // deny_unknown_fields. Keep ListRecipes a unit variant but enforce its
    // empty payload explicitly, before discarding the caller's object.
    let extra_unit_fields = value.as_object().is_some_and(|fields| fields.len() != 1);
    let request: PreprocessRequest =
        serde_json::from_value(value).map_err(|_| invalid_request())?;
    if matches!(request, PreprocessRequest::ListRecipes) && extra_unit_fields {
        return Err(invalid_request());
    }
    request.validate()?;
    Ok(request)
}

impl PreprocessRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        match self {
            Self::GetRecipe { id } | Self::AddVersion { id, .. } => uuid(id, "INVALID_RECIPE_ID"),
            Self::GetRun { id } => uuid(id, "INVALID_RUN_ID"),
            Self::GetArtifact { run_id, .. } => uuid(run_id, "INVALID_RUN_ID"),
            Self::CreateRun { dataset_id, .. }
            | Self::ListRuns { dataset_id }
            | Self::Compare { dataset_id, .. } => uuid(dataset_id, "INVALID_DATASET_ID"),
            Self::SelectRecipe {
                project_id,
                recipe_id,
            }
            | Self::DeselectRecipe {
                project_id,
                recipe_id,
            } => {
                uuid(project_id, "INVALID_PROJECT_ID")?;
                uuid(recipe_id, "INVALID_RECIPE_ID")
            }
            Self::ListProjectRecipes { project_id } => uuid(project_id, "INVALID_PROJECT_ID"),
            Self::ListRecipes | Self::CreateRecipe { .. } => Ok(()),
        }
    }

    fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let mut url = Url::parse("http://127.0.0.1/")
            .map_err(|_| ForwardError::new("TRANSPORT", "本机地址构造失败"))?;
        if port == 0 || url.set_port(Some(port)).is_err() {
            return Err(ForwardError::new("TRANSPORT", "握手端口非法"));
        }
        let (path, method, body) = match self {
            Self::ListRecipes => ("/api/v1/preprocess/recipes".into(), Method::GET, None),
            Self::CreateRecipe { body } => (
                "/api/v1/preprocess/recipes".into(),
                Method::POST,
                Some(body.clone()),
            ),
            Self::GetRecipe { id } => (
                format!("/api/v1/preprocess/recipes/{id}"),
                Method::GET,
                None,
            ),
            Self::AddVersion { id, body } => (
                format!("/api/v1/preprocess/recipes/{id}/versions"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::SelectRecipe {
                project_id,
                recipe_id,
            } => (
                format!("/api/v1/preprocess/projects/{project_id}/recipes/{recipe_id}"),
                Method::POST,
                None,
            ),
            Self::DeselectRecipe {
                project_id,
                recipe_id,
            } => (
                format!("/api/v1/preprocess/projects/{project_id}/recipes/{recipe_id}"),
                Method::DELETE,
                None,
            ),
            Self::ListProjectRecipes { project_id } => (
                format!("/api/v1/preprocess/projects/{project_id}/recipes"),
                Method::GET,
                None,
            ),
            Self::CreateRun { dataset_id, body } => (
                format!("/api/v1/datasets/{dataset_id}/preprocess/runs"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::ListRuns { dataset_id } => (
                format!("/api/v1/datasets/{dataset_id}/preprocess/runs"),
                Method::GET,
                None,
            ),
            Self::GetRun { id } => (format!("/api/v1/preprocess/runs/{id}"), Method::GET, None),
            Self::Compare { dataset_id, body } => (
                format!("/api/v1/datasets/{dataset_id}/preprocess/compare"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::GetArtifact { run_id, kind } => {
                let kind = match kind {
                    ArtifactKind::SampleSpectra => "sample_spectra",
                    ArtifactKind::Report => "report",
                };
                (
                    format!("/api/v1/preprocess/runs/{run_id}/artifacts/{kind}"),
                    Method::GET,
                    None,
                )
            }
        };
        url.set_path(&path);
        Ok((url, method, body))
    }
}

fn client_builder() -> ClientBuilder {
    Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(300))
}

fn reject_sensitive(bytes: &[u8], identity: &Handshake) -> Result<(), ForwardError> {
    if bytes
        .windows(identity.token().len())
        .any(|slice| slice == identity.token().as_bytes())
    {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "数据响应包含敏感身份信息，已拒绝转发",
        ));
    }
    Ok(())
}

fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut encoded = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let first = chunk[0];
        let second = chunk.get(1).copied().unwrap_or(0);
        let third = chunk.get(2).copied().unwrap_or(0);
        encoded.push(ALPHABET[(first >> 2) as usize] as char);
        encoded.push(ALPHABET[(((first & 3) << 4) | (second >> 4)) as usize] as char);
        encoded.push(if chunk.len() > 1 {
            ALPHABET[(((second & 15) << 2) | (third >> 6)) as usize] as char
        } else {
            '='
        });
        encoded.push(if chunk.len() > 2 {
            ALPHABET[(third & 63) as usize] as char
        } else {
            '='
        });
    }
    encoded
}

pub fn validate_generation(generation: u64, current: &Snapshot) -> Result<(), ForwardError> {
    if current.generation_id != generation || current.phase != Phase::Ready {
        return Err(ForwardError::new(
            "STALE_RESPONSE",
            "引擎代次已变化，请重试",
        ));
    }
    Ok(())
}

pub fn forward(identity: &Handshake, request: &PreprocessRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    let client = client_builder()
        .build()
        .map_err(|_| ForwardError::new("TRANSPORT", "本机请求初始化失败"))?;
    let mut outgoing = client.request(method, url).bearer_auth(identity.token());
    if let Some(body) = body {
        outgoing = outgoing.json(&body);
    }
    let response = outgoing
        .send()
        .map_err(|_| ForwardError::new("TRANSPORT", "数据引擎请求失败或超时"))?;
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
    let binary = matches!(request, PreprocessRequest::GetArtifact { .. })
        && status.is_success()
        && header("Content-Type") == Some("application/octet-stream");
    // 11.3 artifact filenames are fixed; use FileResponse's ASCII filename when present.
    let filename = header("Content-Disposition")
        .and_then(|value| {
            value.split(';').find_map(|part| {
                part.trim()
                    .strip_prefix("filename=")
                    .map(|name| name.trim_matches('"').to_owned())
            })
        })
        .unwrap_or_else(|| match request {
            PreprocessRequest::GetArtifact {
                kind: ArtifactKind::Report,
                ..
            } => "report.json".into(),
            _ => "sample_spectra.npz".into(),
        });
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
    reject_sensitive(&bytes, identity)?;
    if status == 204 {
        return Ok(Value::Null);
    }
    let value = if binary {
        json!({"content_type":"application/octet-stream", "body_base64":base64(&bytes), "filename":filename})
    } else {
        serde_json::from_slice(&bytes)
            .map_err(|_| ForwardError::new("INVALID_BODY", "数据响应不是有效JSON"))?
    };
    let canonical = serde_json::to_vec(&value)
        .map_err(|_| ForwardError::new("INVALID_BODY", "数据响应无法序列化"))?;
    reject_sensitive(&canonical, identity)?;
    if !status.is_success() {
        return Err(serde_json::from_value(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "数据引擎返回错误")));
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        io::{self, Write},
        net::{TcpListener, TcpStream},
        thread,
        time::Instant,
    };

    const ID: &str = "00000000-0000-0000-0000-000000000001";
    const OTHER: &str = "00000000-0000-0000-0000-000000000002";
    const TOKEN: &str = "0123456789abcdef0123456789abcdef";
    const IDENTITY: &str = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn read_request(socket: &mut TcpStream) -> io::Result<String> {
        let mut incoming = Vec::new();
        let mut buffer = [0u8; 1024];
        loop {
            let n = socket.read(&mut buffer)?;
            if n == 0 || incoming.len() > 65536 {
                return Err(io::Error::other("invalid stub request"));
            }
            incoming.extend_from_slice(&buffer[..n]);
            if let Some(end) = incoming.windows(4).position(|part| part == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&incoming[..end]);
                let length = headers
                    .lines()
                    .find_map(|line| {
                        line.to_ascii_lowercase()
                            .strip_prefix("content-length: ")
                            .and_then(|v| v.parse::<usize>().ok())
                    })
                    .unwrap_or(0);
                if incoming.len() >= end + 4 + length {
                    return String::from_utf8(incoming).map_err(io::Error::other);
                }
            }
        }
    }

    fn exchange(
        request: Value,
        status: &str,
        headers: &str,
        body: Vec<u8>,
        length: Option<u64>,
    ) -> Result<(Result<Value, ForwardError>, String), Box<dyn std::error::Error>> {
        let request = parse_request(request)?;
        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        let port = listener.local_addr()?.port();
        listener.set_nonblocking(true)?;
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,"token":TOKEN,"protocol":1,"version":"0.1.0",
            "process_created_at":"2026-10-19T00:00:00.000Z","started_at":"2026-10-19T00:00:00.000Z"
        }))?)?;
        let mut response = format!("HTTP/1.1 {status}\r\nConnection: close\r\n{headers}");
        if let Some(length) = length {
            response.push_str(&format!("Content-Length: {length}\r\n"));
        }
        response.push_str("\r\n");
        let server = thread::spawn(move || -> io::Result<String> {
            let deadline = Instant::now() + Duration::from_secs(5);
            let mut socket = loop {
                match listener.accept() {
                    Ok((socket, _)) => break socket,
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                        if Instant::now() >= deadline {
                            return Err(io::Error::new(
                                io::ErrorKind::TimedOut,
                                "stub accept timeout",
                            ));
                        }
                        thread::sleep(Duration::from_millis(2));
                    }
                    Err(error) => return Err(error),
                }
            };
            socket.set_nonblocking(false)?;
            socket.set_read_timeout(Some(Duration::from_secs(3)))?;
            let incoming = read_request(&mut socket)?;
            assert!(
                incoming
                    .to_ascii_lowercase()
                    .contains(&format!("authorization: bearer {TOKEN}"))
            );
            socket.write_all(response.as_bytes())?;
            let _ = socket.write_all(&body); // A size guard can intentionally close early.
            Ok(incoming)
        });
        let result = forward(&identity, &request);
        let incoming = server
            .join()
            .map_err(|_| io::Error::other("stub thread failed"))??;
        Ok((result, incoming))
    }

    fn decode_base64(text: &str) -> Result<Vec<u8>, io::Error> {
        // Independent decoder: bit accumulator, rather than encoder chunk logic.
        let alphabet = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
        let (mut accumulator, mut bits, mut result) = (0u32, 0u32, Vec::new());
        for c in text.bytes().take_while(|&c| c != b'=') {
            let value = alphabet
                .iter()
                .position(|&v| v == c)
                .ok_or_else(|| io::Error::other("invalid base64"))?;
            accumulator = (accumulator << 6) | value as u32;
            bits += 6;
            if bits >= 8 {
                bits -= 8;
                result.push((accumulator >> bits) as u8);
                accumulator &= (1 << bits) - 1;
            }
        }
        Ok(result)
    }

    #[test]
    fn all_twelve_destinations_methods_and_exact_bodies() -> TestResult {
        let body = json!({"deliberately_dynamic":true});
        let cases = [
            (
                json!({"op":"list_recipes"}),
                "/api/v1/preprocess/recipes".into(),
                Method::GET,
                None,
            ),
            (
                json!({"op":"create_recipe","body":body}),
                "/api/v1/preprocess/recipes".into(),
                Method::POST,
                Some(body.clone()),
            ),
            (
                json!({"op":"get_recipe","id":ID}),
                format!("/api/v1/preprocess/recipes/{ID}"),
                Method::GET,
                None,
            ),
            (
                json!({"op":"add_version","id":ID,"body":body}),
                format!("/api/v1/preprocess/recipes/{ID}/versions"),
                Method::POST,
                Some(body.clone()),
            ),
            (
                json!({"op":"select_recipe","project_id":ID,"recipe_id":OTHER}),
                format!("/api/v1/preprocess/projects/{ID}/recipes/{OTHER}"),
                Method::POST,
                None,
            ),
            (
                json!({"op":"deselect_recipe","project_id":ID,"recipe_id":OTHER}),
                format!("/api/v1/preprocess/projects/{ID}/recipes/{OTHER}"),
                Method::DELETE,
                None,
            ),
            (
                json!({"op":"list_project_recipes","project_id":ID}),
                format!("/api/v1/preprocess/projects/{ID}/recipes"),
                Method::GET,
                None,
            ),
            (
                json!({"op":"create_run","dataset_id":ID,"body":body}),
                format!("/api/v1/datasets/{ID}/preprocess/runs"),
                Method::POST,
                Some(body.clone()),
            ),
            (
                json!({"op":"list_runs","dataset_id":ID}),
                format!("/api/v1/datasets/{ID}/preprocess/runs"),
                Method::GET,
                None,
            ),
            (
                json!({"op":"get_run","id":ID}),
                format!("/api/v1/preprocess/runs/{ID}"),
                Method::GET,
                None,
            ),
            (
                json!({"op":"compare","dataset_id":ID,"body":body}),
                format!("/api/v1/datasets/{ID}/preprocess/compare"),
                Method::POST,
                Some(body.clone()),
            ),
            (
                json!({"op":"get_artifact","run_id":ID,"kind":"sample_spectra"}),
                format!("/api/v1/preprocess/runs/{ID}/artifacts/sample_spectra"),
                Method::GET,
                None,
            ),
        ];
        for (value, path, expected_method, expected_body) in cases {
            let mut extra = value.clone();
            extra["url"] = json!("http://outside/forbidden");
            assert_eq!(
                parse_request(extra).err().map(|e| e.error),
                Some("INVALID_REQUEST".into())
            );
            let (url, method, body) = parse_request(value)?.destination(54321)?;
            assert_eq!(url.path(), path);
            assert_eq!(method, expected_method);
            assert_eq!(body, expected_body);
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(54321));
            assert_eq!(url.scheme(), "http");
            assert!(url.query().is_none() && url.fragment().is_none());
        }
        assert!(
            parse_request(json!({"op":"get_artifact","run_id":ID,"kind":"report"}))?
                .destination(1234)?
                .0
                .path()
                .ends_with("/artifacts/report")
        );
        Ok(())
    }

    #[test]
    fn four_uuid_error_codes_cover_every_identifier_field() {
        let cases = [
            (
                json!({"op":"create_run","dataset_id":"bad","body":{}}),
                "INVALID_DATASET_ID",
            ),
            (
                json!({"op":"list_runs","dataset_id":"bad"}),
                "INVALID_DATASET_ID",
            ),
            (
                json!({"op":"compare","dataset_id":"bad","body":{}}),
                "INVALID_DATASET_ID",
            ),
            (json!({"op":"get_run","id":"bad"}), "INVALID_RUN_ID"),
            (
                json!({"op":"get_artifact","run_id":"bad","kind":"report"}),
                "INVALID_RUN_ID",
            ),
            (json!({"op":"get_recipe","id":"bad"}), "INVALID_RECIPE_ID"),
            (
                json!({"op":"add_version","id":"bad","body":{}}),
                "INVALID_RECIPE_ID",
            ),
            (
                json!({"op":"select_recipe","project_id":ID,"recipe_id":"bad"}),
                "INVALID_RECIPE_ID",
            ),
            (
                json!({"op":"deselect_recipe","project_id":ID,"recipe_id":"bad"}),
                "INVALID_RECIPE_ID",
            ),
            (
                json!({"op":"select_recipe","project_id":"bad","recipe_id":ID}),
                "INVALID_PROJECT_ID",
            ),
            (
                json!({"op":"deselect_recipe","project_id":"bad","recipe_id":ID}),
                "INVALID_PROJECT_ID",
            ),
            (
                json!({"op":"list_project_recipes","project_id":"bad"}),
                "INVALID_PROJECT_ID",
            ),
        ];
        for (value, code) in cases {
            assert_eq!(
                parse_request(value).err().map(|e| e.error),
                Some(code.into())
            );
        }
    }

    #[test]
    fn unknown_fields_ops_types_artifact_values_and_free_destinations_are_rejected() {
        for value in [
            json!({"op":"http","url":"http://outside/"}),
            json!({"op":"list_recipes","url":"http://outside/"}),
            json!({"op":"list_recipes","host":"outside"}),
            json!({"op":"list_recipes","port":123}),
            json!({"op":"list_recipes","path":"/other"}),
            json!({"op":"list_recipes","method":"DELETE"}),
            json!({"op":"get_run","id":7}),
            json!({"op":"create_recipe"}),
            json!({"op":"get_artifact","run_id":ID,"kind":"../report"}),
            json!({"op":"get_artifact","run_id":ID,"kind":"processed_cube"}),
            json!({"op":"get_artifact","run_id":ID,"kind":null}),
        ] {
            assert_eq!(
                parse_request(value).err().map(|e| e.error),
                Some("INVALID_REQUEST".into())
            );
        }
    }

    #[test]
    fn uuid_copy_and_port_boundary_preserve_closed_destination() -> TestResult {
        let original = include_str!("annotation.rs")
            .split("fn uuid(")
            .nth(1)
            .ok_or_else(|| io::Error::other("missing uuid"))?
            .split("\nfn invalid_request")
            .next()
            .ok_or_else(|| io::Error::other("missing uuid boundary"))?;
        let copied = include_str!("preprocess.rs")
            .split("fn uuid(")
            .nth(1)
            .ok_or_else(|| io::Error::other("missing copied uuid"))?
            .split("\nfn invalid_request")
            .next()
            .ok_or_else(|| io::Error::other("missing copied uuid boundary"))?;
        assert_eq!(copied, original);
        for id in [
            "../x",
            "http://outside/",
            "00000000-0000-0000-0000-00000000000g",
            "000000000000-0000-0000-000000000001",
        ] {
            assert!(parse_request(json!({"op":"get_run","id":id})).is_err());
        }
        assert!(
            parse_request(json!({"op":"list_recipes"}))?
                .destination(0)
                .is_err()
        );
        Ok(())
    }

    #[test]
    fn json_success_is_unchanged_and_post_body_is_forwarded() -> TestResult {
        let value = json!({"metrics":{"fisher":2.25},"status":"succeeded"});
        let body = serde_json::to_vec(&value)?;
        let (result, incoming) = exchange(
            json!({"op":"create_recipe","body":{"code":"x"}}),
            "200 OK",
            IDENTITY,
            body.clone(),
            Some(body.len() as u64),
        )?;
        assert_eq!(result?, value);
        assert!(incoming.starts_with("POST /api/v1/preprocess/recipes HTTP/1.1"));
        assert!(incoming.ends_with("{\"code\":\"x\"}"));
        Ok(())
    }

    #[test]
    fn binary_artifact_roundtrips_and_keeps_filename() -> TestResult {
        for length in [0, 1, 2, 3, 255, 256] {
            let body = (0..length).map(|i| i as u8).collect::<Vec<_>>();
            let (result, _) = exchange(
                json!({"op":"get_artifact","run_id":ID,"kind":"sample_spectra"}),
                "200 OK",
                &format!(
                    "{IDENTITY}Content-Type: application/octet-stream\r\nContent-Disposition: attachment; filename=\"sample_spectra.npz\"\r\n"
                ),
                body.clone(),
                Some(length as u64),
            )?;
            let value = result?;
            assert_eq!(value["filename"], "sample_spectra.npz");
            assert_eq!(value["content_type"], "application/octet-stream");
            let encoded = value["body_base64"]
                .as_str()
                .ok_or_else(|| io::Error::other("missing base64"))?;
            assert_eq!(decode_base64(encoded)?, body);
        }
        Ok(())
    }

    #[test]
    fn manual_base64_matches_rfc4648_vectors() {
        for (plain, encoded) in [
            ("", ""),
            ("f", "Zg=="),
            ("fo", "Zm8="),
            ("foo", "Zm9v"),
            ("foob", "Zm9vYg=="),
            ("fooba", "Zm9vYmE="),
            ("foobar", "Zm9vYmFy"),
        ] {
            assert_eq!(base64(plain.as_bytes()), encoded);
        }
    }

    #[test]
    fn only_204_maps_empty_body_to_null_not_200() -> TestResult {
        let request = json!({"op":"deselect_recipe","project_id":ID,"recipe_id":OTHER});
        let (value, incoming) =
            exchange(request.clone(), "204 No Content", IDENTITY, vec![], Some(0))?;
        assert_eq!(value?, Value::Null);
        assert!(incoming.starts_with(&format!(
            "DELETE /api/v1/preprocess/projects/{ID}/recipes/{OTHER} HTTP/1.1"
        )));
        assert_eq!(
            exchange(request, "200 OK", IDENTITY, vec![], Some(0))?
                .0
                .err()
                .map(|e| e.error),
            Some("INVALID_BODY".into())
        );
        Ok(())
    }

    #[test]
    fn report_stays_json_and_nonartifact_binary_is_rejected() -> TestResult {
        let value = exchange(
            json!({"op":"get_artifact","run_id":ID,"kind":"report"}),
            "200 OK",
            &format!("{IDENTITY}Content-Type: application/json\r\n"),
            b"{\"ok\":true}".to_vec(),
            Some(11),
        )?
        .0?;
        assert_eq!(value, json!({"ok":true}));
        let result = exchange(
            json!({"op":"list_recipes"}),
            "200 OK",
            &format!("{IDENTITY}Content-Type: application/octet-stream\r\n"),
            vec![255],
            Some(1),
        )?
        .0;
        assert_eq!(result.err().map(|e| e.error), Some("INVALID_BODY".into()));
        Ok(())
    }

    #[test]
    fn identity_checks_precede_http_status_and_body() -> TestResult {
        for headers in [
            "",
            "X-SpectrumAgent-Boot-Id: deadbeef\r\nX-SpectrumAgent-Pid: 123\r\n",
            "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 9\r\n",
        ] {
            let result = exchange(
                json!({"op":"list_recipes"}),
                "500 Error",
                headers,
                b"x".to_vec(),
                Some(1),
            )?
            .0;
            assert_eq!(
                result.err().map(|e| e.error),
                Some("DATASET_IDENTITY_MISMATCH".into())
            );
        }
        assert_eq!(
            exchange(
                json!({"op":"list_recipes"}),
                "200 OK",
                IDENTITY,
                b"[]".to_vec(),
                Some(2)
            )?
            .0?,
            json!([])
        );
        Ok(())
    }

    #[test]
    fn declared_and_streaming_limits_reject_above_eight_mib() -> TestResult {
        for length in [Some(MAX_RESPONSE_BYTES + 1), None] {
            let body = if length.is_none() {
                vec![b' '; (MAX_RESPONSE_BYTES + 1) as usize]
            } else {
                vec![]
            };
            let result = exchange(
                json!({"op":"list_recipes"}),
                "200 OK",
                IDENTITY,
                body,
                length,
            )?
            .0;
            assert_eq!(
                result.err().map(|e| e.error),
                Some("RESPONSE_TOO_LARGE".into())
            );
        }
        Ok(())
    }

    #[test]
    fn raw_and_canonical_tokens_never_cross_bridge() -> TestResult {
        let escaped = format!(
            "\"{}\"",
            TOKEN
                .chars()
                .map(|c| format!("\\u{:04x}", c as u32))
                .collect::<String>()
        );
        for body in [format!("\"{TOKEN}\"").into_bytes(), escaped.into_bytes()] {
            let size = body.len() as u64;
            let result = exchange(
                json!({"op":"list_recipes"}),
                "200 OK",
                IDENTITY,
                body,
                Some(size),
            )?
            .0;
            let error = result
                .err()
                .ok_or_else(|| io::Error::other("missing sensitive rejection"))?;
            assert_eq!(error.error, "SENSITIVE_RESPONSE");
            assert!(!serde_json::to_string(&error)?.contains(TOKEN));
        }
        Ok(())
    }

    #[test]
    fn binary_payload_and_wrapper_filename_are_also_sensitive_checked() -> TestResult {
        let request = json!({"op":"get_artifact","run_id":ID,"kind":"sample_spectra"});
        let headers = format!("{IDENTITY}Content-Type: application/octet-stream\r\n");
        assert_eq!(
            exchange(
                request.clone(),
                "200 OK",
                &headers,
                TOKEN.as_bytes().to_vec(),
                Some(32)
            )?
            .0
            .err()
            .map(|e| e.error),
            Some("SENSITIVE_RESPONSE".into())
        );
        let headers = format!("{headers}Content-Disposition: attachment; filename=\"{TOKEN}\"\r\n");
        assert_eq!(
            exchange(request, "200 OK", &headers, b"npz".to_vec(), Some(3))?
                .0
                .err()
                .map(|e| e.error),
            Some("SENSITIVE_RESPONSE".into())
        );
        Ok(())
    }

    #[test]
    fn structured_http_error_preserves_three_fields() -> TestResult {
        let body = br#"{"error":"INVALID_OPERATOR_PARAMS","detail":"bad","context":{"field":"x"}}"#
            .to_vec();
        let result = exchange(
            json!({"op":"list_recipes"}),
            "400 Bad Request",
            IDENTITY,
            body.clone(),
            Some(body.len() as u64),
        )?
        .0;
        let error = result
            .err()
            .ok_or_else(|| io::Error::other("missing error"))?;
        assert_eq!(error.error, "INVALID_OPERATOR_PARAMS");
        assert_eq!(error.detail, "bad");
        assert_eq!(error.context, json!({"field":"x"}));
        Ok(())
    }

    #[test]
    fn malformed_http_envelope_uses_generic_error() -> TestResult {
        let result = exchange(
            json!({"op":"list_recipes"}),
            "500 Error",
            IDENTITY,
            b"{}".to_vec(),
            Some(2),
        )?
        .0;
        assert_eq!(result.err().map(|e| e.error), Some("HTTP_ERROR".into()));
        Ok(())
    }

    #[test]
    fn redirects_are_not_followed() -> TestResult {
        let result = exchange(
            json!({"op":"list_recipes"}),
            "307 Redirect",
            &format!("{IDENTITY}Location: http://127.0.0.1:1/forbidden\r\n"),
            b"{}".to_vec(),
            Some(2),
        )?
        .0;
        assert_eq!(result.err().map(|e| e.error), Some("HTTP_ERROR".into()));
        Ok(())
    }

    #[test]
    fn actual_generation_guard_used_by_command_rejects_stale_or_nonready() -> TestResult {
        let mut current = Snapshot {
            generation_id: 7,
            phase: Phase::Ready,
            pid: None,
            port: None,
            boot_id: None,
            failure: None,
            cleanup_complete: true,
            pending_activation: false,
        };
        validate_generation(7, &current)?;
        current.generation_id = 8;
        assert_eq!(
            validate_generation(7, &current).err().map(|e| e.error),
            Some("STALE_RESPONSE".into())
        );
        current.generation_id = 7;
        current.phase = Phase::Stopping;
        assert_eq!(
            validate_generation(7, &current).err().map(|e| e.error),
            Some("STALE_RESPONSE".into())
        );
        assert!(include_str!("main.rs").contains("validate_generation(generation, &current)?;"));
        Ok(())
    }

    #[test]
    fn builder_sets_three_hundred_seconds_without_waiting() -> TestResult {
        // reqwest blocking ClientBuilder has no timeout getter (Debug omits it).
        // Check the exact builder passed to forward, then actually build it.
        let source = include_str!("preprocess.rs")
            .split("fn client_builder()")
            .nth(1)
            .ok_or_else(|| io::Error::other("missing client builder"))?
            .split("\nfn reject_sensitive")
            .next()
            .ok_or_else(|| io::Error::other("missing client builder boundary"))?;
        assert!(source.contains(".timeout(Duration::from_secs(300))"));
        assert!(source.contains(".connect_timeout(Duration::from_millis(500))"));
        assert!(source.contains(".no_proxy()"));
        assert!(source.contains(".redirect(reqwest::redirect::Policy::none())"));
        let _client = client_builder().build()?;
        Ok(())
    }
}
