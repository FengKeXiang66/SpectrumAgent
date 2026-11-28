//! Fixed sample-target and PLS operations; credentials and destinations stay native.
pub use crate::annotation::ForwardError;
use crate::{annotation::MAX_RESPONSE_BYTES, handshake::Handshake};
use reqwest::{Method, Url, blocking::Client};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{io::Read, time::Duration};
use std::sync::atomic::{AtomicU64, Ordering};

static REQUEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);
pub fn request_id() -> String {
    format!("m-{}-{}", std::process::id(), REQUEST_SEQUENCE.fetch_add(1, Ordering::Relaxed))
}
fn transport_error(stage: &str, trace: &str, identity: &Handshake, error: Option<&reqwest::Error>) -> ForwardError {
    let mut result = ForwardError::new("TRANSPORT", "建模传输中断，请按请求编号核对后台状态");
    result.context = json!({"request_id":trace,"stage":stage,"engine_boot_id":identity.boot_id,
        "timeout":error.is_some_and(|e|e.is_timeout()),"connect":error.is_some_and(|e|e.is_connect())});
    result
}

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum ModelRequest {
    ListTargets {
        project_id: String,
    },
    PutTarget {
        cube_id: String,
        schema_id: String,
        value: f64,
    },
    ImportTargets {
        project_id: String,
        csv_text: String,
        overwrite: bool,
    },
    CreateRun {
        body: Value,
    },
    SubmitTraining {
        id: String,
        body: Value,
    },
    GetTrainingJob {
        id: String,
    },
    ListTrainingJobs,
    TrainingEvents { id: String, after: u64, limit: u32 },
    CancelTraining { id: String },
    ContinueTraining { id: String, new_id: String },
    TrainingPartial { id: String },
    DownloadTraining { id: String, destination: String, kind: String },
    PreflightRun {
        body: Value,
    },
    ListRuns,
    GetRun {
        id: String,
    },
    LvSweep {
        id: String,
    },
    RegisterModel {
        run_id: String,
        name: Option<String>,
    },
    ListModels,
    SetModelStage {
        id: String,
        stage: String,
    },
    CreateInference {
        model_id: String,
        cube_id: String,
        preprocess_run_id: Option<String>,
        annotation_version_id: Option<String>,
    },
    GetInference {
        id: String,
    },
    GetInferenceMap {
        id: String,
    },
    GetCoefficients {
        model_id: String,
    },
    Classification {
        evaluation_id: String,
        action: String,
        body: Value,
    },
    DownloadClassification {
        export_id: String,
        destination: String,
    },
}

