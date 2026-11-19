//! Acceptance harness only, not the Tauri host or product single-instance boundary.
use serde_json::json;
use spectrum_agent::{
    engine_path::EngineSelection, supervisor::EngineSupervisor, win32::NativeWin32,
};
use std::{
    io::{self, BufRead, Write},
    path::PathBuf,
    sync::Arc,
};

fn emit(value: &impl serde::Serialize) -> io::Result<()> {
    let stdout = io::stdout();
    let mut output = stdout.lock();
    serde_json::to_writer(&mut output, value)?;
    writeln!(output)?;
    output.flush()
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args_os().skip(1);
    let mut injected = None;
    let mut resource = None;
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--injected-exe") => {
                injected = Some(PathBuf::from(args.next().ok_or("missing injected path")?))
            }
            Some("--resource-exe") => {
                resource = Some(PathBuf::from(
                    args.next().ok_or("missing resolved resource path")?,
                ))
            }
            _ => return Err("unknown probe argument".into()),
        }
    }
    let resource = resource.ok_or("probe requires an explicit host-resolved resource path")?;
    let selection = EngineSelection::resolve(injected, || resource);
    emit(
        &json!({"probe_pid":std::process::id(),"debug_assertions":cfg!(debug_assertions),"selection":selection}),
    )?;
    let root = PathBuf::from(std::env::var_os("LOCALAPPDATA").ok_or("LOCALAPPDATA is missing")?)
        .join("SpectrumAgent");
    let (handle, events) =
        EngineSupervisor::start_selected(selection, root, Arc::new(NativeWin32))?;
    let output = std::thread::spawn(move || -> io::Result<()> {
        for event in events {
            emit(&event)?;
        }
        Ok(())
    });
    let input_result = (|| -> Result<(), Box<dyn std::error::Error>> {
        for line in io::stdin().lock().lines() {
            match line?.as_str() {
                "retry" => handle.retry()?,
                "status" => emit(&json!({"snapshot":handle.snapshot()?}))?,
                "smoke" => emit(&json!({"smoke":handle.run_smoke()}))?,
                "stop" => break,
                _ => return Err("unknown probe command".into()),
            }
        }
        Ok(())
    })();
    handle.shutdown_and_join()?;
    drop(handle);
    output.join().map_err(|_| "probe output worker failed")??;
    input_result
}

fn main() {
    if let Err(error) = run() {
        eprintln!("监督器验收入口失败：{error}");
        std::process::exit(1);
    }
}
