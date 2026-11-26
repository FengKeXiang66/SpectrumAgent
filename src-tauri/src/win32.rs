use std::os::windows::ffi::OsStrExt;
use std::os::windows::io::{AsRawHandle, FromRawHandle, OwnedHandle};
use std::{
    ffi::{OsStr, OsString},
    fs::{File, OpenOptions},
    io,
    path::{Path, PathBuf},
};
use windows_sys::Win32::{
    Foundation::{
        CloseHandle, DUPLICATE_SAME_ACCESS, DuplicateHandle, FILETIME, GetLastError, HANDLE,
        WAIT_OBJECT_0, WAIT_TIMEOUT,
    },
    System::{
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject, TerminateJobObject,
        },
        Threading::{
            CREATE_NO_WINDOW, CREATE_SUSPENDED, CreateProcessW, DeleteProcThreadAttributeList,
            EXTENDED_STARTUPINFO_PRESENT, GetCurrentProcess, GetExitCodeProcess, GetProcessTimes,
            INFINITE, InitializeProcThreadAttributeList, LPPROC_THREAD_ATTRIBUTE_LIST,
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST, PROCESS_INFORMATION, ResumeThread,
            STARTF_USESTDHANDLES, STARTUPINFOEXW, STARTUPINFOW, TerminateProcess,
            UpdateProcThreadAttribute, WaitForSingleObject,
        },
    },
};

pub type RawHandle = usize;

#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize)]
pub struct WinError {
    pub api: &'static str,
    pub code: u32,
}

#[derive(Clone, Debug)]
pub struct SpawnRequest {
    pub exe: PathBuf,
    pub args: Vec<OsString>,
}

#[derive(Clone, Debug)]
pub struct CreationParameters {
    pub exe: PathBuf,
    pub directory: PathBuf,
    pub application: Vec<u16>,
    pub command_line: Vec<u16>,
    pub inherit_handles: i32,
    pub flags: u32,
    pub stderr_path: Option<PathBuf>,
}

impl SpawnRequest {
    pub fn parameters(&self) -> Result<CreationParameters, WinError> {
        let directory = self
            .exe
            .parent()
            .filter(|_| self.exe.is_absolute())
            .ok_or(WinError {
                api: "CreateProcessW",
                code: 3,
            })?
            .to_owned();
        let application = wide(self.exe.as_os_str());
        let mut command_line = quoted(self.exe.as_os_str());
        for arg in &self.args {
            command_line.push(b' ' as u16);
            command_line.extend(quoted(arg));
        }
        command_line.push(0);
        if application[..application.len() - 1].contains(&0)
            || command_line[..command_line.len() - 1].contains(&0)
            || command_line.len() > 32767
        {
            return Err(WinError {
                api: "CreateProcessW",
                code: 87,
            });
        }
        Ok(CreationParameters {
            exe: self.exe.clone(),
            directory,
            application,
            command_line,
            inherit_handles: 0,
            flags: CREATE_SUSPENDED | CREATE_NO_WINDOW,
            stderr_path: None,
        })
    }
}

#[derive(Clone, Copy, Debug)]
pub struct CreatedProcess {
    pub process: RawHandle,
    pub thread: RawHandle,
    pub pid: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WaitResult {
    Exited,
    Timeout,
}

pub trait Win32: Send + Sync {
    #[cfg(debug_assertions)]
    fn open_dev_process(&self, _pid: u32) -> Result<RawHandle, WinError> {
        Err(WinError { api: "OpenProcess", code: 50 })
    }
    #[cfg(debug_assertions)]
    fn dev_in_job(&self, _process: RawHandle, _job: RawHandle) -> Result<bool, WinError> {
        Err(WinError { api: "IsProcessInJob", code: 50 })
    }
    fn create_suspended(&self, parameters: &CreationParameters)
    -> Result<CreatedProcess, WinError>;
    fn create_job(&self) -> Result<RawHandle, WinError>;
    fn set_kill_on_close(&self, job: RawHandle) -> Result<(), WinError>;
    fn assign(&self, job: RawHandle, process: RawHandle) -> Result<(), WinError>;
    fn resume(&self, thread: RawHandle) -> Result<(), WinError>;
    fn terminate_process(&self, process: RawHandle) -> Result<(), WinError>;
    fn terminate_job(&self, job: RawHandle) -> Result<(), WinError>;
    fn wait(&self, process: RawHandle, timeout_ms: Option<u32>) -> Result<WaitResult, WinError>;
    fn exit_code(&self, process: RawHandle) -> Result<u32, WinError>;
    fn created_at_ms(&self, process: RawHandle) -> Result<i64, WinError>;
    fn close(&self, handle: RawHandle) -> Result<(), WinError>;
}

#[derive(Default)]
pub struct NativeWin32;

fn error(api: &'static str) -> WinError {
    // This must be the very first API executed after a failed Win32 call.
    WinError {
        api,
        code: unsafe { GetLastError() },
    }
}

fn wide(value: &OsStr) -> Vec<u16> {
    value.encode_wide().chain(Some(0)).collect()
}

fn inheritable(file: File) -> Result<OwnedHandle, WinError> {
    let mut duplicate = std::ptr::null_mut();
    let current = unsafe { GetCurrentProcess() };
    if unsafe {
        DuplicateHandle(current, file.as_raw_handle(), current, &mut duplicate, 0, 1,
                        DUPLICATE_SAME_ACCESS)
    } == 0
    {
        return Err(error("DuplicateHandle"));
    }
    Ok(unsafe { OwnedHandle::from_raw_handle(duplicate) })
}

fn stderr_handles(path: &Path) -> Result<(OwnedHandle, OwnedHandle), WinError> {
    let open_error = |api, err: io::Error| WinError {
        api,
        code: err.raw_os_error().unwrap_or(1) as u32,
    };
    let null = OpenOptions::new().read(true).write(true).open(r"\\.\NUL")
        .map_err(|err| open_error("open_engine_nul", err))?;
    let stderr = OpenOptions::new().write(true).create_new(true).open(path)
        .map_err(|err| open_error("open_engine_stderr", err))?;
    Ok((inheritable(null)?, inheritable(stderr)?))
}

struct HandleList<'a> {
    buffer: Vec<usize>,
    _handles: &'a [HANDLE],
}