fn invalid() -> ForwardError {
    ForwardError::new("INVALID_MODEL_REQUEST", "建模请求字段或标识非法")
}
fn identifier(value: &str) -> Result<(), ForwardError> {
    if value.is_empty()
        || value.len() > 64
        || !value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
    {
        return Err(invalid());
    }
    Ok(())
}
pub fn parse_request(value: Value) -> Result<ModelRequest, ForwardError> {
    if serde_json::to_vec(&value).map_err(|_| invalid())?.len() > 2 * 1024 * 1024 {
        return Err(invalid());
    }
    let extra = value.as_object().is_none_or(|fields| fields.len() != 1);
    let request: ModelRequest = serde_json::from_value(value).map_err(|_| invalid())?;
    if matches!(request, ModelRequest::ListRuns | ModelRequest::ListModels | ModelRequest::ListTrainingJobs) && extra {
        return Err(invalid());
    }
    request.destination(1)?;
    Ok(request)
}
impl ModelRequest {
    fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        let (path, method, body) = match self {
            Self::DownloadTraining { id, destination, kind } => {
                identifier(id)?;
                if !["events", "partial"].contains(&kind.as_str()) || !std::path::Path::new(destination).is_absolute() || destination.contains('\0') {
                    return Err(invalid());
                }
                (format!("/api/v1/models/training-jobs/{id}/export"), Method::GET, None)
            }
            Self::Classification { evaluation_id, action, body } => {
                identifier(evaluation_id)?;
                if !["curves","map","pixel","coefficients","importance","compare","interpret",
                    "register","baseline","infer","task","cancel","retry","export","threshold","choices","evaluate_prediction"].contains(&action.as_str())
                    || !body.is_object() { return Err(invalid()); }
                (format!("/api/v1/models/classification/{evaluation_id}/{action}"), Method::POST, Some(body.clone()))
            }
            Self::DownloadClassification { export_id, destination } => {
                identifier(export_id)?;
                let target = std::path::Path::new(destination);
                if !target.is_absolute() || destination.contains('\0') { return Err(invalid()); }
                (format!("/api/v1/models/classification-exports/{export_id}"), Method::GET, None)
            }
            Self::ListTargets { project_id } => {
                identifier(project_id)?;
                ("/api/v1/models/sample-targets".into(), Method::GET, None)
            }
            Self::PutTarget {
                cube_id,
                schema_id,
                value,
            } => {
                identifier(cube_id)?;
                identifier(schema_id)?;
                if !value.is_finite() {
                    return Err(invalid());
                }
                (
                    format!("/api/v1/models/sample-targets/{cube_id}/{schema_id}"),
                    Method::PUT,
                    Some(json!({"value":value})),
                )
            }
            Self::ImportTargets {
                project_id,
                csv_text,
                overwrite,
            } => {
                identifier(project_id)?;
                (
                    "/api/v1/models/sample-targets/import-csv".into(),
                    Method::POST,
                    Some(
                        json!({"project_id":project_id,"csv_text":csv_text,"overwrite":overwrite}),
                    ),
                )
            }
            Self::SubmitTraining { id, body } => {
                identifier(id)?;
                if !body.is_object() { return Err(invalid()); }
                (format!("/api/v1/models/training-jobs/{id}"), Method::PUT, Some(body.clone()))
            }
            Self::GetTrainingJob { id } => {
                identifier(id)?;
                (format!("/api/v1/models/training-jobs/{id}"), Method::GET, None)
            }
            Self::ListTrainingJobs => ("/api/v1/models/training-jobs".into(), Method::GET, None),
            Self::TrainingEvents { id, limit, .. } => {
                identifier(id)?;
                if *limit == 0 || *limit > 50 { return Err(invalid()); }
                (format!("/api/v1/models/training-jobs/{id}/events"), Method::GET, None)
            }
            Self::CancelTraining { id } => {
                identifier(id)?;
                (format!("/api/v1/models/training-jobs/{id}/cancel"), Method::POST, Some(json!({})))
            }
            Self::ContinueTraining { id, new_id } => {
                identifier(id)?; identifier(new_id)?;
                (format!("/api/v1/models/training-jobs/{id}/continue"), Method::POST, Some(json!({"job_id":new_id})))
            }
            Self::TrainingPartial { id } => {
                identifier(id)?;
                (format!("/api/v1/models/training-jobs/{id}/partial"), Method::GET, None)
            }
            Self::CreateRun { body } => (
                "/api/v1/models/runs".into(),
                Method::POST,
                Some(body.clone()),
            ),
            Self::PreflightRun { body } => (
                "/api/v1/models/runs/preflight".into(),
                Method::POST,
                Some(body.clone()),
            ),
            Self::ListRuns => ("/api/v1/models/runs".into(), Method::GET, None),
            Self::GetRun { id } => {
                identifier(id)?;
                (format!("/api/v1/models/runs/{id}"), Method::GET, None)
            }
            Self::LvSweep { id } => {
                identifier(id)?;
                (
                    format!("/api/v1/models/runs/{id}/lv-sweep"),
                    Method::GET,
                    None,
                )
            }
            Self::RegisterModel { run_id, name } => {
                identifier(run_id)?;
                if name
                    .as_ref()
                    .is_some_and(|s| s.trim().is_empty() || s.chars().count() > 200)
                {
                    return Err(invalid());
                }
                (
                    "/api/v1/models/registry".into(),
                    Method::POST,
                    Some(json!({"run_id":run_id,"name":name})),
                )
            }
            Self::ListModels => ("/api/v1/models/registry".into(), Method::GET, None),
            Self::SetModelStage { id, stage } => {
                identifier(id)?;
                if !["experiment", "candidate", "production"].contains(&stage.as_str()) {
                    return Err(invalid());
                }
                (
                    format!("/api/v1/models/registry/{id}/stage"),
                    Method::PUT,
                    Some(json!({"stage":stage})),
                )
            }
            Self::CreateInference {
                model_id,
                cube_id,
                preprocess_run_id,
                annotation_version_id,
            } => {
                for id in [model_id, cube_id] {
                    identifier(id)?;
                }
                for id in [preprocess_run_id, annotation_version_id].into_iter().flatten() {
                    identifier(id)?;
                }
                (
                    "/api/v1/models/inference-runs".into(),
                    Method::POST,
                    Some(
                        json!({"model_id":model_id,"cube_id":cube_id,"preprocess_run_id":preprocess_run_id,"annotation_version_id":annotation_version_id}),
                    ),
                )
            }
            Self::GetInference { id } => {
                identifier(id)?;
                (
                    format!("/api/v1/models/inference-runs/{id}"),
                    Method::GET,
                    None,
                )
            }
            Self::GetInferenceMap { id } => {
                identifier(id)?;
                (
                    format!("/api/v1/models/inference-runs/{id}/map"),
                    Method::GET,
                    None,
                )
            }
            Self::GetCoefficients { model_id } => {
                identifier(model_id)?;
                (
                    format!("/api/v1/models/registry/{model_id}/coefficients"),
                    Method::GET,
                    None,
                )
            }
        };
        let mut url = Url::parse("http://127.0.0.1/").map_err(|_| invalid())?;
        if port == 0 || url.set_port(Some(port)).is_err() {
            return Err(invalid());
        }
        url.set_path(&path);
        if let Self::DownloadTraining { kind, .. } = self { url.query_pairs_mut().append_pair("kind", kind); }
        if let Self::ListTargets { project_id } = self {
            url.query_pairs_mut().append_pair("project_id", project_id);
        }
        if let Self::TrainingEvents { after, limit, .. } = self {
            url.query_pairs_mut().append_pair("after", &after.to_string()).append_pair("limit", &limit.to_string());
        }
        Ok((url, method, body))
    }
}
pub fn forward(identity: &Handshake, request: &ModelRequest) -> Result<Value, ForwardError> {
    forward_traced(identity, request, &request_id())
}
pub fn forward_traced(identity: &Handshake, request: &ModelRequest, trace: &str) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    let short = matches!(request,
        ModelRequest::SubmitTraining { .. } | ModelRequest::GetTrainingJob { .. } | ModelRequest::ListTrainingJobs
        | ModelRequest::TrainingEvents { .. } | ModelRequest::CancelTraining { .. }
        | ModelRequest::ContinueTraining { .. } | ModelRequest::TrainingPartial { .. });
    let client = crate::http_client::shared(if short { "models-short" } else { "domain-long" }, || Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_millis(500))
        .timeout(Duration::from_secs(if short { 15 } else { 300 })))
        .map_err(|e| transport_error("initialize", trace, identity, Some(&e)))?;
    let mut outgoing = client.request(method, url).bearer_auth(identity.token())
        .header("X-SpectrumAgent-Request-Id", trace);
    if let Some(body) = body {
        outgoing = outgoing.json(&body);
    }
    let response = outgoing
        .send()
        .map_err(|e| transport_error("send_or_wait_headers", trace, identity, Some(&e)))?;
    let header = |key| response.headers().get(key).and_then(|v| v.to_str().ok());
    if header("X-SpectrumAgent-Boot-Id") != Some(identity.boot_id.as_str())
        || header("X-SpectrumAgent-Pid") != Some(identity.pid.to_string().as_str())
    {
        return Err(ForwardError::new(
            "DATASET_IDENTITY_MISMATCH",
            "建模响应身份不匹配",
        ));
    }
    if let ModelRequest::DownloadClassification { destination, .. } | ModelRequest::DownloadTraining { destination, .. } = request {
        if response.status().is_success() {
            if header("Content-Type") != Some("application/octet-stream") {
                return Err(ForwardError::new("BAD_EXPORT_RESPONSE", "导出响应类型无效"));
            }
            use std::io::Write;
            let destination = std::path::Path::new(destination);
            if destination.exists() {
                return Err(ForwardError::new("EXPORT_DESTINATION_EXISTS", "目标文件已存在，请选择新名称"));
            }
            let temporary = destination.with_extension(format!("{}.part", std::process::id()));
            let mut file = std::fs::OpenOptions::new().write(true).create_new(true).open(&temporary)
                .map_err(|_| ForwardError::new("EXPORT_WRITE_FAILED", "无法创建下载文件"))?;
            let mut response = response;
            let saved = (|| -> std::io::Result<u64> {
                let count = if matches!(request, ModelRequest::DownloadTraining { .. }) {
                    let count = std::io::copy(&mut response.by_ref().take(64 * 1024 * 1024 + 1), &mut file)?;
                    if count > 64 * 1024 * 1024 { return Err(std::io::Error::other("training diagnostic too large")); }
                    count
                } else { std::io::copy(&mut response, &mut file)? };
                file.flush()?;
                file.sync_all()?;
                std::fs::hard_link(&temporary, destination)?;
                Ok(count)
            })();
            drop(file);
            let _ = std::fs::remove_file(&temporary);
            return saved.map(|bytes| json!({"saved":true,"bytes":bytes}))
                .map_err(|_| ForwardError::new("EXPORT_WRITE_FAILED", "下载未完成；服务器产物已保留"));
        }
    }
    if response
        .content_length()
        .is_some_and(|n| n > MAX_RESPONSE_BYTES)
    {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "建模响应超过8MiB"));
    }
    let status = response.status();
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| {
            let mut result = transport_error("read_body", trace, identity, None);
            let timeout = e.kind() == std::io::ErrorKind::TimedOut
                || e.get_ref().and_then(|cause| cause.downcast_ref::<reqwest::Error>()).is_some_and(|cause| cause.is_timeout());
            result.context["timeout"] = json!(timeout);
            result
        })?;
    if bytes.len() as u64 > MAX_RESPONSE_BYTES {
        return Err(ForwardError::new("RESPONSE_TOO_LARGE", "建模响应超过8MiB"));
    }
    let value: Value = serde_json::from_slice(&bytes).map_err(|_| {
        let mut error = ForwardError::new("INVALID_BODY", "建模响应不是JSON");
        error.context = json!({"request_id":trace,"stage":"parse_json"}); error
    })?;
    let canonical = serde_json::to_vec(&value).map_err(|_| invalid())?;
    if [&bytes, &canonical].iter().any(|data| {
        data.windows(identity.token().len())
            .any(|s| s == identity.token().as_bytes())
    }) {
        return Err(ForwardError::new(
            "SENSITIVE_RESPONSE",
            "建模响应包含敏感身份信息",
        ));
    }
    if !status.is_success() {
        return Err(serde_json::from_value(value)
            .unwrap_or_else(|_| ForwardError::new("HTTP_ERROR", "建模引擎返回错误")));
    }
    Ok(value)
}

