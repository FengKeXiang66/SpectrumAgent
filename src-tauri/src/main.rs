#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod acceptance;
mod boot;

use boot::{BootAction, boot_decision};
use serde_json::json;
use spectrum_agent::{
    engine_path::EngineSelection,
    health::{SmokeFailure, SmokeMetrics},
    logging::ShellLog,
    state::Phase,
    supervisor::{EngineSupervisor, Snapshot, SupervisorEvent, SupervisorHandle},
    win32::NativeWin32,
};
use std::{
    collections::{BTreeMap, btree_map::Entry},
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use tauri::{Emitter, Manager};
use tauri_plugin_opener::OpenerExt;

struct Desktop {
    supervisor: SupervisorHandle,
    data_root: PathBuf,
    log: ShellLog,
    closing: AtomicBool,
    exit_allowed: AtomicBool,
}

struct BootGeneration {
    started: Instant,
    started_at: String,
    reload_attempted: bool,
    finished: bool,
}

#[derive(Default)]
struct BootMonitor {
    // This belongs to the live WebView document, not to the engine generation.
    boot_at: Option<String>,
    generations: BTreeMap<u64, BootGeneration>,
}

impl BootMonitor {
    fn document_started(&mut self) {
        self.boot_at = None;
    }

    fn begin_generation(&mut self, generation: u64) -> bool {
        if let Entry::Vacant(entry) = self.generations.entry(generation) {
            entry.insert(BootGeneration {
                started: Instant::now(),
                started_at: chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true),
                reload_attempted: false,
                finished: false,
            });
            true
        } else {
            false
        }
    }

    fn decide(&mut self, generation: u64, elapsed: Duration) -> Option<BootAction> {
        let current = self.generations.get_mut(&generation)?;
        if current.finished {
            return None;
        }
        let action = boot_decision(self.boot_at.is_some(), current.reload_attempted, elapsed);
        if action == BootAction::Reload {
            current.reload_attempted = true;
        }
        if self.boot_at.is_some() || action == BootAction::GiveUp {
            current.finished = true;
        }
        Some(action)
    }
}

#[tauri::command]
fn boot_probe(
    state: tauri::State<'_, Desktop>,
    monitor: tauri::State<'_, Mutex<BootMonitor>>,
) -> Result<(), String> {
    let generation = state.supervisor.snapshot()?.generation_id;
    let timestamp = chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true);
    monitor.lock().map_err(|_| "boot monitor lock poisoned".to_owned())?
        .boot_at = Some(timestamp.clone());
    state.log.event("boot_received", json!({"generation_id":generation,"boot_at":timestamp}))
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn engine_status(state: tauri::State<'_, Desktop>) -> Result<Snapshot, String> {
    state.supervisor.snapshot()
}
#[tauri::command]
fn retry_engine(state: tauri::State<'_, Desktop>) -> Result<(), String> {
    state.supervisor.retry()
}
#[tauri::command]
async fn run_smoke(state: tauri::State<'_, Desktop>) -> Result<SmokeMetrics, SmokeFailure> {
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || supervisor.run_smoke())
        .await
        .map_err(|_| SmokeFailure::Transport)?
}
// Approved D1: the same constrained dataset command serves debug and release.
#[tauri::command]
async fn datasets_forward(
    state: tauri::State<'_, Desktop>,
    request: spectrum_agent::datasets_dev::DatasetRequest,
) -> Result<serde_json::Value, spectrum_agent::datasets_dev::ForwardError> {
    use spectrum_agent::datasets_dev::{ForwardError, forward};
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        if current.generation_id != generation || current.phase != Phase::Ready {
            return Err(ForwardError::new("STALE_RESPONSE", "引擎代次已变化，请重试"));
        }
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "数据请求工作线程失败"))?
}
// TASK-04 §5.7: annotations_forward release registration approved 2026-10-20.
#[tauri::command]
async fn annotations_forward(
    state: tauri::State<'_, Desktop>,
    request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::annotation::ForwardError> {
    use spectrum_agent::annotation::{ForwardError, forward, parse_request};
    // Convert enum deserialization errors into ForwardError before any I/O.
    let request = parse_request(request)?;
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        if current.generation_id != generation || current.phase != Phase::Ready {
            return Err(ForwardError::new("STALE_RESPONSE", "引擎代次已变化，请重试"));
        }
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "数据请求工作线程失败"))?
}
#[tauri::command]
async fn models_forward(
    state: tauri::State<'_, Desktop>, request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::models::ForwardError> {
    use spectrum_agent::models::{ForwardError, forward, parse_request};
    let supervisor=state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation,identity)=supervisor.dataset_identity().map_err(|_|ForwardError::new("ENGINE_NOT_READY","引擎尚未就绪"))?;
        let request=parse_request(request)?;
        let result=forward(&identity,&request);
        let current=supervisor.snapshot().map_err(|_|ForwardError::new("ENGINE_NOT_READY","无法核验引擎代次"))?;
        spectrum_agent::preprocess::validate_generation(generation,&current)?;
        result
    }).await.map_err(|_|ForwardError::new("WORKER_FAILED","建模工作线程失败"))?
}
// TASK-05 §11.5/R13/R14: fixed preprocessing operations, 300s request timeout.
#[tauri::command]
async fn preprocess_forward(
    state: tauri::State<'_, Desktop>,
    request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::preprocess::ForwardError> {
    use spectrum_agent::preprocess::{ForwardError, forward, parse_request, validate_generation};
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let request = parse_request(request)?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        validate_generation(generation, &current)?;
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "数据请求工作线程失败"))?
}
#[tauri::command]
async fn open_data_directory(
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
) -> Result<(), String> {
    let root = state.data_root.to_string_lossy().into_owned();
    tauri::async_runtime::spawn_blocking(move || app.opener().open_path(root, None::<&str>))
        .await
        .map_err(|_| "打开数据目录的工作线程失败。".to_owned())?
        .map_err(|_| "无法打开数据目录。".to_owned())
}

