#![cfg(debug_assertions)]
use spectrum_agent::{
    engine_path::EngineSelection,
    handshake,
    state::Phase,
    supervisor::EngineSupervisor,
    win32::{NativeWin32, WaitResult, Win32},
};
use std::{
    fs,
    path::PathBuf,
    sync::Arc,
    time::{Duration, Instant},
};

#[test]
fn real_venv_dual_pid_job_cleanup_and_stale_handshake_recovery()
-> Result<(), Box<dyn std::error::Error>> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!(
        "target/milestone02/dev-lifecycle-{}-{}",
        std::process::id(),
        chrono::Utc::now().timestamp_millis()
    ));
    let native = Arc::new(NativeWin32);
    let mut previous = None;
    for round in 0..2 {
        let selection = EngineSelection::resolve(None, || {
            PathBuf::from(r"E:\unused\resources\backend\app.exe")
        });
        let (handle, _events) =
            EngineSupervisor::start_selected(selection, root.clone(), native.clone())?;
        let deadline = Instant::now() + Duration::from_secs(20);
        let state = loop {
            let state = handle.snapshot()?;
            if state.phase == Phase::Ready {
                break state;
            }
            if state.phase == Phase::Failed || Instant::now() > deadline {
                handle.shutdown_and_join()?;
                return Err(format!("dev start failed: {:?}", state.failure).into());
            }
            std::thread::sleep(Duration::from_millis(25));
        };
        let identity = handshake::parse(&fs::read(root.join("run/handshake.json"))?)?;
        assert_eq!(state.pid, Some(identity.pid));
        if let Some(boot) = previous.as_ref() {
            assert_ne!(boot, &identity.boot_id);
        }
        let day = chrono::Local::now().format("%Y%m%d");
        let log = fs::read_to_string(root.join(format!("logs/shell-{day}.log")))?;
        let record = log
            .lines()
            .filter_map(|line| serde_json::from_str::<serde_json::Value>(line).ok())
            .rfind(|row| row["event"] == "dev_python_identity_verified")
            .ok_or("identity evidence missing")?;
        let launcher = record["launcher_pid"]
            .as_u64()
            .ok_or("launcher PID absent")? as u32;
        assert_ne!(launcher, identity.pid);
        assert_eq!(record["same_job"], true);
        println!(
            "DEV_READY {}",
            serde_json::json!({"round":round,"launcher_pid":launcher,"python_pid":identity.pid,"boot_id":identity.boot_id,"port":identity.port,"same_job":true,"process_created_at_ms":identity.process_created_at_ms})
        );
        handle.shutdown_and_join()?;
        for pid in [launcher, identity.pid] {
            if let Ok(raw) = native.open_dev_process(pid) {
                let state = native.wait(raw, Some(5000));
                native.close(raw).map_err(|e| format!("close: {e:?}"))?;
                assert_eq!(state, Ok(WaitResult::Exited));
            }
        }
        println!(
            "DEV_JOB_CLEANUP {}",
            serde_json::json!({"round":round,"launcher_exited":true,"python_exited":true,"handshake_remaining_observed":root.join("run/handshake.json").exists(),"script_removed_handshake":false})
        );
        previous = Some(identity.boot_id);
    }
    Ok(())
}
