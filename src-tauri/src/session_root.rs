//! Per-session data root (2026-11-13 ruling): the app is a single-use tool.
//! All processing state (db, artifacts, cache, exports, logs) lives under
//! `<permanent>/sessions/<millis>-<pid>` and is wiped on exit; leftovers from
//! crashed runs are swept at next launch. The permanent root keeps only
//! application-level configuration (API-key ciphertext, LLM settings snapshot)
//! and the shell event log.
//!
//! The backend learns its roots through environment variables rather than CLI
//! arguments because the frozen production exe is spawned with `args: vec![]`
//! and resolves its root from the environment on its own.

use std::{
    fs, io,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

/// Backend data root override; read by `AppPaths.from_environment`.
pub const ENV_DATA_ROOT: &str = "SPECTRUMAGENT_DATA_ROOT";
/// Cross-session root for the DPAPI credential file; read by `AppPaths.credential_root`.
pub const ENV_PERMANENT_ROOT: &str = "SPECTRUMAGENT_PERMANENT_ROOT";

/// Create a fresh session directory after sweeping stale ones. Must run after
/// the single-instance lock is held; a live sibling's directory is still
/// protected by the pid embedded in its name.
pub fn create(root: &Path) -> io::Result<PathBuf> {
    sweep(root, process_alive);
    let millis = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|span| span.as_millis())
        .unwrap_or(0);
    let session = root
        .join("sessions")
        .join(format!("{millis}-{}", std::process::id()));
    fs::create_dir_all(&session)?;
    Ok(session)
}

/// Best-effort removal of our own session directory at shutdown. The backend
/// must already be dead so no file locks remain; leftovers are swept at next
/// launch, so a missing directory is success too.
pub fn cleanup(path: &Path) -> io::Result<()> {
    match fs::remove_dir_all(path) {
        Ok(()) => Ok(()),
        Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
        Err(error) => Err(error),
    }
}

/// Remove session directories whose owning process is gone. Names that do not
/// end in a parseable pid, and pids that are still alive, are kept untouched.
fn sweep(root: &Path, is_alive: impl Fn(u32) -> bool) {
    let Ok(entries) = fs::read_dir(root.join("sessions")) else {
        return;
    };
    for entry in entries.flatten() {
        let name = entry.file_name();
        let Some(name) = name.to_str() else { continue };
        let Some(pid) = name
            .rsplit('-')
            .next()
            .and_then(|tail| tail.parse::<u32>().ok())
        else {
            continue;
        };
        if is_alive(pid) {
            continue;
        }
        let _ = fs::remove_dir_all(entry.path());
    }
}

#[cfg(windows)]
fn process_alive(pid: u32) -> bool {
    use windows_sys::Win32::{
        Foundation::CloseHandle,
        System::Threading::{OpenProcess, PROCESS_QUERY_LIMITED_INFORMATION},
    };
    let handle = unsafe { OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, pid) };
    if handle.is_null() {
        return false;
    }
    unsafe { CloseHandle(handle) };
    true
}

#[cfg(not(windows))]
fn process_alive(pid: u32) -> bool {
    Path::new("/proc").join(pid.to_string()).exists()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn create_sweeps_dead_sessions_and_keeps_live_ones() {
        let root = std::env::temp_dir().join(format!("spectrum-session-test-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        let sessions = root.join("sessions");
        let dead = sessions.join("1700000000000-0"); // pid 0 never opens.
        let live = sessions.join(format!("1700000000001-{}", std::process::id()));
        let malformed = sessions.join("not-a-session");
        fs::create_dir_all(dead.join("db")).unwrap();
        fs::create_dir_all(&live).unwrap();
        fs::create_dir_all(&malformed).unwrap();

        let created = create(&root).unwrap();
        assert!(created.is_dir());
        assert!(created.starts_with(&sessions));
        assert!(created.file_name().unwrap().to_str().unwrap().ends_with(&std::process::id().to_string()));
        assert!(!dead.exists(), "dead-pid session must be swept");
        assert!(live.exists(), "live-pid session must survive");
        assert!(malformed.exists(), "unparseable names stay untouched");

        fs::remove_dir_all(&root).unwrap();
    }

    #[test]
    fn cleanup_removes_tree_and_tolerates_missing() {
        let root = std::env::temp_dir().join(format!("spectrum-session-clean-{}", std::process::id()));
        let session = root.join("sessions").join("1-2");
        fs::create_dir_all(session.join("db")).unwrap();
        fs::write(session.join("db").join("x.sqlite3"), b"state").unwrap();
        cleanup(&session).unwrap();
        assert!(!session.exists());
        cleanup(&session).unwrap(); // Already gone: still Ok.
        fs::remove_dir_all(&root).unwrap();
    }
}
