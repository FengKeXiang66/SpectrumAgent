//! TASK-07 R11/R12: three fixed operations; collect bounded SSE before IPC.
use crate::{handshake::Handshake, state::Phase, supervisor::Snapshot};
use reqwest::{Method, Url, blocking::Client};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{io::{BufRead, BufReader, Read}, time::Duration};

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
#[serde(rename_all = "snake_case")]
pub enum PlanAction {
    Approve,
    Reject,
    Skip,
    Rollback,
}

fn present_value<'de, D, T>(deserializer: D) -> Result<Option<T>, D::Error>
where
    D: serde::Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(deserializer).map(Some)
}

#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WorkspaceContext {
    #[serde(
        default,
        deserialize_with = "present_value",
        skip_serializing_if = "Option::is_none"
    )]
    cube_id: Option<String>,
    #[serde(
        default,
        deserialize_with = "present_value",
        skip_serializing_if = "Option::is_none"
    )]
    gesture_ref: Option<String>,
}

fn gesture_reference(value: &str) -> bool {
    value.len() == 34
        && value.starts_with("g-")
        && value
            .bytes()
            .skip(2)
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

impl WorkspaceContext {
    fn validate(&self) -> Result<(), ForwardError> {
        if let Some(cube) = &self.cube_id {
            uuid(cube)?;
        }
        if self
            .gesture_ref
            .as_ref()
            .is_some_and(|value| self.cube_id.is_none() || !gesture_reference(value))
        {
            return Err(invalid_request());
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize)]
#[serde(untagged, deny_unknown_fields)]
pub enum MessageBody {
    Content {
        #[serde(default, skip_serializing_if = "Option::is_none")]
        request_id: Option<String>,
        content: String,
        #[serde(
            default,
            deserialize_with = "present_value",
            skip_serializing_if = "Option::is_none"
        )]
        workspace: Option<WorkspaceContext>,
    },
    Answer {
        #[serde(default, skip_serializing_if = "Option::is_none")]
        request_id: Option<String>,
        check_id: String,
        decision: Decision,
    },
    Plan {
        #[serde(default, skip_serializing_if = "Option::is_none")]
        request_id: Option<String>,
        plan_id: String,
        action: PlanAction,
        #[serde(
            default,
            deserialize_with = "present_value",
            skip_serializing_if = "Option::is_none"
        )]
        step_ref: Option<u64>,
        #[serde(
            default,
            deserialize_with = "present_value",
            skip_serializing_if = "Option::is_none"
        )]
        reason: Option<String>,
    },
}

#[derive(Deserialize, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum SessionScope {
    Global {},
    DatasetVersion { dataset_version_id: String },
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields)]
pub struct SessionQuery {
    pub kind: Option<String>,
    pub dataset_version_id: Option<String>,
    pub limit: Option<u32>,
    pub cursor: Option<String>,
}
#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum AgentRequest {
    InferenceHistory { id: String, model_id: String },
    InferenceTask { id: String, model_id: String, run_id: String, action: String },
    InferencePlot { id: String, model_id: String, run_id: String, file_index: u32, kind: Option<String> },
    InferenceExport { id: String, model_id: String, run_id: String, destination: String },
    ExperimentHistory { id: String, offset: Option<u32>, limit: Option<u32> },
    SelectExperiment { id: String, experiment_id: String },
    CompareExperiments { id: String, first_id: String, second_id: String },
    ArchivedExperimentResult { id: String, experiment_id: String },
    ArchivedExperimentPlot { id: String, experiment_id: String, name: String },
    ArchivedExperimentExport { id: String, experiment_id: String, kind: String, destination: String },
    ExperimentResult { id: String, task_id: String },
    ExperimentPlot { id: String, task_id: String, name: String },
    ExperimentExport { id: String, task_id: String, kind: String, destination: String },
    ExperimentTask { id: String, task_id: String, action: String },
    CancelRequest { id: String, request_id: String },
    GetRequest { id: String, request_id: String },
    StartAnnotation {
        id: String,
        request_id: String,
        cube_ids: Vec<String>,
        mode: String,
    },
    AnnotationTask {
        id: String,
        task_id: String,
        action: String,
        after: Option<u32>,
        limit: Option<u32>,
        version: Option<u64>,
        request_id: Option<String>,
        mode: Option<String>,
        authorization_id: Option<String>,
    },
    CheckBatchPrepare {
        id: String,
        dataset_version_id: Option<String>,
    },
    CreateSession {
        scope: Option<SessionScope>,
        request_id: Option<String>,
        partial_confirmation_token: Option<String>,
    },
    PreflightSession {
        dataset_version_id: String,
    },
    ListSessions {
        #[serde(default)]
        query: SessionQuery,
    },
    GetSession {
        id: String,
    },
    ListMembers {
        id: String,
        after: Option<u32>,
        limit: Option<u32>,
    },
    GetHistory {
        id: String,
        before: Option<u64>,
        after: Option<u64>,
        limit: Option<u32>,
    },
    SelectCube {
        id: String,
        cube_id: Option<String>,
    },
    SendMessage {
        id: String,
        body: MessageBody,
    },
    GetSteps {
        id: String,
    },
    GetRuntime {},
    ArchiveSession {
        id: String,
    },
}

pub fn parse_request(value: Value) -> Result<AgentRequest, ForwardError> {
    if value.get("op").and_then(Value::as_str) == Some("select_cube")
        && value.get("cube_id").is_none()
    {
        return Err(invalid_request());
    }
    let request: AgentRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}
