//! Typed dataset requests for debug and release; never a caller-controlled HTTP proxy.
use crate::handshake::Handshake;
use reqwest::{Method, Url, blocking::Client};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{io::Read, time::Duration};

pub const MAX_RESPONSE_BYTES: u64 = 8 * 1024 * 1024;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ForwardError {
    pub error: String,
    pub detail: String,
    pub context: Value,
}

impl ForwardError {
    pub fn new(code: &str, detail: &str) -> Self {
        Self {
            error: code.into(),
            detail: detail.into(),
            context: json!({}),
        }
    }
}
impl std::fmt::Display for ForwardError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.error, self.detail)
    }
}
impl std::error::Error for ForwardError {}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Region {
    pub l0: u32,
    pub l1: u32,
    pub s0: u32,
    pub s1: u32,
    pub raw: Option<bool>,
}

impl Region {
    fn body(&self) -> Value {
        json!({"l0":self.l0,"l1":self.l1,"s0":self.s0,"s1":self.s1,"raw":self.raw})
    }
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum DatasetRequest {
    Import {
        path: String,
        #[serde(default)]
        raw: bool,
        data_path: Option<String>,
    },
    Get {
        id: String,
    },
    Preview {
        id: String,
        band: u32,
    },
    Band {
        id: String,
        band: u32,
        region: Region,
    },
    Region {
        id: String,
        region: Region,
    },
}

fn dataset_id(id: &str) -> Result<&str, ForwardError> {
    if id.len() != 36
        || !id.bytes().enumerate().all(|(i, c)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                c == b'-'
            } else {
                c.is_ascii_digit() || (b'a'..=b'f').contains(&c)
            }
        })
    {
        return Err(ForwardError::new(
            "INVALID_DATASET_ID",
            "数据集ID必须为规范UUID",
        ));
    }
    Ok(id)
}

impl DatasetRequest {
    fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        let (path, method, body, band) = match self {
            Self::Import {
                path,
                raw,
                data_path,
            } => (
                "/api/v1/datasets/import".to_owned(),
                Method::POST,
                Some(json!({"path":path,"raw":raw,"data_path":data_path})),
                None,
            ),
            Self::Get { id } => (
                format!("/api/v1/datasets/{}", dataset_id(id)?),
                Method::GET,
                None,
                None,
            ),
            Self::Preview { id, band } => (
                format!("/api/v1/datasets/{}/preview", dataset_id(id)?),
                Method::GET,
                None,
                Some(*band),
            ),
            Self::Band { id, band, region } => (
                format!("/api/v1/datasets/{}/band/{band}", dataset_id(id)?),
                Method::POST,
                Some(region.body()),
                None,
            ),
            Self::Region { id, region } => (
                format!("/api/v1/datasets/{}/region", dataset_id(id)?),
                Method::POST,
                Some(region.body()),
                None,
            ),
        };
        let mut url = Url::parse("http://127.0.0.1/")
            .map_err(|_| ForwardError::new("TRANSPORT", "本机地址构造失败"))?;
        if port == 0 || url.set_port(Some(port)).is_err() {
            return Err(ForwardError::new("TRANSPORT", "握手端口非法"));
        }
        url.set_path(&path);
        if let Some(band) = band {
            url.query_pairs_mut().append_pair("band", &band.to_string());
        }
        Ok((url, method, body))
    }
}

pub fn forward(identity: &Handshake, request: &DatasetRequest) -> Result<Value, ForwardError> {
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
                "GET /api/v1/datasets/00000000-0000-0000-0000-000000000001/preview?band=0 HTTP/1.1"
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
            &DatasetRequest::Preview {
                id: "00000000-0000-0000-0000-000000000001".into(),
                band: 0,
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

    #[test]
    fn no_generic_host_port_path_or_method_can_be_deserialized() {
        for value in [
            json!({"op":"proxy","url":"https://example.com/"}),
            json!({"op":"import","path":"C:/data","url":"http://127.0.0.1/other"}),
            json!({"op":"get","id":"../../health"}),
            json!({"op":"get","id":"http://example.com/"}),
        ] {
            if let Ok(request) = serde_json::from_value::<DatasetRequest>(value) {
                assert!(request.destination(1234).is_err());
            }
        }
    }

    #[test]
    fn all_operations_use_the_handshake_port_and_fixed_namespace() -> Result<(), ForwardError> {
        let id = "00000000-0000-0000-0000-000000000001";
        for request in [
            json!({"op":"import","path":"C:/data"}),
            json!({"op":"get","id":id}),
            json!({"op":"preview","id":id,"band":0}),
            json!({"op":"band","id":id,"band":1,"region":{"l0":0,"l1":1,"s0":0,"s1":1}}),
            json!({"op":"region","id":id,"region":{"l0":0,"l1":1,"s0":0,"s1":1}}),
        ] {
            let request: DatasetRequest = serde_json::from_value(request)
                .map_err(|_| ForwardError::new("TEST", "请求解析失败"))?;
            let (url, method, _) = request.destination(4321)?;
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(4321));
            assert!(url.path().starts_with("/api/v1/datasets/"));
            assert!(method == Method::GET || method == Method::POST);
        }
        Ok(())
    }
}
