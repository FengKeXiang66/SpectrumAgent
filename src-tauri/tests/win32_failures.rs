use spectrum_agent::{
    process::ManagedProcess,
    state::FailureKind,
    win32::{
        CreatedProcess, CreationParameters, RawHandle, SpawnRequest, WaitResult, Win32, WinError,
    },
};
use std::{
    collections::BTreeMap,
    path::PathBuf,
    sync::{Arc, Mutex},
};

struct Fake {
    fail: &'static str,
    calls: Mutex<Vec<String>>,
}

impl Fake {
    fn record(&self, api: &'static str, detail: &str) -> Result<(), WinError> {
        self.calls
            .lock()
            .map_err(|_| WinError {
                api: "test_mutex",
                code: 1,
            })?
            .push(format!("{api}{detail}"));
        if self.fail.split('+').any(|name| name == api) {
            return Err(WinError { api, code: 1234 });
        }
        Ok(())
    }
    fn calls(&self) -> Result<Vec<String>, String> {
        self.calls
            .lock()
            .map(|v| v.clone())
            .map_err(|_| "poisoned test recorder".to_owned())
    }
}

#[test]
fn unconfirmed_cleanup_is_preserved_and_blocks_retry() -> Result<(), String> {
    use spectrum_agent::state::Phase;
    use spectrum_agent::supervisor::{EngineSupervisor, SupervisorConfig};
    use std::time::{Duration, Instant};
    let fake = Arc::new(Fake {
        fail: "ResumeThread+WaitForSingleObject",
        calls: Mutex::new(vec![]),
    });
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(format!(
        "target/fake-cleanup-{}-{}",
        std::process::id(),
        chrono::Utc::now().timestamp_millis()
    ));
    let config = SupervisorConfig {
        process: SpawnRequest {
            exe: PathBuf::from(r"E:\bundle\app.exe"),
            args: vec![],
        },
        data_root: root,
    };
    let (handle, _events) = EngineSupervisor::start(config, fake).map_err(|e| e.to_string())?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        let state = handle.snapshot()?;
        if state.phase == Phase::Failed {
            assert!(!state.cleanup_complete);
            break;
        }
        if Instant::now() > deadline {
            handle.shutdown_and_join()?;
            return Err("injected failure did not reach Failed".to_owned());
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    handle.retry()?;
    std::thread::sleep(Duration::from_millis(50));
    assert_eq!(handle.snapshot()?.generation_id, 1);
    assert_eq!(handle.snapshot()?.phase, Phase::Failed);
    handle.shutdown_and_join()?;
    println!(
        "CLEANUP FAILURE: WaitForSingleObject error retained; cleanup_complete=false; retry blocked at generation=1"
    );
    Ok(())
}

impl Win32 for Fake {
    fn create_suspended(&self, request: &CreationParameters) -> Result<CreatedProcess, WinError> {
        assert_eq!(request.inherit_handles, 0);
        assert_eq!(request.flags, 0x08000004);
        assert_eq!(request.directory, PathBuf::from(r"E:\bundle"));
        assert_eq!(request.application.last(), Some(&0));
        assert_eq!(request.command_line.last(), Some(&0));
        self.record(
            "CreateProcessW",
            &format!(
                "(exe={},cwd={},inherit={},flags=0x{:08x},mutable_utf16={:?})",
                request.exe.display(),
                request.directory.display(),
                request.inherit_handles,
                request.flags,
                request.command_line
            ),
        )?;
        Ok(CreatedProcess {
            process: 101,
            thread: 102,
            pid: 9000,
        })
    }
    fn create_job(&self) -> Result<RawHandle, WinError> {
        self.record("CreateJobObjectW", "(security=NULL)")?;
        Ok(103)
    }
    fn set_kill_on_close(&self, job: RawHandle) -> Result<(), WinError> {
        self.record(
            "SetInformationJobObject",
            &format!("({job},KILL_ON_JOB_CLOSE)"),
        )
    }
    fn assign(&self, job: RawHandle, process: RawHandle) -> Result<(), WinError> {
        self.record("AssignProcessToJobObject", &format!("({job},{process})"))
    }
    fn resume(&self, thread: RawHandle) -> Result<(), WinError> {
        self.record("ResumeThread", &format!("({thread})"))
    }
    fn terminate_process(&self, process: RawHandle) -> Result<(), WinError> {
        self.record("TerminateProcess", &format!("({process})"))
    }
    fn terminate_job(&self, job: RawHandle) -> Result<(), WinError> {
        self.record("TerminateJobObject", &format!("({job})"))
    }
    fn wait(&self, process: RawHandle, timeout: Option<u32>) -> Result<WaitResult, WinError> {
        self.record("WaitForSingleObject", &format!("({process},{timeout:?})"))?;
        Ok(WaitResult::Exited)
    }
    fn exit_code(&self, process: RawHandle) -> Result<u32, WinError> {
        self.record("GetExitCodeProcess", &format!("({process})"))?;
        Ok(1)
    }
    fn created_at_ms(&self, process: RawHandle) -> Result<i64, WinError> {
        self.record("GetProcessTimes", &format!("({process})"))?;
        Ok(1)
    }
    fn close(&self, handle: RawHandle) -> Result<(), WinError> {
        self.record("CloseHandle", &format!("({handle})"))
    }
}

#[test]
fn five_injected_failures_use_correct_termination_wait_and_exact_handle_counts()
-> Result<(), String> {
    for (fail, kind, termination, expected_handles) in [
        ("CreateProcessW", FailureKind::SpawnFailed, None, vec![]),
        (
            "CreateJobObjectW",
            FailureKind::JobSetupFailed,
            Some("TerminateProcess(101)"),
            vec![101, 102],
        ),
        (
            "SetInformationJobObject",
            FailureKind::JobSetupFailed,
            Some("TerminateProcess(101)"),
            vec![101, 102, 103],
        ),
        (
            "AssignProcessToJobObject",
            FailureKind::JobSetupFailed,
            Some("TerminateProcess(101)"),
            vec![101, 102, 103],
        ),
        (
            "ResumeThread",
            FailureKind::ResumeFailed,
            Some("TerminateJobObject(103)"),
            vec![101, 102, 103],
        ),
    ] {
        let fake = Arc::new(Fake {
            fail,
            calls: Mutex::new(vec![]),
        });
        let result = ManagedProcess::launch(
            fake.clone(),
            &SpawnRequest {
                exe: PathBuf::from(r"E:\bundle\app.exe"),
                args: vec![],
            },
        );
        let failure = result.err().ok_or("expected injected launch failure")?;
        assert_eq!(failure.kind, kind);
        assert_eq!(failure.error.code, 1234);
        assert!(failure.cleanup_errors.is_empty());
        let calls = fake.calls()?;
        println!(
            "INJECT {fail}: {}",
            serde_json::to_string(&calls).map_err(|e| e.to_string())?
        );
        let mut closed = BTreeMap::new();
        for call in &calls {
            if call.starts_with("CloseHandle(") {
                *closed.entry(call.clone()).or_insert(0) += 1;
            }
        }
        assert_eq!(closed.len(), expected_handles.len());
        for handle in expected_handles {
            assert_eq!(closed.get(&format!("CloseHandle({handle})")), Some(&1));
        }
        match termination {
            None => assert!(!calls.iter().any(|c| c.starts_with("Terminate")
                || c.starts_with("WaitForSingleObject")
                || c.starts_with("CloseHandle"))),
            Some(expected) => {
                let terminate_at = calls
                    .iter()
                    .position(|c| c == expected)
                    .ok_or("missing termination")?;
                let wait_at = calls
                    .iter()
                    .position(|c| c == "WaitForSingleObject(101,None)")
                    .ok_or("missing wait")?;
                let close_at = calls
                    .iter()
                    .position(|c| c.starts_with("CloseHandle"))
                    .ok_or("missing close")?;
                assert!(terminate_at < wait_at && wait_at < close_at);
                assert_eq!(
                    calls.iter().filter(|c| c.starts_with("Terminate")).count(),
                    1
                );
            }
        }
    }
    Ok(())
}

#[test]
fn success_closes_thread_immediately_and_cleanup_is_idempotent() -> Result<(), String> {
    let fake = Arc::new(Fake {
        fail: "",
        calls: Mutex::new(vec![]),
    });
    let mut child = ManagedProcess::launch(
        fake.clone(),
        &SpawnRequest {
            exe: PathBuf::from(r"E:\bundle\app.exe"),
            args: vec![],
        },
    )
    .map_err(|e| format!("{e:?}"))?;
    let calls = fake.calls()?;
    let resume_at = calls
        .iter()
        .position(|c| c == "ResumeThread(102)")
        .ok_or("resume missing")?;
    assert_eq!(
        calls.get(resume_at + 1),
        Some(&"CloseHandle(102)".to_owned())
    );
    assert!(child.cleanup().is_empty());
    assert!(child.cleanup().is_empty());
    drop(child);
    let calls = fake.calls()?;
    for handle in [101, 102, 103] {
        assert_eq!(
            calls
                .iter()
                .filter(|c| **c == format!("CloseHandle({handle})"))
                .count(),
            1
        );
    }
    assert_eq!(
        calls
            .iter()
            .filter(|c| c.starts_with("TerminateJobObject"))
            .count(),
        1
    );
    println!(
        "SUCCESS/CLEANUP: {}",
        serde_json::to_string(&calls).map_err(|e| e.to_string())?
    );
    Ok(())
}