fn bounded_text(value: &Option<String>, maximum: usize) -> Result<(), ForwardError> {
    if value
        .as_ref()
        .is_some_and(|s| s.is_empty() || s.len() > maximum)
    {
        return Err(invalid_request());
    }
    Ok(())
}
fn page_limit(limit: &Option<u32>, maximum: u32) -> Result<(), ForwardError> {
    if limit.is_some_and(|v| v == 0 || v > maximum) {
        return Err(invalid_request());
    }
    Ok(())
}
impl AgentRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        match self {
            Self::InferenceHistory { id, model_id } => { uuid(id)?; uuid(model_id) }
            Self::InferenceTask { id, model_id, run_id, action } => {
                uuid(id)?;uuid(model_id)?;uuid(run_id)?;
                if !["get","cancel","result"].contains(&action.as_str()) { return Err(invalid_request()); }
                Ok(())
            }
            Self::InferencePlot { id, model_id, run_id, kind, .. } => {
                uuid(id)?;uuid(model_id)?;uuid(run_id)?;
                if kind.as_ref().is_some_and(|v| !["prediction","input"].contains(&v.as_str())) { return Err(invalid_request()); }
                Ok(())
            }
            Self::InferenceExport { id, model_id, run_id, destination } => {
                uuid(id)?;uuid(model_id)?;uuid(run_id)?;
                let path=std::path::Path::new(destination);
                if !path.is_absolute() || path.extension().and_then(|v|v.to_str())!=Some("zip") { return Err(invalid_request()); }
                Ok(())
            }
            Self::ExperimentHistory { id, limit, .. } => { uuid(id)?; page_limit(limit,50) }
            Self::SelectExperiment { id, experiment_id } | Self::ArchivedExperimentResult { id, experiment_id } => {
                uuid(id)?; uuid(experiment_id)
            }
            Self::CompareExperiments { id, first_id, second_id } => { uuid(id)?; uuid(first_id)?; uuid(second_id) }
            Self::ExperimentResult { id, task_id } => { uuid(id)?; uuid(task_id) }
            Self::ExperimentPlot { id, task_id, name } | Self::ArchivedExperimentPlot { id, experiment_id: task_id, name } => {
                uuid(id)?; uuid(task_id)?;
                if !["train_input.png","train_processed.png","test_input.png","test_processed.png"].contains(&name.as_str()) { return Err(invalid_request()); }
                Ok(())
            }
            Self::ExperimentExport { id, task_id, kind, destination } | Self::ArchivedExperimentExport { id, experiment_id: task_id, kind, destination } => {
                uuid(id)?; uuid(task_id)?;
                let expected = match kind.as_str() { "report" => "html", "bundle" => "zip", _ => return Err(invalid_request()) };
                let path = std::path::Path::new(destination);
                if !path.is_absolute() || path.extension().and_then(|v|v.to_str()) != Some(expected) { return Err(invalid_request()); }
                Ok(())
            }
            Self::ExperimentTask { id, task_id, action } => {
                uuid(id)?;
                uuid(task_id)?;
                if !["get", "cancel"].contains(&action.as_str()) { return Err(invalid_request()); }
                Ok(())
            }
            Self::CancelRequest { id, request_id } | Self::GetRequest { id, request_id } => {
                uuid(id)?;
                uuid(request_id)
            }
            Self::StartAnnotation { id, request_id, cube_ids, mode } => {
                uuid(id)?;
                uuid(request_id)?;
                if cube_ids.is_empty() || !["per_image", "all"].contains(&mode.as_str()) {
                    return Err(invalid_request());
                }
                let mut seen = std::collections::HashSet::new();
                for cube in cube_ids {
                    uuid(cube)?;
                    if !seen.insert(cube) { return Err(invalid_request()); }
                }
                Ok(())
            }
            Self::AnnotationTask { id, task_id, action, after, limit, version, request_id, mode, authorization_id } => {
                uuid(id)?; uuid(task_id)?;
                if let Some(grant) = authorization_id { uuid(grant)?; }
                if authorization_id.is_some() && action != "prepare" { return Err(invalid_request()); }
                match action.as_str() {
                    "get" | "cancel" if after.is_none() && limit.is_none() && version.is_none() && request_id.is_none() && mode.is_none() => Ok(()),
                    "items" if request_id.is_none() && mode.is_none() && *version != Some(0) => page_limit(limit, 100),
                    "prepare" if after.is_none() && limit.is_none() && version.is_none() && mode.is_none() => {
                        uuid(request_id.as_deref().ok_or_else(invalid_request)?)
                    }
                    "focus" | "blur" if after.is_none() && limit.is_none() && version.is_none() && mode.is_none() && request_id.is_none() => Ok(()),
                    "retry" if after.is_none() && limit.is_none() && version.is_none() => {
                        uuid(request_id.as_deref().ok_or_else(invalid_request)?)?;
                        if mode.as_deref().is_some_and(|m| m != "failed" && m != "remaining") { return Err(invalid_request()); }
                        Ok(())
                    }
                    _ => Err(invalid_request()),
                }
            }
            Self::CheckBatchPrepare {
                id,
                dataset_version_id,
            } => {
                uuid(id)?;
                if let Some(version) = dataset_version_id {
                    uuid(version)?;
                }
                Ok(())
            }
            Self::CreateSession {
                scope,
                request_id,
                partial_confirmation_token,
            } => {
                if let Some(SessionScope::DatasetVersion { dataset_version_id }) = scope {
                    uuid(dataset_version_id)?;
                }
                if let Some(id) = request_id {
                    uuid(id)?;
                }
                bounded_text(partial_confirmation_token, 4096)
            }
            Self::PreflightSession { dataset_version_id } => uuid(dataset_version_id),
            Self::ArchiveSession { id } => uuid(id),
            Self::ListSessions { query } => {
                if query
                    .kind
                    .as_ref()
                    .is_some_and(|k| k != "global" && k != "dataset_version")
                {
                    return Err(invalid_request());
                }
                if let Some(id) = &query.dataset_version_id {
                    uuid(id)?;
                }
                page_limit(&query.limit, 50)?;
                bounded_text(&query.cursor, 4096)
            }
            Self::GetSteps { id } | Self::GetSession { id } => uuid(id),
            Self::ListMembers { id, limit, .. } => {
                uuid(id)?;
                page_limit(limit, 100)
            }
            Self::GetHistory {
                id,
                before,
                after,
                limit,
            } => {
                uuid(id)?;
                page_limit(limit, 100)?;
                if before.is_some() && after.is_some() {
                    return Err(invalid_request());
                }
                Ok(())
            }
            Self::SelectCube { id, cube_id } => {
                uuid(id)?;
                if let Some(cube) = cube_id {
                    uuid(cube)?;
                }
                Ok(())
            }
            Self::GetRuntime {} => Ok(()),
            Self::SendMessage { id, body } => {
                uuid(id)?;
                let request_id = match body {
                    MessageBody::Content { request_id, .. }
                    | MessageBody::Answer { request_id, .. }
                    | MessageBody::Plan { request_id, .. } => request_id,
                };
                if let Some(id) = request_id {
                    uuid(id)?;
                }
                match body {
                    MessageBody::Content { content, .. } if content.trim().is_empty() => {
                        Err(invalid_request())
                    }
                    MessageBody::Content {
                        workspace: Some(workspace),
                        ..
                    } => workspace.validate(),
                    MessageBody::Answer { check_id, .. } => uuid(check_id),
                    MessageBody::Plan {
                        plan_id,
                        action,
                        step_ref,
                        reason,
                        ..
                    } => {
                        uuid(plan_id)?;
                        let valid = match action {
                            PlanAction::Approve => step_ref.is_none() && reason.is_none(),
                            PlanAction::Reject => {
                                step_ref.is_none()
                                    && reason.as_ref().is_some_and(|r| !r.trim().is_empty())
                            }
                            PlanAction::Skip | PlanAction::Rollback => {
                                step_ref.is_some_and(|n| n >= 1)
                                    && reason.as_ref().is_some_and(|r| !r.trim().is_empty())
                            }
                        };
                        if valid {
                            Ok(())
                        } else {
                            Err(invalid_request())
                        }
                    }
                    _ => Ok(()),
                }
            }
        }
    }
    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (path, method, body) = match self {
            Self::InferenceHistory { id, model_id } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{model_id}/inferences"),Method::GET,None),
            Self::InferenceTask { id, model_id, run_id, action } => {
                let base=format!("/api/v1/agent/sessions/{id}/experiment-history/{model_id}/inferences/{run_id}");
                let suffix=match action.as_str(){"cancel"=>"/cancel","result"=>"/result",_=>""};
                (format!("{base}{suffix}"),if action=="cancel"{Method::POST}else{Method::GET},None)
            }
            Self::InferencePlot { id, model_id, run_id, file_index, .. } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{model_id}/inferences/{run_id}/plots/{file_index}"),Method::GET,None),
            Self::InferenceExport { id, model_id, run_id, .. } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{model_id}/inferences/{run_id}/export"),Method::GET,None),
            Self::ExperimentHistory { id, .. } => (format!("/api/v1/agent/sessions/{id}/experiment-history"), Method::GET, None),
            Self::SelectExperiment { id, experiment_id } => (format!("/api/v1/agent/sessions/{id}/experiment-history/selection"), Method::POST, Some(json!({"experiment_id":experiment_id}))),
            Self::CompareExperiments { id, first_id, second_id } => (format!("/api/v1/agent/sessions/{id}/experiment-history/comparison"), Method::POST, Some(json!({"first_id":first_id,"second_id":second_id}))),
            Self::ArchivedExperimentResult { id, experiment_id } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{experiment_id}/result"), Method::GET, None),
            Self::ArchivedExperimentPlot { id, experiment_id, name } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{experiment_id}/plots/{name}"), Method::GET, None),
            Self::ArchivedExperimentExport { id, experiment_id, kind, .. } => (format!("/api/v1/agent/sessions/{id}/experiment-history/{experiment_id}/export/{kind}"), Method::GET, None),
            Self::ExperimentResult { id, task_id } => (format!("/api/v1/agent/sessions/{id}/experiments/{task_id}/result"), Method::GET, None),
            Self::ExperimentPlot { id, task_id, name } => (format!("/api/v1/agent/sessions/{id}/experiments/{task_id}/plots/{name}"), Method::GET, None),
            Self::ExperimentExport { id, task_id, kind, .. } => (format!("/api/v1/agent/sessions/{id}/experiments/{task_id}/export/{kind}"), Method::GET, None),
            Self::ExperimentTask { id, task_id, action } => {
                let base = format!("/api/v1/agent/sessions/{id}/experiments/{task_id}");
                if action == "cancel" { (format!("{base}/cancel"), Method::POST, None) }
                else { (base, Method::GET, None) }
            }
            Self::StartAnnotation { id, request_id, cube_ids, mode } => (
                format!("/api/v1/agent/sessions/{id}/annotation-flow"), Method::POST,
                Some(json!({"request_id": request_id, "cube_ids": cube_ids, "mode": mode})),
            ),
            Self::AnnotationTask { id, task_id, action, request_id, mode, authorization_id, .. } => {
                let base = format!("/api/v1/agent/sessions/{id}/batch-prepare/{task_id}");
                match action.as_str() {
                    "get" => (base, Method::GET, None),
                    "items" => (format!("{base}/items"), Method::GET, None),
                    "cancel" => (format!("{base}/cancel"), Method::POST, None),
                    "prepare" => {
                        let mut body = json!({"request_id":request_id});
                        if let Some(grant) = authorization_id { body["authorization_id"] = json!(grant); }
                        (format!("/api/v1/agent/sessions/{id}/annotation-flow/{task_id}/prepare"), Method::POST, Some(body))
                    },
                    "focus" | "blur" => (format!("/api/v1/agent/sessions/{id}/annotation-flow/{task_id}/{action}"), Method::POST, None),
                    "retry" => (format!("{base}/retry"), Method::POST, Some(json!({"request_id":request_id, "mode":mode.as_deref().unwrap_or("failed")}))),
                    _ => return Err(invalid_request()),
                }
            }
            Self::CheckBatchPrepare {
                id,
                dataset_version_id,
            } => (
                format!("/api/v1/agent/sessions/{id}/batch-prepare/check"),
                Method::POST,
                Some(
                    dataset_version_id
                        .as_ref()
                        .map_or_else(|| json!({}), |v| json!({"dataset_version_id":v})),
                ),
            ),
            Self::CreateSession {
                scope,
                request_id,
                partial_confirmation_token,
            } => {
                let mut value = json!({});
                if let Some(scope) = scope {
                    value["scope"] = serde_json::to_value(scope).map_err(|_| invalid_request())?;
                }
                if let Some(id) = request_id {
                    value["request_id"] = json!(id);
                }
                if let Some(token) = partial_confirmation_token {
                    value["partial_confirmation_token"] = json!(token);
                }
                ("/api/v1/agent/sessions".into(), Method::POST, Some(value))
            }
            Self::PreflightSession { dataset_version_id } => (
                "/api/v1/agent/sessions/preflight".into(),
                Method::POST,
                Some(json!({"dataset_version_id":dataset_version_id})),
            ),
            Self::ListSessions { .. } => ("/api/v1/agent/sessions".into(), Method::GET, None),
            Self::CancelRequest { id, request_id } => (
                format!("/api/v1/agent/sessions/{id}/requests/{request_id}/cancel"), Method::POST, None),
            Self::GetRequest { id, request_id } => (
                format!("/api/v1/agent/sessions/{id}/requests/{request_id}"), Method::GET, None),
            Self::GetSession { id } => (format!("/api/v1/agent/sessions/{id}"), Method::GET, None),
            Self::ListMembers { id, .. } => (
                format!("/api/v1/agent/sessions/{id}/members"),
                Method::GET,
                None,
            ),
            Self::GetHistory { id, .. } => (
                format!("/api/v1/agent/sessions/{id}/history"),
                Method::GET,
                None,
            ),
            Self::SelectCube { id, cube_id } => (
                format!("/api/v1/agent/sessions/{id}/selection"),
                Method::PATCH,
                Some(json!({"cube_id":cube_id})),
            ),
            Self::GetSteps { id } => (
                format!("/api/v1/agent/sessions/{id}/steps"),
                Method::GET,
                None,
            ),
            Self::GetRuntime {} => ("/api/v1/agent/runtime".into(), Method::GET, None),
            Self::ArchiveSession { id } => (
                format!("/api/v1/agent/sessions/{id}/archive"),
                Method::POST,
                None,
            ),
            Self::SendMessage { id, body } => (
                format!("/api/v1/agent/sessions/{id}/messages"),
                Method::POST,
                Some(serde_json::to_value(body).map_err(|_| invalid_request())?),
            ),
        };
        let mut url = fixed_url(port, &path)?;
        {
            let mut q = url.query_pairs_mut();
            match self {
                Self::AnnotationTask { action, after, limit, version, .. } if action == "items" => {
                    if let Some(v) = after { q.append_pair("after", &v.to_string()); }
                    if let Some(v) = limit { q.append_pair("limit", &v.to_string()); }
                    if let Some(v) = version { q.append_pair("version", &v.to_string()); }
                }
                Self::InferencePlot { kind, .. } => {
                    if let Some(value)=kind { q.append_pair("kind",value); }
                }
                Self::ExperimentHistory { offset, limit, .. } => {
                    q.append_pair("offset", &offset.unwrap_or(0).to_string());
                    q.append_pair("limit", &limit.unwrap_or(20).to_string());
                }
                Self::ListSessions { query } => {
                    if let Some(v) = &query.kind {
                        q.append_pair("kind", v);
                    }
                    if let Some(v) = &query.dataset_version_id {
                        q.append_pair("dataset_version_id", v);
                    }
                    if let Some(v) = &query.cursor {
                        q.append_pair("cursor", v);
                    }
                    if let Some(v) = query.limit {
                        q.append_pair("limit", &v.to_string());
                    }
                }
                Self::ListMembers { after, limit, .. } => {
                    if let Some(v) = after {
                        q.append_pair("after", &v.to_string());
                    }
                    if let Some(v) = limit {
                        q.append_pair("limit", &v.to_string());
                    }
                }
                Self::GetHistory {
                    before,
                    after,
                    limit,
                    ..
                } => {
                    if let Some(v) = before {
                        q.append_pair("before", &v.to_string());
                    }
                    if let Some(v) = after {
                        q.append_pair("after", &v.to_string());
                    }
                    if let Some(v) = limit {
                        q.append_pair("limit", &v.to_string());
                    }
                }
                _ => {}
            }
        }
        if url.query() == Some("") {
            url.set_query(None);
        }
        Ok((url, method, body))
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
            "step" | "clarify" | "human_check" | "plan" | "workspace" | "done" | "error" | "progress"
        ) {
            return Err(ForwardError::new("INVALID_BODY", "SSE 事件类型非法"));
        }
        let value: Value = serde_json::from_str(&data.join("\n"))
            .map_err(|_| ForwardError::new("INVALID_BODY", "SSE 数据不是有效JSON"))?;
        if !value.is_object() {
            return Err(ForwardError::new("INVALID_BODY", "SSE 数据必须为对象"));
        }
        if name == "progress" && (!value.get("phase").and_then(Value::as_str)
            .is_some_and(|phase| ["model", "tool"].contains(&phase))
            || value.as_object().is_some_and(|fields| fields.keys().any(|key| !["phase", "tool"].contains(&key.as_str())))
            || value.get("tool").is_some_and(|tool| !tool.is_string())) {
            return Err(ForwardError::new("INVALID_BODY", "SSE 阶段非法"));
        }
        if name == "workspace" {
            let object = value.as_object().ok_or_else(invalid_request)?;
            if object.keys().any(|key| {
                ![
                    "cube_id",
                    "gesture_ref",
                    "display_name",
                    "stage",
                    "revision",
                ]
                .contains(&key.as_str())
            }) || !value
                .get("cube_id")
                .and_then(Value::as_str)
                .is_some_and(|cube| uuid(cube).is_ok())
                || value
                    .get("gesture_ref")
                    .is_some_and(|gesture| !gesture.as_str().is_some_and(gesture_reference))
                || value
                    .get("display_name")
                    .is_some_and(|name| !name.is_string())
                || value.get("stage").is_some_and(|stage| {
                    !stage
                        .as_str()
                        .is_some_and(|value| ["annotation", "preprocess"].contains(&value))
                })
                || value
                    .get("revision")
                    .is_some_and(|revision| revision.as_u64().is_none())
            {
                return Err(ForwardError::new("INVALID_BODY", "SSE 工作区引用非法"));
            }
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

fn reject_sensitive_value(value: &Value, secrets: &[&str]) -> Result<(), ForwardError> {
    match value {
        Value::String(text) => reject_sensitive(text.as_bytes(), secrets),
        Value::Array(items) => items
            .iter()
            .try_for_each(|item| reject_sensitive_value(item, secrets)),
        Value::Object(fields) => fields.iter().try_for_each(|(key, item)| {
            reject_sensitive(key.as_bytes(), secrets)?;
            reject_sensitive_value(item, secrets)
        }),
        _ => Ok(()),
    }
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
    forward_http_scoped(identity, url, method, body, sse, (secrets, &[]))
}

// Project paths must be visible in successful settings responses. They remain
// forbidden in error envelopes; credentials keep the stronger all-response rule.
pub(crate) fn forward_http_scoped(
    identity: &Handshake,
    url: Url,
    method: Method,
    body: Option<Value>,
    sse: bool,
    protected: (&[&str], &[&str]),
) -> Result<Value, ForwardError> {
    let (secrets, error_secrets) = protected;
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
        .chain(
            error_secrets
                .iter()
                .copied()
                .filter(|_| !status.is_success()),
        )
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
    reject_sensitive_value(&value, &secrets)?;
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

fn save_experiment_export(identity: &Handshake, url: Url, destination: &str, limit: u64) -> Result<Value, ForwardError> {
    use std::io::Write;
    let path = std::path::Path::new(destination);
    if path.exists() { return Err(ForwardError::new("EXPORT_DESTINATION_EXISTS", "保存位置已有文件，请选择新文件名")); }
    let response = Client::builder().no_proxy().redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(2)).timeout(Duration::from_secs(60)).build()
        .map_err(|_|ForwardError::new("TRANSPORT","无法初始化导出连接"))?
        .get(url).bearer_auth(identity.token()).send()
        .map_err(|_|ForwardError::new("TRANSPORT","无法读取实验报告"))?;
    let header = |key|response.headers().get(key).and_then(|v|v.to_str().ok());
    if header("X-SpectrumAgent-Boot-Id") != Some(identity.boot_id.as_str())
        || header("X-SpectrumAgent-Pid") != Some(identity.pid.to_string().as_str()) {
        return Err(ForwardError::new("SESSION_IDENTITY_MISMATCH","导出响应与当前引擎不一致"));
    }
    if !response.status().is_success() || header("Content-Type") != Some("application/octet-stream") {
        return Err(ForwardError::new("EXPERIMENT_EXPORT_FAILED","报告尚未就绪或产物校验失败，未写入文件"));
    }
    let expected = response.content_length();
    if expected.is_some_and(|n|n > limit) { return Err(ForwardError::new("RESPONSE_TOO_LARGE","报告超过导出上限")); }
    let mut bytes=Vec::new();
    response.take(limit+1).read_to_end(&mut bytes).map_err(|_|ForwardError::new("TRANSPORT","报告下载中断"))?;
    if bytes.len() as u64 > limit || expected.is_some_and(|n|n != bytes.len() as u64) {
        return Err(ForwardError::new("INVALID_BODY","报告下载不完整或超过上限"));
    }
    reject_sensitive(&bytes, &[identity.token()])?;
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|_|ForwardError::new("EXPORT_WRITE_FAILED","无法创建临时文件"))?.as_nanos();
    let temporary=path.with_extension(format!("{stamp}.part"));
    let mut file=std::fs::OpenOptions::new().write(true).create_new(true).open(&temporary)
        .map_err(|_|ForwardError::new("EXPORT_WRITE_FAILED","无法创建导出文件"))?;
    let saved=(|| -> std::io::Result<()> {
        file.write_all(&bytes)?;file.flush()?;file.sync_all()?;
        std::fs::hard_link(&temporary,path)?;Ok(())
    })();
    drop(file);let _=std::fs::remove_file(&temporary);
    saved.map_err(|_|ForwardError::new("EXPORT_WRITE_FAILED","未完成保存，请选择新文件名；服务器产物保留"))?;
    Ok(json!({"saved":true,"bytes":bytes.len()}))
}

