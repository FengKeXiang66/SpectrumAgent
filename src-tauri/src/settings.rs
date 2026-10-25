//! TASK-07: only the three existing LLM settings operations, no secret logging.
pub use crate::agent::{ForwardError, validate_generation};
use crate::{
    agent::{fixed_url, forward_http, invalid_request},
    handshake::Handshake,
};
use reqwest::{Method, Url};
use serde::Deserialize;
use serde_json::{Value, json};

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum SettingsRequest {
    GetLlm {},
    PutLlm { body: Value },
    PutKey { key: String },
}

pub fn parse_request(value: Value) -> Result<SettingsRequest, ForwardError> {
    let request: SettingsRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl SettingsRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        if let Self::PutLlm { body } = self {
            let fields = body.as_object().ok_or_else(invalid_request)?;
            for (key, value) in fields {
                let valid = match key.as_str() {
                    "base_url" | "model" => value.is_string(),
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
            Self::GetLlm {} => ("/api/v1/settings/llm", Method::GET, None),
            Self::PutLlm { body } => ("/api/v1/settings/llm", Method::PUT, Some(body.clone())),
            Self::PutKey { key } => (
                "/api/v1/settings/llm/key",
                Method::PUT,
                Some(json!({"key":key})),
            ),
        };
        Ok((fixed_url(port, path)?, method, body))
    }
}

pub fn forward(identity: &Handshake, request: &SettingsRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    let secrets = match request {
        SettingsRequest::PutKey { key } => vec![key.as_str()],
        _ => vec![],
    };
    forward_http(identity, url, method, body, false, &secrets)
}
