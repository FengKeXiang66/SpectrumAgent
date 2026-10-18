//! Opt-in, bounded diagnostics for acceptance. No extra command/capability or dependency.
//! Normal runs do not start a timer, evaluate this script, or create audit files.
use serde_json::json;
use spectrum_agent::{handshake, logging::ShellLog};
use std::{
    fs,
    io::Write,
    path::PathBuf,
    sync::{Arc, Mutex},
    time::{Duration, Instant},
};
use tauri::Manager;

const READ_DOCUMENT: &str = r#"(() => {
  if (!window.__spectrumAcceptanceInvoke) {
    window.__spectrumAcceptanceInvoke = {pending:true};
    window.__TAURI_INTERNALS__.invoke('engine_status').then(
      value => window.__spectrumAcceptanceInvoke = {ok:true,value},
      () => window.__spectrumAcceptanceInvoke = {ok:false});
  }
  const storage = s => Array.from({length:s.length},(_,i)=>s.key(i)).sort().map(k=>[k,s.getItem(k)]);
  return {url:window.location.href,scripts:Array.from(document.scripts).map(s=>s.src),
    html:document.documentElement.outerHTML,
    fields:Array.from(document.querySelectorAll('input,textarea,select')).map(e=>({id:e.id,value:e.value,disabled:e.disabled})),
    localStorage:storage(localStorage),sessionStorage:storage(sessionStorage),
    phase:document.querySelector('[data-phase]')?.getAttribute('data-phase') ?? 'Starting',
    invoke:window.__spectrumAcceptanceInvoke,
    interactive:document.querySelector('[data-phase="Ready"] #agent-input:not(:disabled)') !== null};
})()"#;

pub fn enabled() -> bool {
    std::env::var_os("SPECTRUM_ACCEPTANCE_PROBE").as_deref() == Some(std::ffi::OsStr::new("1"))
}

pub fn start(
    app: tauri::AppHandle,
    root: PathBuf,
    log: ShellLog,
    started: Instant,
) -> std::io::Result<()> {
    if !enabled() {
        return Ok(());
    }
    let directory = root.join("acceptance");
    fs::create_dir_all(&directory)?;
    let output = Arc::new(Mutex::new(
        fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(directory.join(format!("dom-{}.jsonl", std::process::id())))?,
    ));
    let secrets = Arc::new(Mutex::new(Vec::<String>::new()));
    log.event(
        "acceptance_probe_started",
        json!({"pid":std::process::id(),"duration_ms":45000,"period_ms":100}),
    )?;
    std::thread::Builder::new().name("bounded-acceptance-observer".to_owned()).spawn(move || {
        for tick in 0..450 {
            if let Ok(bytes) = fs::read(root.join("run").join("handshake.json"))
                && let Ok(identity) = handshake::parse(&bytes)
                && let Ok(mut tokens) = secrets.lock()
                && !tokens.iter().any(|s| s == identity.token()) { tokens.push(identity.token().to_owned()); }
            let host = app.clone(); let audit_log = log.clone(); let file = output.clone(); let tokens = secrets.clone();
            let queued = Instant::now();
            if app.run_on_main_thread(move || {
                let Some(window) = host.get_webview_window("main") else { return; };
                let _ = audit_log.event("acceptance_heartbeat",json!({"pid":std::process::id(),"tick":tick,"elapsed_ms":started.elapsed().as_millis(),"queue_ms":queued.elapsed().as_millis(),"visible":window.is_visible().ok()}));
                let callback_log = audit_log.clone();
                let _ = window.eval_with_callback(READ_DOCUMENT, move |raw| {
                    let samples = match tokens.lock() { Ok(samples) => samples, Err(_) => return };
                    let hits = samples.iter().filter(|token| raw.contains(token.as_str())).count();
                    let bearer = raw.to_ascii_lowercase().contains("authorization: bearer");
                    let Ok(document) = serde_json::from_str::<serde_json::Value>(&raw) else {
                        let _ = callback_log.event("acceptance_dom_invalid",json!({"tick":tick})); return;
                    };
                    let elapsed = started.elapsed().as_millis();
                    let _ = callback_log.event("acceptance_dom_audit",json!({"pid":std::process::id(),"tick":tick,"elapsed_ms":elapsed,"bytes":raw.len(),"token_samples":samples.len(),"exact_token_hits":hits,"authorization_bearer":bearer,"phase":document["phase"],"interactive":document["interactive"],"invoke":document["invoke"]}));
                    // Scan the original callback string before archiving. Never archive a leaked secret.
                    if hits == 0 && !bearer && let Ok(mut writer) = file.lock() {
                        let record = json!({"pid":std::process::id(),"tick":tick,"elapsed_ms":elapsed,"document":document});
                        let _ = serde_json::to_writer(&mut *writer,&record);
                        let _ = writer.write_all(b"\n"); let _ = writer.flush();
                    }
                });
            }).is_err() { break; }
            std::thread::sleep(Duration::from_millis(100));
        }
        let _ = log.event("acceptance_probe_finished",json!({"pid":std::process::id()}));
    })?;
    Ok(())
}