pub fn forward(identity: &Handshake, request: &AgentRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    if let AgentRequest::ExperimentExport { destination, .. } | AgentRequest::ArchivedExperimentExport { destination, .. } = request {
        return save_experiment_export(identity, url, destination,16*1024*1024);
    }
    if let AgentRequest::InferenceExport { destination, .. } = request {
        return save_experiment_export(identity,url,destination,64*1024*1024);
    }
    let mut result = forward_http(
        identity,
        url,
        method,
        body,
        matches!(request, AgentRequest::SendMessage { .. }),
        &[],
    )?;
    if matches!(request, AgentRequest::GetRuntime {}) {
        result["desktop_transport"] = json!({"protocol":1,"stream":true});
    }
    Ok(result)
}

/// Deliver only complete, validated frames. UTF-8, secret scanning, identity,
/// response bounds and the engine generation gate also apply to live events.
pub fn forward_stream(
    identity: &Handshake,
    request: &AgentRequest,
    mut on_event: impl FnMut(Value) -> Result<(), ForwardError>,
) -> Result<(), ForwardError> {
    if !matches!(request, AgentRequest::SendMessage { .. }) {
        return Err(invalid_request());
    }
    let (mut url, method, body) = request.destination(identity.port)?;
    url.query_pairs_mut().append_pair("progress", "true");
    let client = Client::builder().no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(300)).build()
        .map_err(|_| ForwardError::new("TRANSPORT", "本机请求初始化失败"))?;
    let response = client.request(method, url).bearer_auth(identity.token())
        .json(&body).send()
        .map_err(|_| ForwardError::new("TRANSPORT", "数据引擎请求失败或超时"))?;
    let header = |key| response.headers().get(key).and_then(|v| v.to_str().ok());
    if header("X-SpectrumAgent-Boot-Id") != Some(identity.boot_id.as_str())
        || header("X-SpectrumAgent-Pid") != Some(identity.pid.to_string().as_str()) {
        return Err(ForwardError::new("DATASET_IDENTITY_MISMATCH", "响应与本代引擎身份不匹配"));
    }
    if response.content_length().is_some_and(|size| size > MAX_RESPONSE_BYTES) {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
    }
    let status = response.status();
    if status.is_success() && !header("Content-Type")
        .is_some_and(|value| value.split(';').next() == Some("text/event-stream")) {
        return Err(ForwardError::new("INVALID_BODY", "响应不是SSE流"));
    }
    let secrets = [identity.token()];
    if !status.is_success() {
        let mut bytes = Vec::new();
        response.take(MAX_RESPONSE_BYTES + 1).read_to_end(&mut bytes)
            .map_err(|_| ForwardError::new("TRANSPORT", "读取响应失败"))?;
        if bytes.len() as u64 > MAX_RESPONSE_BYTES {
            return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
        }
        reject_sensitive(&bytes, &secrets)?;
        let value: Value = serde_json::from_slice(&bytes)
            .map_err(|_| ForwardError::new("INVALID_BODY", "响应不是有效JSON"))?;
        reject_sensitive_value(&value, &secrets)?;
        let mut failure = serde_json::from_value::<ForwardError>(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "数据引擎返回错误"));
        failure.status_code = Some(status.as_u16());
        return Err(failure);
    }
    stream_frames(response, &secrets, &mut on_event)
}

