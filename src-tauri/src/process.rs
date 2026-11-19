use crate::{
    state::FailureKind,
    win32::{RawHandle, SpawnRequest, WaitResult, Win32, WinError},
};
use std::sync::Arc;

struct OwnedHandle {
    value: Option<RawHandle>,
    api: Arc<dyn Win32>,
}

impl OwnedHandle {
    fn new(value: RawHandle, api: Arc<dyn Win32>) -> Self {
        Self {
            value: Some(value),
            api,
        }
    }
    fn close(&mut self) -> Result<(), WinError> {
        match self.value.take() {
            Some(value) => self.api.close(value),
            None => Ok(()),
        }
    }
}

impl Drop for OwnedHandle {
    fn drop(&mut self) {
        if let Err(error) = self.close() {
            eprintln!("CloseHandle failed: code={}", error.code);
        }
    }
}

#[derive(Debug)]
pub struct LaunchFailure {
    pub kind: FailureKind,
    pub error: WinError,
    pub pid: Option<u32>,
    pub cleanup_errors: Vec<WinError>,
}

pub struct ManagedProcess {
    #[cfg(debug_assertions)]
    launcher: Option<OwnedHandle>,
    api: Arc<dyn Win32>,
    process: OwnedHandle,
    thread: OwnedHandle,
    job: Option<OwnedHandle>,
    assigned: bool,
    reaped: bool,
    pub pid: u32,
    pub created_at_ms: i64,
}

impl ManagedProcess {
    pub fn launch(api: Arc<dyn Win32>, request: &SpawnRequest) -> Result<Self, LaunchFailure> {
        Self::launch_observed(api, request, |_, _| {})
    }

    pub fn launch_observed(
        api: Arc<dyn Win32>,
        request: &SpawnRequest,
        mut observer: impl FnMut(&str, u32),
    ) -> Result<Self, LaunchFailure> {
        let parameters = request.parameters().map_err(|error| LaunchFailure {
            kind: FailureKind::SpawnFailed,
            error,
            pid: None,
            cleanup_errors: vec![],
        })?;
        let child = api
            .create_suspended(&parameters)
            .map_err(|error| LaunchFailure {
                kind: FailureKind::SpawnFailed,
                error,
                pid: None,
                cleanup_errors: vec![],
            })?;
        let mut owned = Self {
            #[cfg(debug_assertions)]
            launcher: None,
            process: OwnedHandle::new(child.process, api.clone()),
            thread: OwnedHandle::new(child.thread, api.clone()),
            job: None,
            api,
            assigned: false,
            reaped: false,
            pid: child.pid,
            created_at_ms: 0,
        };
        observer("process_created_suspended", child.pid);
        if let Err((kind, error)) = owned.finish_launch(&mut observer) {
            let cleanup_errors = owned.cleanup();
            return Err(LaunchFailure {
                kind,
                error,
                pid: Some(child.pid),
                cleanup_errors,
            });
        }
        Ok(owned)
    }

    fn finish_launch(
        &mut self,
        observer: &mut impl FnMut(&str, u32),
    ) -> Result<(), (FailureKind, WinError)> {
        let job = self
            .api
            .create_job()
            .map_err(|e| (FailureKind::JobSetupFailed, e))?;
        self.job = Some(OwnedHandle::new(job, self.api.clone()));
        self.api
            .set_kill_on_close(job)
            .map_err(|e| (FailureKind::JobSetupFailed, e))?;
        let process = self.raw().ok_or((
            FailureKind::JobSetupFailed,
            WinError {
                api: "process_handle",
                code: 6,
            },
        ))?;
        self.api
            .assign(job, process)
            .map_err(|e| (FailureKind::JobSetupFailed, e))?;
        self.assigned = true;
        observer("job_assigned", self.pid);
        let thread = self.thread.value.ok_or((
            FailureKind::ResumeFailed,
            WinError {
                api: "thread_handle",
                code: 6,
            },
        ))?;
        self.api
            .resume(thread)
            .map_err(|e| (FailureKind::ResumeFailed, e))?;
        self.thread
            .close()
            .map_err(|e| (FailureKind::ResumeFailed, e))?;
        observer("thread_resumed_and_closed", self.pid);
        self.created_at_ms = self
            .api
            .created_at_ms(process)
            .map_err(|e| (FailureKind::ProcessIdentityFailed, e))?;
        Ok(())
    }