fn exports_directory(root: &std::path::Path, cube_id: &str) -> Result<PathBuf, String> {
    if cube_id.len() != 36
        || !cube_id.bytes().enumerate().all(|(i, c)| {
            if matches!(i, 8 | 13 | 18 | 23) {
                c == b'-'
            } else {
                c.is_ascii_hexdigit()
            }
        })
    {
        return Err("数据集标识必须为规范 UUID。".to_owned());
    }
    Ok(root.join("exports").join(cube_id.to_ascii_lowercase()))
}

#[tauri::command]
async fn open_exports_directory(
    app: tauri::AppHandle,
    state: tauri::State<'_, Desktop>,
    cube_id: String,
) -> Result<(), String> {
    let directory = exports_directory(&state.data_root, &cube_id)?
        .to_string_lossy()
        .into_owned();
    tauri::async_runtime::spawn_blocking(move || app.opener().open_path(directory, None::<&str>))
        .await
        .map_err(|_| "打开投影目录的工作线程失败。".to_owned())?
        .map_err(|_| "无法打开 JSON 所在文件夹。".to_owned())
}

#[cfg(test)]
mod exports_tests {
    use super::exports_directory;

    #[test]
    fn export_folder_is_scoped_to_a_canonical_cube_uuid() -> Result<(), String> {
        let root = std::path::Path::new("E:/isolated-app");
        let id = "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB";
        assert_eq!(
            exports_directory(root, id)?,
            root.join("exports").join(id.to_ascii_lowercase())
        );
        Ok(())
    }

    #[test]
    fn export_folder_rejects_paths_and_malformed_ids() {
        for id in [
            "../other",
            "E:/other",
            "",
            "abcdefab-cdef-abcd-efab-cdefabcdefa/",
            "../00000000000000000000000000000000",
        ] {
            assert!(exports_directory(std::path::Path::new("E:/isolated-app"), id).is_err());
        }
    }
}

// TASK-07 R11/R12: fixed agent operations, collected SSE, same generation gate.
#[tauri::command]
async fn agent_forward(
    state: tauri::State<'_, Desktop>,
    request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::agent::ForwardError> {
    use spectrum_agent::agent::{ForwardError, forward, parse_request, validate_generation};
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let request = parse_request(request)?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        validate_generation(generation, &current)?;
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "请求工作线程失败"))?
}

