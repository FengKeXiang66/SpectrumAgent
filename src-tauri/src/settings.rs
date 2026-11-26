//! Fixed LLM settings and TASK-25 project path defaults, no secret logging.
pub use crate::agent::{ForwardError, validate_generation};
use crate::{
    agent::{fixed_url, forward_http, forward_http_scoped, invalid_request, uuid},
    handshake::Handshake,
};
use reqwest::{Method, Url};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum SettingsRequest {
    GetLlm {},
    PutLlm {
        body: Value,
    },
    PutKey {
        key: String,
    },
    PutRouterKey {
        key: String,
    },
    VerifyLlm {},
    VerifyRouterLlm {},
    GetProjectPaths {
        project_id: String,
    },
    PutProjectPaths {
        project_id: String,
        body: ProjectPathsBody,
    },
}

#[derive(Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct ProjectPathsBody {
    source_path: String,
    output_root: String,
}

pub fn parse_request(value: Value) -> Result<SettingsRequest, ForwardError> {
    let request: SettingsRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl SettingsRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        if let Self::GetProjectPaths { project_id } | Self::PutProjectPaths { project_id, .. } =
            self
        {
            uuid(project_id)?;
        }
        if let Self::PutLlm { body } = self {
            let fields = body.as_object().ok_or_else(invalid_request)?;
            for (key, value) in fields {
                let valid = match key.as_str() {
                    "base_url" | "model" | "router_model" | "router_base_url" => value.is_string(),
                    "egress_enabled" => value.is_boolean(),
                    "temperature" | "max_tokens" | "timeout_ms" => {
                        value.is_string() || value.is_number()
                    }
                    _ => false,
                };
                if !valid {
                    return Err(invalid_request());
                }
            }
        }
        Ok(())
    }

    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (path, method, body) = match self {
            Self::GetLlm {} => ("/api/v1/settings/llm".into(), Method::GET, None),
            Self::PutLlm { body } => (
                "/api/v1/settings/llm".into(),
                Method::PUT,
                Some(body.clone()),
            ),
            Self::PutKey { key } => (
                "/api/v1/settings/llm/key".into(),
                Method::PUT,
                Some(json!({"key":key})),
            ),
            Self::PutRouterKey { key } => (
                "/api/v1/settings/llm/router-key".into(),
                Method::PUT,
                Some(json!({"key":key})),
            ),
            Self::VerifyLlm {} => (
                "/api/v1/settings/llm/verify".into(),
                Method::POST,
                None,
            ),
            Self::VerifyRouterLlm {} => (
                "/api/v1/settings/llm/verify-router".into(),
                Method::POST,
                None,
            ),
            Self::GetProjectPaths { project_id } => (
                format!(
                    "/api/v1/settings/projects/{}/paths",
                    project_id.to_ascii_lowercase()
                ),
                Method::GET,
                None,
            ),
            Self::PutProjectPaths { project_id, body } => (
                format!(
                    "/api/v1/settings/projects/{}/paths",
                    project_id.to_ascii_lowercase()
                ),
                Method::PUT,
                Some(serde_json::to_value(body).map_err(|_| invalid_request())?),
            ),
        };
        Ok((fixed_url(port, &path)?, method, body))
    }
}

pub fn forward(identity: &Handshake, request: &SettingsRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    if let SettingsRequest::PutProjectPaths { body: fields, .. } = request {
        let paths: Vec<&str> = [fields.source_path.as_str(), fields.output_root.as_str()]
            .into_iter()
            .filter(|value| !value.is_empty())
            .collect();
        return forward_http_scoped(identity, url, method, body, false, (&[], &paths));
    }
    let secrets = match request {
        SettingsRequest::PutKey { key } | SettingsRequest::PutRouterKey { key } => vec![key.as_str()],
        _ => vec![],
    };
    forward_http(identity, url, method, body, false, &secrets)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn router_settings_use_fixed_routes_and_only_accept_known_fields() {
        let body = json!({"router_base_url":"https://route.example.test/v1","router_model":"small"});
        let put = parse_request(json!({"op":"put_llm","body":body})).unwrap();
        let (url, method, sent) = put.destination(15555).unwrap();
        assert_eq!(url.path(), "/api/v1/settings/llm");
        assert_eq!(method, Method::PUT);
        assert_eq!(sent, Some(body));
        for value in [
            json!({"op":"put_llm","body":{"router_base_url":42}}),
            json!({"op":"put_llm","body":{"router_api_key":"denied"}}),
            json!({"op":"put_router_key","key":"test","url":"https://outside.test"}),
            json!({"op":"verify_router_llm","body":{"router_base_url":"https://outside.test"}}),
        ] {
            assert!(parse_request(value).is_err());
        }
        for (input, path, verb, body) in [
            (json!({"op":"put_router_key","key":""}), "/api/v1/settings/llm/router-key",
                Method::PUT, Some(json!({"key":""}))),
            (json!({"op":"verify_router_llm"}), "/api/v1/settings/llm/verify-router", Method::POST, None),
        ] {
            let (url, method, sent) = parse_request(input).unwrap().destination(15555).unwrap();
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.path(), path);
            assert_eq!(method, verb);
            assert_eq!(sent, body);
        }
    }

    #[test]
    fn router_key_is_rejected_if_echoed_in_error_response() {
        use std::{io::{BufRead, BufReader, Read, Write}, net::TcpListener, thread, time::Duration};
        const KEY: &str = "synthetic-router-credential";
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,"token":"0123456789abcdef0123456789abcdef",
            "protocol":1,"version":"0.1.0","process_created_at":"2026-11-26T00:00:00.000Z",
            "started_at":"2026-11-26T00:00:00.000Z"
        })).unwrap()).unwrap();
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket.set_read_timeout(Some(Duration::from_secs(3))).unwrap();
            let mut reader = BufReader::new(&mut socket);
            let mut length = 0;
            loop {
                let mut line = String::new();
                assert!(reader.read_line(&mut line).unwrap() > 0);
                if line == "\r\n" { break; }
                if let Some((key, value)) = line.split_once(':')
                    && key.eq_ignore_ascii_case("content-length")
                {
                    length = value.trim().parse().unwrap();
                }
            }
            let mut request = vec![0; length];
            reader.read_exact(&mut request).unwrap();
            assert_eq!(serde_json::from_slice::<Value>(&request).unwrap(), json!({"key":KEY}));
            let body = json!({"error":"FAILED","detail":KEY,"context":{}}).to_string();
            write!(socket, "HTTP/1.1 400 Bad Request\r\nX-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", body.len(), body).unwrap();
        });
        let request = parse_request(json!({"op":"put_router_key","key":KEY})).unwrap();
        let error = forward(&identity, &request).unwrap_err();
        server.join().unwrap();
        assert_eq!(error.error, "SENSITIVE_RESPONSE");
        assert!(!serde_json::to_string(&error).unwrap().contains(KEY));
    }
}
