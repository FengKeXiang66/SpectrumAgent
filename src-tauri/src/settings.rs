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
        SettingsRequest::PutKey { key } => vec![key.as_str()],
        _ => vec![],
    };
    forward_http(identity, url, method, body, false, &secrets)
}