fn stream_frames(
    reader: impl Read,
    secrets: &[&str],
    on_event: &mut impl FnMut(Value) -> Result<(), ForwardError>,
) -> Result<(), ForwardError> {
    let mut reader = BufReader::new(reader.take(MAX_RESPONSE_BYTES + 1));
    let mut frame = Vec::new();
    let mut total = 0u64;
    loop {
        let start = frame.len();
        let count = reader.read_until(b'\n', &mut frame)
            .map_err(|_| ForwardError::new("TRANSPORT", "读取响应失败"))?;
        total += count as u64;
        if total > MAX_RESPONSE_BYTES {
            return Err(ForwardError::new("RESPONSE_TOO_LARGE", "响应超过8MiB上限"));
        }
        if count == 0 {
            if !frame.is_empty() {
                return Err(ForwardError::new("INVALID_BODY", "SSE 响应中断，事件不完整"));
            }
            return Ok(());
        }
        if frame[start..] != *b"\n" && frame[start..] != *b"\r\n" {
            continue;
        }
        reject_sensitive(&frame, secrets)?;
        let text = std::str::from_utf8(&frame)
            .map_err(|_| ForwardError::new("INVALID_BODY", "SSE 编码非法"))?;
        let batch = parse_sse(text)?;
        reject_sensitive_value(&batch, secrets)?;
        if let Some(events) = batch["events"].as_array() {
            for event in events { on_event(event.clone())?; }
        }
        frame.clear();
    }
}