#[cfg(test)]
mod tests {
    // 测试代码用 unwrap 直接暴露失败；三条 clippy deny 只针对生产路径。
    #![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
    use super::*;
    const ID: &str = "00000000-0000-0000-0000-000000000001";
    #[test]
    fn transport_diagnostic_keeps_safe_stage_and_trace() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        drop(listener);
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,"token":"0123456789abcdef0123456789abcdef",
            "protocol":1,"version":"0.1.0","process_created_at":"2026-10-27T00:00:00.000Z",
            "started_at":"2026-10-27T00:00:00.000Z"
        })).unwrap()).unwrap();
        let error = forward_traced(&identity, &ModelRequest::ListRuns, "m-test-1").unwrap_err();
        assert_eq!(error.error, "TRANSPORT");
        assert_eq!(error.context["request_id"], "m-test-1");
        assert_eq!(error.context["stage"], "send_or_wait_headers");
        assert_eq!(error.context["connect"], true);
        assert!(!serde_json::to_string(&error).unwrap().contains(identity.token()));
    }
    #[test]
    fn classification_actions_are_closed_and_keep_exact_evaluation() {
        for action in ["curves", "map", "pixel", "coefficients", "importance", "compare", "interpret", "register",
                       "baseline", "infer", "task", "cancel", "retry", "export", "threshold", "choices", "evaluate_prediction"] {
            let body = json!({"scope":"pixel","offset":0});
            let request = parse_request(json!({"op":"classification","evaluation_id":ID,"action":action,"body":body})).unwrap();
            let (url, method, sent) = request.destination(14567).unwrap();
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.path(), format!("/api/v1/models/classification/{ID}/{action}"));
            assert_eq!(method, Method::POST);
            assert_eq!(sent, Some(body));
        }
        for value in [
            json!({"op":"classification","evaluation_id":"../x","action":"map","body":{}}),
            json!({"op":"classification","evaluation_id":ID,"action":"http://outside","body":{}}),
            json!({"op":"classification","evaluation_id":ID,"action":"map","body":[]}),
            json!({"op":"download_classification","export_id":ID,"destination":"relative.zip"})
        ] { assert!(parse_request(value).is_err()); }
    }

    #[test]
    fn classification_binary_download_streams_beyond_json_limit() {
        use std::{io::Write, net::TcpListener, thread};
        const TOKEN: &str = "0123456789abcdef0123456789abcdef";
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,"token":TOKEN,"protocol":1,"version":"0.1.0",
            "process_created_at":"2026-10-27T00:00:00.000Z","started_at":"2026-10-27T00:00:00.000Z"
        })).unwrap()).unwrap();
        let length = MAX_RESPONSE_BYTES as usize + 1024;
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            socket.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
            let mut request = [0u8; 4096];
            let read = socket.read(&mut request).unwrap();
            assert!(String::from_utf8_lossy(&request[..read]).contains("Bearer 0123456789abcdef0123456789abcdef"));
            socket.write_all(format!("HTTP/1.1 200 OK\r\nConnection: close\r\nX-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\nContent-Type: application/octet-stream\r\nContent-Length: {length}\r\n\r\n").as_bytes()).unwrap();
            socket.write_all(&vec![42; length]).unwrap();
        });
        let destination = std::env::temp_dir().join(format!("classification-download-{}-{}.zip", std::process::id(), port));
        let parsed = parse_request(json!({"op":"download_classification","export_id":ID,"destination":destination.to_str().unwrap()})).unwrap();
        assert_eq!(forward(&identity, &parsed).unwrap(), json!({"saved":true,"bytes":length}));
        server.join().unwrap();
        let bytes = std::fs::read(&destination).unwrap();
        assert_eq!(bytes.len(), length);
        assert!(bytes.iter().all(|v| *v == 42));
        std::fs::remove_file(destination).unwrap();
    }
    #[test]
    fn training_diagnostic_download_is_fixed_and_writes_complete_payload() {
        use std::{io::Write, net::TcpListener, thread};
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
            "boot_id":"1234abcd","pid":123,"port":port,"token":"0123456789abcdef0123456789abcdef","protocol":1,"version":"0.1.0",
            "process_created_at":"2026-10-27T00:00:00.000Z","started_at":"2026-10-27T00:00:00.000Z"
        })).unwrap()).unwrap();
        let body = "{\"kind\":\"training_diagnostic\",\"complete\":false}";
        let server = thread::spawn(move || {
            let (mut socket, _) = listener.accept().unwrap();
            let mut bytes = [0;4096]; let n = socket.read(&mut bytes).unwrap();
            assert!(String::from_utf8_lossy(&bytes[..n]).starts_with(&format!("GET /api/v1/models/training-jobs/{ID}/export?kind=partial HTTP/1.1")));
            socket.write_all(format!("HTTP/1.1 200 OK\r\nConnection: close\r\nX-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\nContent-Type: application/octet-stream\r\nContent-Length: {}\r\n\r\n{body}",body.len()).as_bytes()).unwrap();
        });
        let path = std::env::temp_dir().join(format!("training-diagnostic-{}-{port}.json",std::process::id()));
        let request = parse_request(json!({"op":"download_training","id":ID,"kind":"partial","destination":path})).unwrap();
        assert_eq!(forward(&identity,&request).unwrap()["bytes"],body.len());
        server.join().unwrap();assert_eq!(std::fs::read_to_string(&path).unwrap(),body);std::fs::remove_file(path).unwrap();
        assert!(parse_request(json!({"op":"download_training","id":ID,"kind":"other","destination":"relative.json"})).is_err());
    }
    #[test]
    fn fixed_operations_and_methods() {
        for (value, method, suffix) in [
            (
                json!({"op":"list_targets","project_id":ID}),
                Method::GET,
                "sample-targets",
            ),
            (
                json!({"op":"put_target","cube_id":ID,"schema_id":ID,"value":2}),
                Method::PUT,
                "00000000-0000-0000-0000-000000000001",
            ),
            (
                json!({"op":"import_targets","project_id":ID,"csv_text":"csv","overwrite":false}),
                Method::POST,
                "import-csv",
            ),
            (json!({"op":"create_run","body":{}}), Method::POST, "runs"),
            (json!({"op":"list_runs"}), Method::GET, "runs"),
            (
                json!({"op":"preflight_run","body":{}}),
                Method::POST,
                "preflight",
            ),
            (json!({"op":"get_run","id":ID}), Method::GET, ID),
            (json!({"op":"lv_sweep","id":ID}), Method::GET, "lv-sweep"),
        ] {
            let request = parse_request(value).unwrap();
            let (url, actual, _) = request.destination(123).unwrap();
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(123));
            assert_eq!(actual, method);
            assert!(url.path().ends_with(suffix));
        }
    }
    #[test]
    fn rejects_general_proxy_extra_fields_traversal_and_oversize() {
        for value in [
            json!({"op":"list_runs","url":"https://example.com"}),
            json!({"op":"get_run","id":"../settings"}),
            json!({"op":"fetch","path":"/health"}),
            json!({"op":"create_run","body":{},"token":"secret"}),
            json!({"op":"import_targets","project_id":ID,"csv_text":"x".repeat(2*1024*1024),"overwrite":false}),
        ] {
            assert!(parse_request(value).is_err());
        }
    }
    #[test]
    fn registry_inference_six_fixed_operations() {
        for (request, method, path) in [
            (
                json!({"op":"register_model","run_id":ID,"name":"PLS"}),
                Method::POST,
                "/api/v1/models/registry".to_string(),
            ),
            (
                json!({"op":"list_models"}),
                Method::GET,
                "/api/v1/models/registry".into(),
            ),
            (
                json!({"op":"set_model_stage","id":ID,"stage":"production"}),
                Method::PUT,
                format!("/api/v1/models/registry/{ID}/stage"),
            ),
            (
                json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":ID,"annotation_version_id":ID}),
                Method::POST,
                "/api/v1/models/inference-runs".into(),
            ),
            (
                json!({"op":"get_inference","id":ID}),
                Method::GET,
                format!("/api/v1/models/inference-runs/{ID}"),
            ),
            (
                json!({"op":"get_inference_map","id":ID}),
                Method::GET,
                format!("/api/v1/models/inference-runs/{ID}/map"),
            ),
        ] {
            let (url, actual, body) = parse_request(request).unwrap().destination(123).unwrap();
            assert_eq!(actual, method);
            assert_eq!(url.path(), path);
            assert_eq!(url.host_str(), Some("127.0.0.1"));
            assert_eq!(url.port(), Some(123));
            if method == Method::POST {
                assert!(body.unwrap().is_object());
            }
        }
    }
    #[test]
    fn snapshot_inference_allows_omitted_references_but_keeps_fixed_route_and_id_checks() {
        for request in [
            json!({"op":"create_inference","model_id":ID,"cube_id":ID}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":null,"annotation_version_id":null}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"annotation_version_id":ID}),
        ] {
            let (url, method, body) = parse_request(request).unwrap().destination(123).unwrap();
            assert_eq!(url.path(), "/api/v1/models/inference-runs");
            assert_eq!(method, Method::POST);
            assert!(body.unwrap()["preprocess_run_id"].is_null());
        }
        for request in [
            json!({"op":"create_inference","model_id":"../model","cube_id":ID}),
            json!({"op":"create_inference","model_id":ID,"cube_id":"../cube"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":"../run"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"annotation_version_id":"../annotation"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"path":"/other"}),
        ] { assert!(parse_request(request).is_err()); }
    }
    #[test]
    fn new_ops_reject_proxy_fields_invalid_stages_and_all_id_traversal() {
        for request in [
            json!({"op":"list_models","url":"https://example.com"}),
            json!({"op":"register_model","run_id":"../health"}),
            json!({"op":"register_model","run_id":ID,"name":""}),
            json!({"op":"set_model_stage","id":ID,"stage":"traffic_split"}),
            json!({"op":"get_inference_map","id":"x?token=secret"}),
            json!({"op":"get_inference","id":"x/y"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":ID,"annotation_version_id":"../x"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":ID,"annotation_version_id":ID,"pipeline":{}}),
        ] {
            assert!(parse_request(request).is_err());
        }
    }
    #[test]
    fn model_operations_reach_loopback_with_native_auth_and_exact_bodies() {
        use std::{io::Write, net::TcpListener, thread};
        const TOKEN: &str = "0123456789abcdef0123456789abcdef";
        for request in [
            json!({"op":"submit_training","id":ID,"body":{"task":"classification"}}),
            json!({"op":"get_training_job","id":ID}),
            json!({"op":"register_model","run_id":ID,"name":"model"}),
            json!({"op":"list_models"}),
            json!({"op":"set_model_stage","id":ID,"stage":"production"}),
            json!({"op":"create_inference","model_id":ID,"cube_id":ID,"preprocess_run_id":ID,"annotation_version_id":ID}),
            json!({"op":"get_inference","id":ID}),
            json!({"op":"get_inference_map","id":ID}),
        ] {
            let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
            let port = listener.local_addr().unwrap().port();
            let identity = crate::handshake::parse(&serde_json::to_vec(&json!({
                "boot_id":"1234abcd","pid":123,"port":port,"token":TOKEN,"protocol":1,"version":"0.1.0",
                "process_created_at":"2026-10-27T00:00:00.000Z","started_at":"2026-10-27T00:00:00.000Z"
            })).unwrap()).unwrap();
            let parsed = parse_request(request).unwrap();
            let (url, method, expected_body) = parsed.destination(port).unwrap();
            let server = thread::spawn(move || {
                let (mut socket, _) = listener.accept().unwrap();
                socket
                    .set_read_timeout(Some(Duration::from_secs(5)))
                    .unwrap();
                let mut data = Vec::new();
                loop {
                    let mut bytes = [0; 4096];
                    let n = socket.read(&mut bytes).unwrap();
                    assert!(n > 0);
                    data.extend_from_slice(&bytes[..n]);
                    if let Some(end) = data.windows(4).position(|s| s == b"\r\n\r\n") {
                        let header = String::from_utf8_lossy(&data[..end]).to_lowercase();
                        let length = header
                            .lines()
                            .find_map(|s| {
                                s.strip_prefix("content-length: ")
                                    .and_then(|s| s.parse::<usize>().ok())
                            })
                            .unwrap_or(0);
                        if data.len() < end + 4 + length {
                            continue;
                        }
                        assert!(header.starts_with(&format!(
                            "{} {} http/1.1",
                            method.as_str().to_lowercase(),
                            url.path()
                        )));
                        assert!(header.contains(&format!("authorization: bearer {TOKEN}")));
                        if let Some(body) = expected_body {
                            assert_eq!(
                                serde_json::from_slice::<Value>(&data[end + 4..]).unwrap(),
                                body
                            );
                        } else {
                            assert_eq!(length, 0);
                        }
                        break;
                    }
                }
                socket.write_all(b"HTTP/1.1 200 OK\r\nConnection: close\r\nX-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\nContent-Length: 11\r\n\r\n{\"ok\":true}").unwrap();
            });
            assert_eq!(forward(&identity, &parsed).unwrap(), json!({"ok":true}));
            server.join().unwrap();
        }
    }
}