    pub fn raw(&self) -> Option<RawHandle> {
        self.process.value
    }
    #[cfg(debug_assertions)]
    pub fn dev_job(&self) -> Option<RawHandle> {
        self.job.as_ref().and_then(|job| job.value)
    }
    /// DEV ONLY: pin and supervise the actual CPython process, retaining the
    /// launcher handle and the original kill-on-close Job. Never fall back.
    #[cfg(debug_assertions)]
    pub fn adopt_dev_python(&mut self, pid: u32, created: i64) -> Result<(), WinError> {
        let job = self.dev_job().ok_or(WinError { api: "dev_job_handle", code: 6 })?;
        let raw = self.api.open_dev_process(pid)?;
        let pinned = OwnedHandle::new(raw, self.api.clone());
        validate_dev_process(self.api.as_ref(), raw, job, created)?;
        let launcher = std::mem::replace(&mut self.process, pinned);
        self.launcher = Some(launcher);
        self.pid = pid;
        self.created_at_ms = created;
        Ok(())
    }
    pub fn mark_reaped(&mut self) {
        self.reaped = true;
    }
    pub fn request_termination(&self) -> Result<(), WinError> {
        let Some(process) = self.raw() else {
            return Ok(());
        };
        match self
            .job
            .as_ref()
            .and_then(|job| job.value)
            .filter(|_| self.assigned)
        {
            Some(job) => self.api.terminate_job(job),
            None => self.api.terminate_process(process),
        }
    }

    // Only supervisor/waiter threads call this; never the desktop event loop.
    pub fn cleanup(&mut self) -> Vec<WinError> {
        let mut errors = Vec::new();
        if let Some(process) = self.raw()
            && !self.reaped
        {
            let terminate = match self
                .job
                .as_ref()
                .and_then(|job| job.value)
                .filter(|_| self.assigned)
            {
                Some(job) => self.api.terminate_job(job),
                None => self.api.terminate_process(process),
            };
            if let Err(error) = terminate {
                errors.push(error);
            }
            match self.api.wait(process, None) {
                Ok(WaitResult::Exited) => self.reaped = true,
                Ok(WaitResult::Timeout) => errors.push(WinError {
                    api: "WaitForSingleObject",
                    code: 258,
                }),
                Err(error) => errors.push(error),
            }
        }
        if let Err(error) = self.thread.close() {
            errors.push(error);
        }
        if let Err(error) = self.process.close() {
            errors.push(error);
        }
        #[cfg(debug_assertions)]
        if let Some(launcher) = self.launcher.as_mut()
            && let Err(error) = launcher.close() {
            errors.push(error);
        }
        if let Some(job) = self.job.as_mut()
            && let Err(error) = job.close()
        {
            errors.push(error);
        }
        errors
    }
}

#[cfg(debug_assertions)]
pub fn validate_dev_process(api: &dyn Win32, raw: RawHandle, job: RawHandle, created: i64) -> Result<(), WinError> {
    if !api.dev_in_job(raw, job)? { return Err(WinError { api: "IsProcessInJob", code: 5 }); }
    if api.created_at_ms(raw)? != created { return Err(WinError { api: "dev_process_created_at", code: 13 }); }
    if api.wait(raw, Some(0))? != WaitResult::Timeout { return Err(WinError { api: "dev_process_exited", code: 6 }); }
    Ok(())
}

impl Drop for ManagedProcess {
    fn drop(&mut self) {
        for error in self.cleanup() {
            eprintln!(
                "process cleanup failed: api={} code={}",
                error.api, error.code
            );
        }
    }
}