#[tauri::command]
async fn settings_forward(
    state: tauri::State<'_, Desktop>,
    request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::settings::ForwardError> {
    use spectrum_agent::settings::{ForwardError, forward, parse_request, validate_generation};
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let request = parse_request(request)?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        validate_generation(generation, &current)?;
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "请求工作线程失败"))?
}

#[tauri::command]
async fn annotations_draft_forward(
    state: tauri::State<'_, Desktop>,
    request: serde_json::Value,
) -> Result<serde_json::Value, spectrum_agent::annotations_draft::ForwardError> {
    use spectrum_agent::annotations_draft::{ForwardError, forward, parse_request, validate_generation};
    let supervisor = state.supervisor.clone();
    tauri::async_runtime::spawn_blocking(move || {
        let (generation, identity) = supervisor.dataset_identity()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "数据引擎尚未就绪"))?;
        let request = parse_request(request)?;
        let result = forward(&identity, &request);
        let current = supervisor.snapshot()
            .map_err(|_| ForwardError::new("ENGINE_NOT_READY", "无法核验当前引擎代次"))?;
        validate_generation(generation, &current)?;
        result
    }).await.map_err(|_| ForwardError::new("WORKER_FAILED", "请求工作线程失败"))?
}

fn begin_shutdown(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<Desktop>() else {
        return;
    };
    if state.closing.swap(true, Ordering::AcqRel) {
        return;
    }
    let supervisor = state.supervisor.clone();
    let app = app.clone();
    let _ = supervisor.stop();
    tauri::async_runtime::spawn_blocking(move || {
        let result = supervisor.shutdown_and_join();
        if let Some(state) = app.try_state::<Desktop>() {
            let _ = state
                .log
                .event("host_cleanup_completed", json!({"success":result.is_ok()}));
            // Opt-in acceptance only: let the existing bounded observer capture
            // React's Stopping DOM after engine cleanup, without blocking the UI.
            if acceptance::enabled() {
                let _ = state.log.event(
                    "acceptance_close_capture_window",
                    json!({"duration_ms":350}),
                );
                std::thread::sleep(std::time::Duration::from_millis(350));
            }
            state.exit_allowed.store(true, Ordering::Release);
        }
        app.exit(if result.is_ok() { 0 } else { 1 });
    });
}