#[cfg(test)]
mod streaming_tests {
    use super::*;
    use std::sync::{Arc, atomic::{AtomicBool, Ordering}};

    #[test]
    fn live_event_arrives_before_eof_and_utf8_survives_byte_reads() -> Result<(), ForwardError> {
        struct Gated {
            bytes: Vec<u8>, index: usize, first_end: usize, delivered: Arc<AtomicBool>,
        }
        impl Read for Gated {
            fn read(&mut self, out: &mut [u8]) -> std::io::Result<usize> {
                if self.index == self.first_end && !self.delivered.load(Ordering::SeqCst) {
                    return Err(std::io::Error::other("first event was buffered"));
                }
                if self.index == self.bytes.len() { return Ok(0); }
                out[0] = self.bytes[self.index];
                self.index += 1;
                Ok(1)
            }
        }
        let first = "event: progress\r\ndata: {\"phase\":\"model\"}\r\n\r\n";
        let second = "event: done\ndata: {\"content\":\"分割就绪\",\"step_count\":0}\n\n";
        let delivered = Arc::new(AtomicBool::new(false));
        let reader = Gated {bytes: format!("{first}{second}").into_bytes(),index:0,
            first_end:first.len(),delivered:delivered.clone()};
        let mut events = Vec::new();
        stream_frames(reader, &[], &mut |event| {
            delivered.store(true, Ordering::SeqCst);
            events.push(event);
            Ok(())
        })?;
        assert_eq!(events.len(), 2);
        assert_eq!(events[1]["data"]["content"], "分割就绪");
        Ok(())
    }