impl<'a> HandleList<'a> {
    fn raw(&mut self) -> LPPROC_THREAD_ATTRIBUTE_LIST {
        self.buffer.as_mut_ptr().cast()
    }

    fn new(handles: &'a [HANDLE]) -> Result<Self, WinError> {
        let mut bytes = 0;
        unsafe { InitializeProcThreadAttributeList(std::ptr::null_mut(), 1, 0, &mut bytes) };
        if bytes == 0 {
            return Err(error("InitializeProcThreadAttributeList"));
        }
        let mut buffer = vec![0usize; bytes.div_ceil(std::mem::size_of::<usize>())];
        if unsafe { InitializeProcThreadAttributeList(buffer.as_mut_ptr().cast(), 1, 0, &mut bytes) } == 0 {
            return Err(error("InitializeProcThreadAttributeList"));
        }
        let mut list = Self { buffer, _handles: handles };
        if unsafe {
            UpdateProcThreadAttribute(
                list.raw(), 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST as usize, handles.as_ptr().cast(),
                std::mem::size_of_val(handles), std::ptr::null_mut(), std::ptr::null(),
            )
        } == 0
        {
            return Err(error("UpdateProcThreadAttribute"));
        }
        Ok(list)
    }
}

impl Drop for HandleList<'_> {
    fn drop(&mut self) {
        unsafe { DeleteProcThreadAttributeList(self.raw()) };
    }
}

fn quoted(value: &OsStr) -> Vec<u16> {
    let mut result = vec![b'"' as u16];
    let mut slashes = 0;
    for ch in value.encode_wide() {
        if ch == b'\\' as u16 {
            slashes += 1;
            continue;
        }
        if ch == b'"' as u16 {
            result.extend(std::iter::repeat_n(b'\\' as u16, slashes * 2 + 1));
        } else {
            result.extend(std::iter::repeat_n(b'\\' as u16, slashes));
        }
        result.push(ch);
        slashes = 0;
    }
    result.extend(std::iter::repeat_n(b'\\' as u16, slashes * 2));
    result.push(b'"' as u16);
    result
}