fn show_window(app: &tauri::AppHandle, log: &ShellLog, generation: u64, activate: bool) {
    if let Some(window) = app.get_webview_window("main") {
        let shown = window.show().is_ok();
        let visible = window.is_visible().ok();
        if activate {
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
        let _ = log.event(
            "window_shown",
            json!({"generation_id":generation,"success":shown,"visible":visible,"activated":activate}),
        );
        start_boot_monitor(app, log, generation);
    }
}

fn start_boot_monitor(app: &tauri::AppHandle, log: &ShellLog, generation: u64) {
    let Some(state) = app.try_state::<Mutex<BootMonitor>>() else { return; };
    let Ok(mut monitor) = state.lock() else { return; };
    if !monitor.begin_generation(generation) { return; }
    drop(monitor);
    let app = app.clone();
    let thread_log = log.clone();
    let done = Arc::new(AtomicBool::new(false));
    let result = std::thread::Builder::new().name(format!("boot-monitor-{generation}")).spawn(move || {
        while !done.load(Ordering::Acquire) {
            let host = app.clone();
            let finished = done.clone();
            if app.run_on_main_thread(move || {
                let Some(desktop) = host.try_state::<Desktop>() else { finished.store(true, Ordering::Release); return; };
                let active = desktop.supervisor.snapshot().is_ok_and(|snapshot| snapshot.generation_id == generation);
                if !active || desktop.closing.load(Ordering::Acquire) { finished.store(true, Ordering::Release); return; }
                let Some(state) = host.try_state::<Mutex<BootMonitor>>() else { finished.store(true, Ordering::Release); return; };
                let Ok(mut monitor) = state.lock() else { finished.store(true, Ordering::Release); return; };
                let Some(current) = monitor.generations.get(&generation) else { finished.store(true, Ordering::Release); return; };
                let elapsed = current.started.elapsed();
                let Some(action) = monitor.decide(generation, elapsed) else { finished.store(true, Ordering::Release); return; };
                if monitor.boot_at.is_some() { finished.store(true, Ordering::Release); return; }
                let Some(window) = host.get_webview_window("main") else { finished.store(true, Ordering::Release); return; };
                match action {
                    BootAction::Wait => {}
                    BootAction::Reload => {
                        let result = window.eval("location.reload()");
                        let _ = desktop.log.event("boot_reload", json!({"generation_id":generation,
                            "elapsed_ms":elapsed.as_millis(),"success":result.is_ok(),"error":result.err().map(|e|e.to_string())}));
                    }
                    BootAction::GiveUp => {
                        finished.store(true, Ordering::Release);
                        let _ = desktop.log.event("boot_timeout_final", json!({"generation_id":generation,"elapsed_ms":elapsed.as_millis()}));
                        let title = "SpectrumAgent — 页面未加载，请查看日志";
                        let result = window.set_title(title);
                        let _ = desktop.log.event("boot_title_changed", json!({"generation_id":generation,"title":title,
                            "success":result.is_ok(),"error":result.err().map(|e|e.to_string())}));
                        let Some(current) = monitor.generations.get(&generation) else { return; };
                        let failure = json!({"generation_id":generation,"started_at":current.started_at,
                            "boot_at":monitor.boot_at,"reload_attempted":current.reload_attempted,
                            "webview_version":tauri::webview_version().unwrap_or_else(|error|format!("unavailable: {error}")),
                            "url":window.url().map(|url|url.to_string()).unwrap_or_else(|error|format!("unavailable: {error}"))});
                        let path = desktop.log.directory().join("boot_failure.json");
                        let result = serde_json::to_vec_pretty(&failure).map_err(std::io::Error::other)
                            .and_then(|bytes|std::fs::write(&path,bytes));
                        let _ = desktop.log.event("boot_failure_written", json!({"generation_id":generation,"path":path,
                            "success":result.is_ok(),"error":result.err().map(|e|e.to_string())}));
                    }
                }
            }).is_err() { break; }
            std::thread::sleep(Duration::from_millis(100));
        }
    });
    if let Err(error) = result {
        let _ = thread_log.event("boot_monitor_failed", json!({"generation_id":generation,"error":error.to_string()}));
    }
}

#[cfg(test)]
mod boot_monitor_tests {
    use super::{BootAction, BootMonitor};
    use std::time::Duration;

    #[test]
    fn reload_budget_is_independent_and_activations_do_not_reset_it() {
        let mut monitor = BootMonitor::default();
        assert!(monitor.begin_generation(1));
        assert_eq!(monitor.decide(1, Duration::from_secs(5)), Some(BootAction::Reload));
        assert!(!monitor.begin_generation(1));
        monitor.document_started(); // The automatic reload preserves its generation budget.
        assert_eq!(monitor.decide(1, Duration::from_secs(10)), Some(BootAction::Wait));
        assert_eq!(monitor.decide(1, Duration::from_secs(15)), Some(BootAction::GiveUp));
        assert_eq!(monitor.decide(1, Duration::from_secs(60)), None);
        assert!(monitor.begin_generation(2));
        assert_eq!(monitor.decide(2, Duration::from_secs(5)), Some(BootAction::Reload));
    }

    #[test]
    fn engine_retry_keeps_healthy_document_until_real_navigation() {
        let mut monitor = BootMonitor { boot_at: Some("document boot timestamp".to_owned()), ..BootMonitor::default() };
        for generation in [1, 2, 99] {
            assert!(monitor.begin_generation(generation));
            // Wait produces no reload/title/failure-file operation in the caller.
            assert_eq!(monitor.decide(generation, Duration::from_secs(60)), Some(BootAction::Wait));
            assert_eq!(monitor.decide(generation, Duration::from_secs(120)), None);
        }
        monitor.document_started();
        assert!(monitor.boot_at.is_none());
        assert!(monitor.begin_generation(100));
        assert_eq!(monitor.decide(100, Duration::from_secs(5)), Some(BootAction::Reload));
    }
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let started = Instant::now();
    let root = PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA 缺失")?)
        .join("SpectrumAgent");
    let log = ShellLog::new(&root)?;
    log.event("shell_started", json!({"pid":std::process::id()}))?;
    let pending_activation = Arc::new(AtomicBool::new(false));
    let pending_callback = pending_activation.clone();
    let callback_log = log.clone();
    let setup_log = log.clone();
    let builder = tauri::Builder::default()
        .manage(Mutex::new(BootMonitor::default()))
        .on_page_load(|webview, payload| {
            if webview.label() == "main" && payload.event() == tauri::webview::PageLoadEvent::Started
                && let Some(state) = webview.app_handle().try_state::<Mutex<BootMonitor>>()
                && let Ok(mut monitor) = state.lock() {
                monitor.document_started();
            }
        })
        // Must be the first registered plugin; it acquires the lock before setup/spawn.
        .plugin(tauri_plugin_single_instance::init(move |app, _args, _cwd| {
            pending_callback.store(true, Ordering::Release);
            let _ = callback_log.event("single_instance_activation", json!({}));
            if let Some(state) = app.try_state::<Desktop>() {
                let _ = state.supervisor.activate();
                if let Ok(status) = state.supervisor.snapshot()
                    && matches!(status.phase, Phase::Ready | Phase::Failed) {
                    show_window(app, &callback_log, status.generation_id, true);
                    pending_callback.store(false, Ordering::Release);
                }
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init());
    #[cfg(debug_assertions)]
    let builder = builder.invoke_handler(tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, open_exports_directory, boot_probe, datasets_forward, annotations_forward, preprocess_forward, agent_forward, settings_forward, annotations_draft_forward, models_forward]);
    #[cfg(not(debug_assertions))]
    let builder = builder
        .invoke_handler(tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, open_exports_directory, boot_probe, datasets_forward, annotations_forward, preprocess_forward, agent_forward, settings_forward, annotations_draft_forward, models_forward]);
    let app = builder.setup(move |app| {
            setup_log.event("single_instance_lock_acquired", json!({}))?;
            let resource = app.path().resolve("resources/backend/app.exe", tauri::path::BaseDirectory::Resource)?;
            let selection = EngineSelection::resolve(None, || resource);
            let (handle, events) = EngineSupervisor::start_selected(selection, root.clone(), Arc::new(NativeWin32))?;
            app.manage(Desktop { supervisor: handle.clone(), data_root: root,
                log: setup_log.clone(), closing: AtomicBool::new(false), exit_allowed: AtomicBool::new(false) });
            if let Some(state) = app.try_state::<Desktop>() {
                acceptance::start(app.handle().clone(), state.data_root.clone(), setup_log.clone(), started)?;
            }
            if pending_activation.load(Ordering::Acquire) { let _ = handle.activate(); }
            let host = app.handle().clone();
            let event_log = setup_log.clone();
            std::thread::Builder::new().name("desktop-status-events".to_owned()).spawn(move || {
                let mut last_phase = Phase::Starting;
                for event in events {
                    if let SupervisorEvent::Status(snapshot) = event {
                        let _ = host.emit("engine-status", &snapshot);
                        if matches!(snapshot.phase, Phase::Ready | Phase::Failed) {
                            let first = snapshot.phase != last_phase;
                            let activate = pending_activation.swap(false, Ordering::AcqRel);
                            if first || activate {
                                show_window(&host, &event_log, snapshot.generation_id, first || activate);
                                let _ = event_log.event("desktop_presented", json!({"generation_id":snapshot.generation_id,"phase":snapshot.phase,"elapsed_ms":started.elapsed().as_millis()}));
                            }
                        } else if snapshot.phase == Phase::Starting
                            && let Some(window) = host.get_webview_window("main") {
                            let hidden = window.hide().is_ok();
                            let _ = event_log.event("window_hidden", json!({"generation_id":snapshot.generation_id,"success":hidden,"visible":window.is_visible().ok()}));
                        }
                        last_phase = snapshot.phase;
                    }
                }
            })?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                begin_shutdown(window.app_handle());
            }
        })
        .build(tauri::generate_context!())?;
    app.run(|app, event| {
        if let tauri::RunEvent::ExitRequested { api, .. } = event
            && let Some(state) = app.try_state::<Desktop>()
            && !state.exit_allowed.load(Ordering::Acquire)
        {
            api.prevent_exit();
            begin_shutdown(app);
        }
    });
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("SpectrumAgent 外壳启动失败：{error}");
        std::process::exit(1);
    }
}