    #[test]
    fn live_frames_reject_decoded_secrets_and_incomplete_events() {
        let escaped = b"event: done\ndata: {\"content\":\"s\\u0065cret\"}\n\n";
        let mut delivered = 0;
        assert!(stream_frames(&escaped[..], &["secret"], &mut |_| { delivered+=1; Ok(()) }).is_err());
        assert_eq!(delivered, 0);
        assert!(stream_frames(&b"event: done\ndata: {}"[..], &[], &mut |_| Ok(())).is_err());
        assert!(stream_frames(&b"event: progress\ndata: {\"phase\":\"invented\"}\n\n"[..], &[], &mut |_| Ok(())).is_err());
    }

    #[test]
    fn cancel_destination_is_fixed_and_requires_owned_identifiers() -> Result<(), ForwardError> {
        let sid = "00000000-0000-0000-0000-000000000001";
        let rid = "00000000-0000-0000-0000-000000000002";
        let request = parse_request(json!({"op":"cancel_request","id":sid,"request_id":rid}))?;
        let (url, method, body) = request.destination(1234)?;
        assert_eq!(url.path(), format!("/api/v1/agent/sessions/{sid}/requests/{rid}/cancel"));
        assert_eq!(method, Method::POST);
        assert!(body.is_none());
        assert!(parse_request(json!({"op":"cancel_request","id":sid,"request_id":"../other"})).is_err());
        assert!(parse_request(json!({"op":"cancel_request","id":sid,"request_id":rid,"url":"http://other"})).is_err());
        Ok(())
    }

