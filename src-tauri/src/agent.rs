//! TASK-07 R11/R12: three fixed operations; collect bounded SSE before IPC.
use crate::{handshake::Handshake, state::Phase, supervisor::Snapshot};
use reqwest::{Method, Url, blocking::Client};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{io::Read, time::Duration};

pub const MAX_RESPONSE_BYTES: u64 = crate::annotation::MAX_RESPONSE_BYTES;

#[derive(Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ForwardError {
    pub error: String,
    pub detail: String,
    pub context: Value,
    // Preserve preflight HTTP status alongside the original error envelope.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub status_code: Option<u16>,
}

impl ForwardError {
    pub fn new(code: &str, detail: &str) -> Self {
        Self {
            error: code.into(),
            detail: detail.into(),
            context: json!({}),
            status_code: None,
        }
    }
}
impl std::fmt::Display for ForwardError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}: {}", self.error, self.detail)
    }
}
impl std::error::Error for ForwardError {}

pub(crate) fn invalid_request() -> ForwardError {
    // No serde diagnostics, body, URL, credential or caller input in errors.
    ForwardError::new("INVALID_REQUEST", "请求字段、类型或取值非法")
}

pub(crate) fn uuid(value: &str) -> Result<(), ForwardError> {
    if value.len() != 36
        || !value.bytes().enumerate().all(|(i, c)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                c == b'-'
            } else {
                c.is_ascii_hexdigit()
            }
        })
    {
        return Err(invalid_request());
    }
    Ok(())
}

#[derive(Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Decision {
    Approve,
    Reject,
}

#[derive(Deserialize, Serialize)]
#[serde(untagged, deny_unknown_fields)]
pub enum MessageBody {
    Content {
        content: String,
    },
    Answer {
        check_id: String,
        decision: Decision,
    },
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum AgentRequest {
    CreateSession {},
    SendMessage { id: String, body: MessageBody },
    GetSteps { id: String },
}

pub fn parse_request(value: Value) -> Result<AgentRequest, ForwardError> {
    let request: AgentRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl AgentRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        match self {
            Self::CreateSession {} => Ok(()),
            Self::GetSteps { id } => uuid(id),
            Self::SendMessage { id, body } => {
                uuid(id)?;
                match body {
                    MessageBody::Content { content } if content.trim().is_empty() => {
                        Err(invalid_request())
                    }
                    MessageBody::Answer { check_id, .. } => uuid(check_id),
                    _ => Ok(()),
                }
            }
        }
    }

    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (path, method, body) = match self {
            Self::CreateSession {} => (
                "/api/v1/agent/sessions".into(),
                Method::POST,
                Some(json!({})),
            ),
            Self::GetSteps { id } => (
                format!("/api/v1/agent/sessions/{id}/steps"),
                Method::GET,
                None,
            ),
            Self::SendMessage { id, body } => (
                format!("/api/v1/agent/sessions/{id}/messages"),
                Method::POST,
                Some(serde_json::to_value(body).map_err(|_| invalid_request())?),
            ),
        };
        Ok((fixed_url(port, &path)?, method, body))
    }
}

pub(crate) fn fixed_url(port: u16, path: &str) -> Result<Url, ForwardError> {
    let mut url = Url::parse("http://127.0.0.1/")
        .map_err(|_| ForwardError::new("TRANSPORT", "本机地址构造失败"))?;
    if port == 0 || url.set_port(Some(port)).is_err() {
        return Err(ForwardError::new("TRANSPORT", "握手端口非法"));
    }
    url.set_path(path);
    Ok(url)
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

pub fn parse_sse(text: &str) -> Result<Value, ForwardError> {
    fn flush(
        events: &mut Vec<Value>,
        event: &mut Option<String>,
        data: &mut Vec<String>,
    ) -> Result<(), ForwardError> {
        if data.is_empty() {
            *event = None;
            return Ok(());
        }
        let name = event
            .take()
            .ok_or_else(|| ForwardError::new("INVALID_BODY", "SSE 事件缺少类型"))?;
        if !matches!(
            name.as_str(),
            "step" | "clarify" | "human_check" | "done" | "error"
        ) {
            return Err(ForwardError::new("INVALID_BODY", "SSE 事件类型非法"));
        }
        let value: Value = serde_json::from_str(&data.join("\n"))
            .map_err(|_| ForwardError::new("INVALID_BODY", "SSE 数据不是有效JSON"))?;
        if !value.is_object() {
            return Err(ForwardError::new("INVALID_BODY", "SSE 数据必须为对象"));
        }
        events.push(json!({"event":name,"data":value}));
        data.clear();
        Ok(())
    }
    let (mut events, mut event, mut data) = (Vec::new(), None, Vec::new());
    for line in text.split('\n') {
        let line = line.strip_suffix('\r').unwrap_or(line);
        if line.is_empty() {
            flush(&mut events, &mut event, &mut data)?;
            continue;
        }
        if let Some((field, value)) = line.split_once(':') {
            let value = value.strip_prefix(' ').unwrap_or(value);
            match field {
                "event" => event = Some(value.to_owned()),
                "data" => data.push(value.to_owned()),
                _ => {}
            }
        }
    }
    flush(&mut events, &mut event, &mut data)?;
    Ok(json!({"events":events}))
}

fn reject_sensitive(bytes: &[u8], secrets: &[&str]) -> Result<(), ForwardError> {
    if secrets.iter().any(|secret| {
        !secret.is_empty()
            && bytes
                .windows(secret.len())
                .any(|part| part == secret.as_bytes())
    }) {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "响应包含敏感信息，已拒绝转发",
        ));
    }
    Ok(())
}

// Shared only by the two fixed domain forwarders, never exposed as an IPC proxy.
pub(crate) fn forward_http(
    identity: &Handshake,
    url: Url,
    method: Method,
    body: Option<Value>,
    sse: bool,
    secrets: &[&str],
) -> Result<Value, ForwardError> {
    let client = Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        // Reuse #05's bounded long-running operation timeout.
        .timeout(Duration::from_secs(300))
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
    // Identity MUST precede status, limits and body parsing, even on errors.
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
    if sse
        && status.is_success()
        && !header("Content-Type").is_some_and(|v| v.split(';').next() == Some("text/event-stream"))
    {
        return Err(ForwardError::new("INVALID_BODY", "响应不是SSE流"));
    }
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| ForwardError::new("TRANSPORT", "读取响应失败"))?;
    if bytes.len() as u64 > MAX_RESPONSE_BYTES {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
    }
    let secrets: Vec<&str> = std::iter::once(identity.token())
        .chain(secrets.iter().copied())
        .collect();
    reject_sensitive(&bytes, &secrets)?;
    let value = if sse && status.is_success() {
        parse_sse(
            std::str::from_utf8(&bytes)
                .map_err(|_| ForwardError::new("INVALID_BODY", "SSE 编码非法"))?,
        )?
    } else {
        serde_json::from_slice(&bytes)
            .map_err(|_| ForwardError::new("INVALID_BODY", "响应不是有效JSON"))?
    };
    reject_sensitive(
        &serde_json::to_vec(&value)
            .map_err(|_| ForwardError::new("INVALID_BODY", "响应无法序列化"))?,
        &secrets,
    )?;
    if !status.is_success() {
        let mut error = serde_json::from_value::<ForwardError>(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "数据引擎返回错误"));
        error.status_code = Some(status.as_u16());
        return Err(error);
    }
    Ok(value)
}

pub fn forward(identity: &Handshake, request: &AgentRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    forward_http(
        identity,
        url,
        method,
        body,
        matches!(request, AgentRequest::SendMessage { .. }),
        &[],
    )
}
