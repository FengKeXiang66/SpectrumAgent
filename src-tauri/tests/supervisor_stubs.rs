#![cfg(feature = "test-probes")]
use spectrum_agent::{
    state::{FailureKind, Phase},
    supervisor::{EngineSupervisor, ExitReason, Snapshot, SupervisorConfig, SupervisorHandle},
    win32::{NativeWin32, SpawnRequest},
};
use std::{
    fs,
    net::TcpStream,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicU64, Ordering},
    },
    time::{Duration, Instant},
};

static NEXT: AtomicU64 = AtomicU64::new(1);
type TestResult = Result<(), Box<dyn std::error::Error>>;

struct Running {
    handle: SupervisorHandle,
    root: PathBuf,
}
impl Drop for Running {
    fn drop(&mut self) {
        let _ = self.handle.shutdown_and_join();
    }
}

fn prepare() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target/stub-runtime")
        .join(format!(
            "{}-{}-{}",
            std::process::id(),
            chrono::Utc::now().timestamp_millis(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    fs::create_dir_all(&root)?;
    Ok(root)
}
fn start(root: PathBuf, mode: &str) -> Result<Running, Box<dyn std::error::Error>> {
    let config = SupervisorConfig {
        process: SpawnRequest {
            exe: PathBuf::from(env!("CARGO_BIN_EXE_supervisor-stub")),
            args: vec![mode.into(), root.as_os_str().to_owned()],
        },
        data_root: root.clone(),
    };
    let (handle, _events) = EngineSupervisor::start(config, Arc::new(NativeWin32))?;
    Ok(Running { handle, root })
}
fn wait(
    running: &Running,
    phase: Phase,
    timeout: Duration,
) -> Result<Snapshot, Box<dyn std::error::Error>> {
    let deadline = Instant::now() + timeout;
    loop {
        let snapshot = running.handle.snapshot()?;
        if snapshot.phase == phase && (phase != Phase::Failed || snapshot.cleanup_complete) {
            return Ok(snapshot);
        }
        if Instant::now() >= deadline {
            return Err(
                format!("state wait expired: wanted={phase:?}, observed={snapshot:?}").into(),
            );
        }
        std::thread::sleep(Duration::from_millis(10));
    }
}
fn logs(running: &Running) -> Result<Vec<serde_json::Value>, Box<dyn std::error::Error>> {
    let mut result = vec![];
    for entry in fs::read_dir(running.root.join("logs"))? {
        let entry = entry?;
        if entry.file_name().to_string_lossy().starts_with("shell-") {
            for line in fs::read_to_string(entry.path())?.lines() {
                assert!(!line.contains("abcdef0123456789abcdef0123456789"));
                result.push(serde_json::from_str(line)?);
            }
        }
    }
    Ok(result)
}

#[test]
fn stub_tolerates_disconnected_health_client() -> TestResult {
    let running = start(prepare()?, "ready")?;
    let ready = wait(&running, Phase::Ready, Duration::from_secs(5))?;
    let port = ready.port.ok_or("port missing")?;
    drop(TcpStream::connect(("127.0.0.1", port))?);
    std::thread::sleep(Duration::from_millis(250));
    assert_eq!(running.handle.snapshot()?.phase, Phase::Ready);
    println!("STUB transport: client disconnected without a request; stub remains Ready");
    Ok(())
}

#[test]
fn stub_ready_then_stop_has_no_listening_port_and_separate_app_exit() -> TestResult {
    let running = start(prepare()?, "ready")?;
    let ready = wait(&running, Phase::Ready, Duration::from_secs(5))?;
    let port = ready.port.ok_or("port missing")?;
    running.handle.shutdown_and_join()?;
    assert!(TcpStream::connect(("127.0.0.1", port)).is_err());
    let log = logs(&running)?;
    assert_eq!(
        log.iter()
            .filter(|line| line["event"] == "app_exit")
            .count(),
        1
    );
    assert!(!log.iter().any(|line| line["to"] == "app_exit"));
    assert!(!log.iter().any(|line| line["event"] == "engine_failure"));
    println!(
        "STUB ready/stop: pid={:?} port={port} phase=Stopping port_absent=true app_exit=1 token_leaks=0",
        ready.pid
    );
    Ok(())
}

#[test]
fn stub_immediate_exit_reports_actual_exit_code() -> TestResult {
    let start_time = Instant::now();
    let running = start(prepare()?, "exit")?;
    let failed = wait(&running, Phase::Failed, Duration::from_secs(5))?;
    let failure = failed.failure.ok_or("failure missing")?;
    assert_eq!(failure.kind, FailureKind::ExitedBeforeReady);
    assert!(matches!(
        failure.exit_reason,
        ExitReason::ProcessExit { code: 23 }
    ));
    println!(
        "STUB immediate-exit: pid={:?} code=23 kind=ExitedBeforeReady elapsed_ms={}",
        failed.pid,
        start_time.elapsed().as_millis()
    );
    Ok(())
}

#[test]
fn stub_alive_without_handshake_times_out_after_actual_30_seconds() -> TestResult {
    let start_time = Instant::now();
    let running = start(prepare()?, "timeout")?;
    running.handle.activate()?;
    let failed = wait(&running, Phase::Failed, Duration::from_secs(34))?;
    let elapsed = start_time.elapsed();
    assert_eq!(
        failed.failure.ok_or("failure missing")?.kind,
        FailureKind::StartupTimeout
    );
    assert!(failed.pending_activation);
    assert!((Duration::from_millis(29500)..Duration::from_secs(33)).contains(&elapsed));
    println!(
        "STUB no-handshake: pid={:?} kind=StartupTimeout elapsed_ms={} pending_activation=true",
        failed.pid,
        elapsed.as_millis()
    );
    Ok(())
}

#[test]
fn stub_wrong_health_boot_id_fails_only_after_child_identity_validation() -> TestResult {
    let running = start(prepare()?, "wrong-boot")?;
    let failed = wait(&running, Phase::Failed, Duration::from_secs(5))?;
    let failure = failed.failure.ok_or("failure missing")?;
    assert_eq!(failure.kind, FailureKind::HealthIdentityMismatch);
    assert!(matches!(
        failure.exit_reason,
        ExitReason::IdentityMismatch {
            layer: "health_boot_id"
        }
    ));
    assert!(
        logs(&running)?
            .iter()
            .any(|line| line["event"] == "handshake_identity_verified")
    );
    println!(
        "STUB mismatch: pid={:?} child_pid_and_created_at=verified failure_layer=health_boot_id kind=HealthIdentityMismatch",
        failed.pid
    );
    Ok(())
}

#[test]
fn stub_exit_after_ready_produces_exactly_one_failure_transition() -> TestResult {
    let running = start(prepare()?, "ready-exit")?;
    wait(&running, Phase::Ready, Duration::from_secs(5))?;
    fs::write(running.root.join("ready-ack"), b"parent_observed_Ready")?;
    let failed = wait(&running, Phase::Failed, Duration::from_secs(5))?;
    assert!(matches!(
        failed
            .failure
            .as_ref()
            .ok_or("failure missing")?
            .exit_reason,
        ExitReason::ProcessExit { code: 24 }
    ));
    assert_eq!(
        failed.failure.ok_or("failure missing")?.kind,
        FailureKind::EngineExitedAfterReady
    );
    let count = logs(&running)?
        .iter()
        .filter(|line| {
            line["event"] == "state_transition" && line["from"] == "Ready" && line["to"] == "Failed"
        })
        .count();
    assert_eq!(count, 1);
    println!(
        "STUB ready-exit: pid={:?} Ready->Failed(EngineExitedAfterReady) count={count}",
        failed.pid
    );
    Ok(())
}

#[test]
fn retry_waits_for_cleanup_and_late_a_exit_cannot_change_b() -> TestResult {
    let root = prepare()?;
    fs::write(root.join("mode.txt"), "exit")?;
    let running = start(root, "from-file")?;
    let a = wait(&running, Phase::Failed, Duration::from_secs(5))?;
    fs::write(running.root.join("mode.txt"), "ready")?;
    running.handle.retry()?;
    let b = wait(&running, Phase::Ready, Duration::from_secs(5))?;
    assert_eq!(b.generation_id, a.generation_id + 1);
    running.handle.inject_old_exit_for_test(a.generation_id)?;
    std::thread::sleep(Duration::from_millis(100));
    assert_eq!(running.handle.snapshot()?.phase, Phase::Ready);
    assert!(
        logs(&running)?
            .iter()
            .any(|line| line["event"] == "stale_generation_result_discarded")
    );
    println!(
        "STUB retry: A_generation={} B_generation={} late_A_exit=discarded B=Ready",
        a.generation_id, b.generation_id
    );
    Ok(())
}

#[test]
fn absent_executable_immediately_fails_and_does_not_clean_invalid_old_handshake() -> TestResult {
    let root = prepare()?;
    fs::create_dir_all(root.join("run"))?;
    let original = b"{invalid_json";
    fs::write(root.join("run/handshake.json"), original)?;
    let config = SupervisorConfig {
        process: SpawnRequest {
            exe: root.join("absent.exe"),
            args: vec![],
        },
        data_root: root.clone(),
    };
    let start_time = Instant::now();
    let (handle, _events) = EngineSupervisor::start(config, Arc::new(NativeWin32))?;
    let running = Running { handle, root };
    let failed = wait(&running, Phase::Failed, Duration::from_secs(2))?;
    let failure = failed.failure.ok_or("failure missing")?;
    assert_eq!(failure.kind, FailureKind::SpawnFailed);
    assert!(failure.preexisting_handshake_invalid.is_some());
    assert!(matches!(
        failure.exit_reason,
        ExitReason::Win32 { code: 2, .. }
    ));
    assert_eq!(fs::read(running.root.join("run/handshake.json"))?, original);
    assert!(start_time.elapsed() < Duration::from_secs(1));
    println!(
        "MISSING PATH (constructor injection): kind=SpawnFailed elapsed_ms={} preexisting_handshake_invalid=retained bytes_unchanged=true",
        start_time.elapsed().as_millis()
    );
    Ok(())
}
