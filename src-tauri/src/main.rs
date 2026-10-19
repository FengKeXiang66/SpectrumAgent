#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod acceptance;

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
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::Instant,
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
    let builder = builder.invoke_handler(tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, datasets_forward]);
    #[cfg(not(debug_assertions))]
    let builder = builder
        .invoke_handler(tauri::generate_handler![engine_status, retry_engine, run_smoke, open_data_directory, datasets_forward]);
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
