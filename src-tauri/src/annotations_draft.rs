//! TASK-07 12.6: five fixed draft/export routes. Legacy annotation stays frozen.
pub use crate::agent::{ForwardError, MAX_RESPONSE_BYTES, validate_generation};
use crate::{
    agent::{fixed_url, forward_http, invalid_request, uuid},
    handshake::Handshake,
};
use reqwest::{Method, Url, blocking::Client};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{io::Read, time::Duration};

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum DraftRequest {
    GetDraft {
        cube_id: String,
    },
    AddRegion {
        cube_id: String,
        body: Value,
    },
    PatchRegion {
        cube_id: String,
        region_id: String,
        body: Value,
    },
    Confirm {
        cube_id: String,
        body: Value,
    },
    TrainingMat {
        cube_id: String,
        version_id: String,
    },
}

pub fn parse_request(value: Value) -> Result<DraftRequest, ForwardError> {
    let request: DraftRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl DraftRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        let cube_id = match self {
            Self::GetDraft { cube_id }
            | Self::AddRegion { cube_id, .. }
            | Self::PatchRegion { cube_id, .. }
            | Self::Confirm { cube_id, .. }
            | Self::TrainingMat { cube_id, .. } => cube_id,
        };
        uuid(cube_id)?;
        match self {
            Self::TrainingMat { version_id, .. } => uuid(version_id)?,
            Self::PatchRegion { region_id, .. }
                if !region_id
                    .strip_prefix("r-")
                    .is_some_and(|id| id.len() >= 4 && id.bytes().all(|c| c.is_ascii_digit())) =>
            {
                return Err(invalid_request());
            }
            _ => {}
        }
        if let Self::AddRegion { body, .. }
        | Self::PatchRegion { body, .. }
        | Self::Confirm { body, .. } = self
            && !body.is_object()
        {
            return Err(invalid_request());
        }
        Ok(())
    }

    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (path, method, body) = match self {
            Self::GetDraft { cube_id } => (
                format!("/api/v1/annotations/{cube_id}/draft"),
                Method::GET,
                None,
            ),
            Self::AddRegion { cube_id, body } => (
                format!("/api/v1/annotations/{cube_id}/draft/regions"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::PatchRegion {
                cube_id,
                region_id,
                body,
            } => (
                format!("/api/v1/annotations/{cube_id}/draft/regions/{region_id}"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::Confirm { cube_id, body } => (
                format!("/api/v1/annotations/{cube_id}/draft/confirm"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::TrainingMat {
                cube_id,
                version_id,
            } => (
                format!("/api/v1/annotations/{cube_id}/versions/{version_id}/training-mat"),
                Method::GET,
                None,
            ),
        };
        Ok((fixed_url(port, &path)?, method, body))
    }
}

fn sensitive(bytes: &[u8], identity: &Handshake) -> Result<(), ForwardError> {
    if bytes
        .windows(identity.token().len())
        .any(|part| part == identity.token().as_bytes())
    {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "响应包含敏感信息，已拒绝转发",
        ));
    }
    Ok(())
}

pub fn forward(identity: &Handshake, request: &DraftRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    if !matches!(request, DraftRequest::TrainingMat { .. }) {
        return forward_http(identity, url, method, body, false, &[]);
    }
    // Binary download uses the identical identity-first and dual 8MiB limits.
    let client = Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(300))
        .build()
        .map_err(|_| ForwardError::new("TRANSPORT", "本机请求初始化失败"))?;
    let response = client
        .get(url)
        .bearer_auth(identity.token())
        .send()
        .map_err(|_| ForwardError::new("TRANSPORT", "数据引擎请求失败或超时"))?;
    let header = |key| response.headers().get(key).and_then(|v| v.to_str().ok());
    if header("X-SpectrumAgent-Boot-Id") != Some(identity.boot_id.as_str())
        || header("X-SpectrumAgent-Pid") != Some(identity.pid.to_string().as_str())
    {
        return Err(ForwardError::new(
            "DATASET_IDENTITY_MISMATCH",
            "响应与本代引擎身份不匹配",
        ));
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_RESPONSE_BYTES)
    {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
    }
    let status = response.status();
    if status.is_success() && header("Content-Type") != Some("application/octet-stream") {
        return Err(ForwardError::new("INVALID_BODY", "响应不是训练MAT"));
    }
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ForwardError::new("TRANSPORT", "读取响应失败"))?;
    if bytes.len() as u64 > MAX_RESPONSE_BYTES {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
    }
    sensitive(&bytes, identity)?;
    if !status.is_success() {
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|_| ForwardError::new("INVALID_BODY", "响应不是有效JSON"))?;
        sensitive(
            &serde_json::to_vec(&value).map_err(|_| invalid_request())?,
            identity,
        )?;
        let mut error = serde_json::from_value::<ForwardError>(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "数据引擎返回错误"));
        error.status_code = Some(status.as_u16());
        return Err(error);
    }
    let value = json!({"content_type":"application/octet-stream","filename":"training_mat.mat","body_base64":base64(&bytes)});
    sensitive(
        &serde_json::to_vec(&value).map_err(|_| invalid_request())?,
        identity,
    )?;
    Ok(value)
}

// Same dependency-free encoding as #05's artifact forwarder.
fn base64(bytes: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let a = chunk[0];
        let b = chunk.get(1).copied().unwrap_or(0);
        let c = chunk.get(2).copied().unwrap_or(0);
        output.push(ALPHABET[(a >> 2) as usize] as char);
        output.push(ALPHABET[(((a & 3) << 4) | (b >> 4)) as usize] as char);
        output.push(if chunk.len() > 1 {
            ALPHABET[(((b & 15) << 2) | (c >> 6)) as usize] as char
        } else {
            '='
        });
        output.push(if chunk.len() > 2 {
            ALPHABET[(c & 63) as usize] as char
        } else {
            '='
        });
    }
    output
}