    #[test]
    fn experiment_task_routes_only_query_and_cancel() -> Result<(), ForwardError> {
        let sid = "00000000-0000-0000-0000-000000000001";
        let tid = "00000000-0000-0000-0000-000000000002";
        for action in ["get", "cancel"] {
            let request = parse_request(json!({"op":"experiment_task","id":sid,"task_id":tid,"action":action}))?;
            let (url, method, body) = request.destination(1234)?;
            let suffix = if action == "cancel" { "/cancel" } else { "" };
            assert_eq!(url.path(), format!("/api/v1/agent/sessions/{sid}/experiments/{tid}{suffix}"));
            assert_eq!(method, if action == "cancel" { Method::POST } else { Method::GET });
            assert!(body.is_none());
        }
        assert!(parse_request(json!({"op":"experiment_task","id":sid,"task_id":tid,"action":"run"})).is_err());
        assert!(parse_request(json!({"op":"experiment_task","id":sid,"task_id":"../other","action":"get"})).is_err());
        Ok(())
    }

    #[test]
    fn experiment_results_allow_only_fixed_files_and_export_formats() -> Result<(), ForwardError> {
        let sid = "00000000-0000-0000-0000-000000000001";
        let tid = "00000000-0000-0000-0000-000000000002";
        let request = parse_request(json!({"op":"experiment_result","id":sid,"task_id":tid}))?;
        assert_eq!(request.destination(1234)?.0.path(), format!("/api/v1/agent/sessions/{sid}/experiments/{tid}/result"));
        for name in ["train_input.png","train_processed.png","test_input.png","test_processed.png"] {
            let request = parse_request(json!({"op":"experiment_plot","id":sid,"task_id":tid,"name":name}))?;
            assert_eq!(request.destination(1234)?.0.path(), format!("/api/v1/agent/sessions/{sid}/experiments/{tid}/plots/{name}"));
        }
        for name in ["../model.joblib", "model.joblib", "test_input.png?other=1"] {
            assert!(parse_request(json!({"op":"experiment_plot","id":sid,"task_id":tid,"name":name})).is_err());
        }
        let path = std::env::temp_dir().join("report.html");
        assert!(parse_request(json!({"op":"experiment_export","id":sid,"task_id":tid,"kind":"model","destination":path})).is_err());
        assert!(parse_request(json!({"op":"experiment_export","id":sid,"task_id":tid,"kind":"bundle","destination":path})).is_err());
        assert!(parse_request(json!({"op":"experiment_export","id":sid,"task_id":tid,"kind":"report","destination":"relative.html"})).is_err());
        Ok(())
    }

    #[test]
    fn archived_experiment_routes_are_bounded_and_use_real_ids() -> Result<(), ForwardError> {
        let sid="00000000-0000-0000-0000-000000000001";
        let eid="00000000-0000-0000-0000-000000000002";
        let request=parse_request(json!({"op":"experiment_history","id":sid,"offset":20,"limit":20}))?;
        let (url,method,body)=request.destination(1234)?;
        assert_eq!(url.path(),format!("/api/v1/agent/sessions/{sid}/experiment-history"));
        assert_eq!(url.query(),Some("offset=20&limit=20"));
        assert_eq!(method,Method::GET);assert!(body.is_none());
        let request=parse_request(json!({"op":"select_experiment","id":sid,"experiment_id":eid}))?;
        let (url,method,body)=request.destination(1234)?;
        assert_eq!(url.path(),format!("/api/v1/agent/sessions/{sid}/experiment-history/selection"));
        assert_eq!(method,Method::POST);assert_eq!(body,Some(json!({"experiment_id":eid})));
        for (op,suffix,extra) in [
            ("archived_experiment_result","result",json!({})),
            ("archived_experiment_plot","plots/test_input.png",json!({"name":"test_input.png"})),
            ("archived_experiment_export","export/report",json!({"kind":"report","destination":std::env::temp_dir().join("report.html")})),
        ] {
            let mut value=json!({"op":op,"id":sid,"experiment_id":eid});
            if let (Some(target),Some(extra))=(value.as_object_mut(),extra.as_object()) { target.extend(extra.clone()); }
            let request=parse_request(value)?;
            assert_eq!(request.destination(1234)?.0.path(),format!("/api/v1/agent/sessions/{sid}/experiment-history/{eid}/{suffix}"));
        }
        assert!(parse_request(json!({"op":"experiment_history","id":sid,"limit":51})).is_err());
        assert!(parse_request(json!({"op":"experiment_history","id":sid,"offset":-1})).is_err());
        assert!(parse_request(json!({"op":"archived_experiment_result","id":sid,"experiment_id":"../other"})).is_err());
        assert!(parse_request(json!({"op":"archived_experiment_plot","id":sid,"experiment_id":eid,"name":"model.joblib"})).is_err());
        assert!(parse_request(json!({"op":"archived_experiment_result","id":sid,"experiment_id":eid,"url":"http://other"})).is_err());
        Ok(())
    }