impl Win32 for NativeWin32 {
    #[cfg(debug_assertions)]
    fn open_dev_process(&self, pid: u32) -> Result<RawHandle, WinError> {
        use windows_sys::Win32::System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION, PROCESS_SYNCHRONIZE};
        let raw = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SYNCHRONIZE, 0, pid) };
        if raw.is_null() { return Err(error("OpenProcess")); }
        Ok(raw as usize)
    }
    #[cfg(debug_assertions)]
    fn dev_in_job(&self, process: RawHandle, job: RawHandle) -> Result<bool, WinError> {
        use windows_sys::Win32::System::JobObjects::IsProcessInJob;
        let mut belongs = 0;
        if unsafe { IsProcessInJob(process as HANDLE, job as HANDLE, &mut belongs) } == 0 {
            return Err(error("IsProcessInJob"));
        }
        Ok(belongs != 0)
    }
    fn create_suspended(
        &self,
        parameters: &CreationParameters,
    ) -> Result<CreatedProcess, WinError> {
        if !parameters.exe.is_file() {
            return Err(WinError {
                api: "CreateProcessW",
                code: 2,
            });
        }
        let directory = wide(parameters.directory.as_os_str());
        let mut command = parameters.command_line.clone();
        let stdio = parameters.stderr_path.as_deref().map(stderr_handles).transpose()?;
        let handles = stdio.as_ref().map(|(null, stderr)| [null.as_raw_handle(), stderr.as_raw_handle()]);
        let mut attributes = handles.as_ref().map(|handles| HandleList::new(handles)).transpose()?;
        let mut startup = STARTUPINFOEXW::default();
        let mut flags = parameters.flags;
        let mut inherit_handles = parameters.inherit_handles;
        startup.StartupInfo.cb = std::mem::size_of::<STARTUPINFOW>() as u32;
        if let (Some(attributes), Some([null, stderr])) = (&mut attributes, handles) {
            startup.StartupInfo.cb = std::mem::size_of::<STARTUPINFOEXW>() as u32;
            startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
            startup.StartupInfo.hStdInput = null;
            startup.StartupInfo.hStdOutput = null;
            startup.StartupInfo.hStdError = stderr;
            startup.lpAttributeList = attributes.raw();
            flags |= EXTENDED_STARTUPINFO_PRESENT;
            inherit_handles = 1;
        }
        let mut info = PROCESS_INFORMATION::default();
        // With redirection, only the two explicitly listed handles can be inherited.
        let ok = unsafe {
            CreateProcessW(
                parameters.application.as_ptr(),
                command.as_mut_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                inherit_handles,
                flags,
                std::ptr::null(),
                directory.as_ptr(),
                &startup.StartupInfo,
                &mut info,
            )
        };
        if ok == 0 {
            return Err(error("CreateProcessW"));
        }
        Ok(CreatedProcess {
            process: info.hProcess as usize,
            thread: info.hThread as usize,
            pid: info.dwProcessId,
        })
    }
    fn create_job(&self) -> Result<RawHandle, WinError> {
        let handle = unsafe { CreateJobObjectW(std::ptr::null(), std::ptr::null()) };
        if handle.is_null() {
            return Err(error("CreateJobObjectW"));
        }
        Ok(handle as usize)
    }
    fn set_kill_on_close(&self, job: RawHandle) -> Result<(), WinError> {
        let mut limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
        limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        if unsafe {
            SetInformationJobObject(
                job as HANDLE,
                JobObjectExtendedLimitInformation,
                &limits as *const _ as *const _,
                std::mem::size_of_val(&limits) as u32,
            )
        } == 0
        {
            return Err(error("SetInformationJobObject"));
        }
        Ok(())
    }
    fn assign(&self, job: RawHandle, process: RawHandle) -> Result<(), WinError> {
        if unsafe { AssignProcessToJobObject(job as HANDLE, process as HANDLE) } == 0 {
            return Err(error("AssignProcessToJobObject"));
        }
        Ok(())
    }
    fn resume(&self, thread: RawHandle) -> Result<(), WinError> {
        if unsafe { ResumeThread(thread as HANDLE) } == u32::MAX {
            return Err(error("ResumeThread"));
        }
        Ok(())
    }
    fn terminate_process(&self, process: RawHandle) -> Result<(), WinError> {
        if unsafe { TerminateProcess(process as HANDLE, 1) } == 0 {
            return Err(error("TerminateProcess"));
        }
        Ok(())
    }
    fn terminate_job(&self, job: RawHandle) -> Result<(), WinError> {
        if unsafe { TerminateJobObject(job as HANDLE, 1) } == 0 {
            return Err(error("TerminateJobObject"));
        }
        Ok(())
    }
    fn wait(&self, process: RawHandle, timeout_ms: Option<u32>) -> Result<WaitResult, WinError> {
        match unsafe { WaitForSingleObject(process as HANDLE, timeout_ms.unwrap_or(INFINITE)) } {
            WAIT_OBJECT_0 => Ok(WaitResult::Exited),
            WAIT_TIMEOUT => Ok(WaitResult::Timeout),
            _ => Err(error("WaitForSingleObject")),
        }
    }
    fn exit_code(&self, process: RawHandle) -> Result<u32, WinError> {
        let mut code = 0;
        if unsafe { GetExitCodeProcess(process as HANDLE, &mut code) } == 0 {
            return Err(error("GetExitCodeProcess"));
        }
        Ok(code)
    }
    fn created_at_ms(&self, process: RawHandle) -> Result<i64, WinError> {
        let mut creation = FILETIME::default();
        let mut exit = FILETIME::default();
        let mut kernel = FILETIME::default();
        let mut user = FILETIME::default();
        if unsafe {
            GetProcessTimes(
                process as HANDLE,
                &mut creation,
                &mut exit,
                &mut kernel,
                &mut user,
            )
        } == 0
        {
            return Err(error("GetProcessTimes"));
        }
        let ticks = (u64::from(creation.dwHighDateTime) << 32) | u64::from(creation.dwLowDateTime);
        Ok((ticks / 10_000) as i64 - 11_644_473_600_000)
    }
    fn close(&self, handle: RawHandle) -> Result<(), WinError> {
        if unsafe { CloseHandle(handle as HANDLE) } == 0 {
            return Err(error("CloseHandle"));
        }
        Ok(())
    }
}
