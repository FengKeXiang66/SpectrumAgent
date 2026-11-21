//! Stable per-user storage. Processing data survives both clean exits and crashes.
//! Runtime handshakes remain generation-owned and are cleaned by the supervisor.

use std::{
    fs, io,
    path::{Path, PathBuf},
};

/// Backend data root override; read by `AppPaths.from_environment`.
pub const ENV_DATA_ROOT: &str = "SPECTRUMAGENT_DATA_ROOT";
/// Root for application settings, credentials and experiment archives.
pub const ENV_PERMANENT_ROOT: &str = "SPECTRUMAGENT_PERMANENT_ROOT";

/// Called after acquiring the single-instance lock. Never sweep old session data:
/// an older installation may still have recoverable files there.
pub fn open(root: &Path) -> io::Result<PathBuf> {
    fs::create_dir_all(root)?;
    Ok(root.to_path_buf())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reopening_uses_the_same_database_and_preserves_legacy_sessions() -> io::Result<()> {
        let root = std::env::temp_dir().join(format!("spectrum-workspace-test-{}", std::process::id()));
        let first = open(&root)?;
        fs::create_dir_all(first.join("db"))?;
        fs::write(first.join("db/spectrum-agent.sqlite3"), b"saved database")?;
        let legacy = root.join("sessions/1700000000000-0");
        fs::create_dir_all(&legacy)?;
        fs::write(legacy.join("saved.json"), b"legacy data")?;

        let second = open(&root)?;
        assert_eq!(first, second);
        assert_eq!(
            fs::read(second.join("db/spectrum-agent.sqlite3"))?,
            b"saved database"
        );
        assert_eq!(fs::read(legacy.join("saved.json"))?, b"legacy data");
        fs::remove_dir_all(root)?;
        Ok(())
    }
}