    #[test]
    fn inference_routes_do_not_allow_training_paths_or_arbitrary_downloads() -> Result<(), ForwardError> {
        let sid="00000000-0000-0000-0000-000000000001";
        let mid="00000000-0000-0000-0000-000000000002";
        let rid="00000000-0000-0000-0000-000000000003";
        for action in ["get","cancel","result"] {
            let request=parse_request(json!({"op":"inference_task","id":sid,"model_id":mid,"run_id":rid,"action":action}))?;
            let (url,method,body)=request.destination(1234)?;
            let suffix=match action {"cancel"=>"/cancel","result"=>"/result",_=>""};
            assert_eq!(url.path(),format!("/api/v1/agent/sessions/{sid}/experiment-history/{mid}/inferences/{rid}{suffix}"));
            assert_eq!(method,if action=="cancel"{Method::POST}else{Method::GET});
            assert!(body.is_none());
        }
        let request=parse_request(json!({"op":"inference_plot","id":sid,"model_id":mid,"run_id":rid,"file_index":0}))?;
        assert!(request.destination(1234)?.0.path().ends_with("/plots/0"));
        let input=parse_request(json!({"op":"inference_plot","id":sid,"model_id":mid,"run_id":rid,"file_index":0,"kind":"input"}))?;
        assert_eq!(input.destination(1234)?.0.query(),Some("kind=input"));
        assert!(parse_request(json!({"op":"inference_plot","id":sid,"model_id":mid,"run_id":rid,"file_index":0,"kind":"model.joblib"})).is_err());
        assert!(parse_request(json!({"op":"inference_task","id":sid,"model_id":mid,"run_id":rid,"action":"train"})).is_err());
        assert!(parse_request(json!({"op":"inference_plot","id":sid,"model_id":mid,"run_id":rid,"file_index":-1})).is_err());
        assert!(parse_request(json!({"op":"inference_task","id":sid,"model_id":"../model","run_id":rid,"action":"get"})).is_err());
        assert!(parse_request(json!({"op":"inference_export","id":sid,"model_id":mid,"run_id":rid,"destination":"relative.zip"})).is_err());
        assert!(parse_request(json!({"op":"inference_export","id":sid,"model_id":mid,"run_id":rid,"destination":std::env::temp_dir().join("report.html")})).is_err());
        assert!(parse_request(json!({"op":"inference_task","id":sid,"model_id":mid,"run_id":rid,"action":"get","url":"http://other"})).is_err());
        Ok(())
    }

    #[test]
    fn report_download_checks_identity_and_never_overwrites() -> Result<(), Box<dyn std::error::Error>> {
        use std::{io::Write, net::TcpListener, thread};
        let sid = "00000000-0000-0000-0000-000000000001";
        let tid = "00000000-0000-0000-0000-000000000002";
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_nanos();
        let folder = std::env::temp_dir().join(format!("spectrum-result-{}-{stamp}",std::process::id()));
        std::fs::create_dir(&folder)?;
        let run = (|| -> Result<(), Box<dyn std::error::Error>> {
            for valid_identity in [false, true] {
                let listener = TcpListener::bind(("127.0.0.1",0))?;
                listener.set_nonblocking(true)?;
                let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
                    "boot_id":"1234abcd","pid":123,"port":listener.local_addr()?.port(),
                    "token":"0123456789abcdef0123456789abcdef","protocol":1,"version":"0.1.0",
                    "process_created_at":"2026-10-19T00:00:00.000Z","started_at":"2026-10-19T00:00:00.000Z"
                }))?)?;
                let path = folder.join("report.html");
                let request = parse_request(json!({"op":"experiment_export","id":sid,"task_id":tid,"kind":"report","destination":path}))?;
                let server = thread::spawn(move || -> std::io::Result<String> {
                    let deadline = std::time::Instant::now()+Duration::from_secs(5);
                    let mut socket = loop {
                        match listener.accept() {
                            Ok((socket,_))=>break socket,
                            Err(error) if error.kind()==std::io::ErrorKind::WouldBlock => {
                                if std::time::Instant::now()>=deadline { return Err(std::io::Error::other("stub accept timeout")); }
                                thread::sleep(Duration::from_millis(2));
                            }
                            Err(error)=>return Err(error),
                        }
                    };
                    socket.set_nonblocking(false)?;
                    socket.set_read_timeout(Some(Duration::from_secs(3)))?;
                    let mut incoming=Vec::new();
                    while !incoming.ends_with(b"\r\n\r\n") && incoming.len()<65536 {
                        let mut byte=[0];
                        if socket.read(&mut byte)?==0 { return Err(std::io::Error::other("incomplete request")); }
                        incoming.push(byte[0]);
                    }
                    let boot=if valid_identity {"1234abcd"} else {"different"};
                    socket.write_all(format!("HTTP/1.1 200 OK\r\nConnection: close\r\nX-SpectrumAgent-Boot-Id: {boot}\r\nX-SpectrumAgent-Pid: 123\r\nContent-Type: application/octet-stream\r\nContent-Length: 15\r\n\r\n<html>ok</html>").as_bytes())?;
                    Ok(String::from_utf8_lossy(&incoming).into_owned())
                });
                let result=forward(&identity,&request);
                let incoming=server.join().map_err(|_|std::io::Error::other("stub thread failed"))??;
                assert!(incoming.starts_with(&format!("GET /api/v1/agent/sessions/{sid}/experiments/{tid}/export/report ")));
                assert!(incoming.to_ascii_lowercase().contains("authorization: bearer 0123456789abcdef0123456789abcdef"));
                if valid_identity {
                    assert_eq!(result?["saved"],true);
                    assert_eq!(std::fs::read(&path)?,b"<html>ok</html>");
                    assert_eq!(forward(&identity,&request).err().map(|e|e.error),Some("EXPORT_DESTINATION_EXISTS".into()));
                    assert_eq!(std::fs::read(&path)?,b"<html>ok</html>");
                } else {
                    assert_eq!(result.err().map(|e|e.error),Some("SESSION_IDENTITY_MISMATCH".into()));
                    assert!(!path.exists());
                }
            }
            assert_eq!(std::fs::read_dir(&folder)?.count(),1); // no partial download remains
            Ok(())
        })();
        std::fs::remove_file(folder.join("report.html")).ok();
        std::fs::remove_dir(folder)?;
        run
    }
}
