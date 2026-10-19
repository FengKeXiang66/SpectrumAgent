#![cfg(debug_assertions)]
use spectrum_agent::{
    process::validate_dev_process,
    win32::{CreatedProcess, CreationParameters, RawHandle, WaitResult, Win32, WinError},
};
struct Identity {
    belongs: bool,
    created: i64,
    alive: bool,
}
impl Win32 for Identity {
    fn dev_in_job(&self, process: RawHandle, job: RawHandle) -> Result<bool, WinError> {
        assert_eq!((process, job), (101, 103));
        Ok(self.belongs)
    }
    fn created_at_ms(&self, _: RawHandle) -> Result<i64, WinError> {
        Ok(self.created)
    }
    fn wait(&self, _: RawHandle, _: Option<u32>) -> Result<WaitResult, WinError> {
        Ok(if self.alive {
            WaitResult::Timeout
        } else {
            WaitResult::Exited
        })
    }
    fn create_suspended(&self, _: &CreationParameters) -> Result<CreatedProcess, WinError> {
        Err(unused())
    }
    fn create_job(&self) -> Result<RawHandle, WinError> {
        Err(unused())
    }
    fn set_kill_on_close(&self, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
    fn assign(&self, _: RawHandle, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
    fn resume(&self, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
    fn terminate_process(&self, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
    fn terminate_job(&self, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
    fn exit_code(&self, _: RawHandle) -> Result<u32, WinError> {
        Err(unused())
    }
    fn close(&self, _: RawHandle) -> Result<(), WinError> {
        Err(unused())
    }
}
fn unused() -> WinError {
    WinError {
        api: "unexpected_test_call",
        code: 1,
    }
}

#[test]
fn same_job_creation_time_and_live_process_are_all_required() {
    let good = Identity {
        belongs: true,
        created: 123,
        alive: true,
    };
    assert!(validate_dev_process(&good, 101, 103, 123).is_ok());
    for (identity, expected) in [
        (
            Identity {
                belongs: false,
                ..good
            },
            "IsProcessInJob",
        ),
        (
            Identity {
                created: 124,
                ..good
            },
            "dev_process_created_at",
        ),
        (
            Identity {
                alive: false,
                ..good
            },
            "dev_process_exited",
        ),
    ] {
        let result = validate_dev_process(&identity, 101, 103, 123);
        assert_eq!(result.err().map(|error| error.api), Some(expected));
    }
}
