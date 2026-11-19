//! DEV ONLY. This entire module is excluded from release by lib.rs cfg.
use crate::win32::SpawnRequest;
use std::{ffi::OsString, io, path::Path};

pub fn python_request(data_root: &Path) -> io::Result<SpawnRequest> {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or_else(|| io::Error::other("开发仓库根目录不存在"))?;
    let exe = std::env::var_os("SPECTRUMAGENT_DEV_PYTHON")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| root.join(".venv").join("Scripts").join("python.exe"));
    if !exe.is_absolute() {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "dev Python必须是绝对路径",
        ));
    }
    Ok(SpawnRequest {
        exe,
        args: vec![
            OsString::from("-B"),
            root.join("scripts").join("dev_sidecar.py").into_os_string(),
            OsString::from("--data-root"),
            data_root.as_os_str().to_owned(),
        ],
    })
}
