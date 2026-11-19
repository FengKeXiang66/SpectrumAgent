//! Host supplies the Tauri-resolved resource path; release never reads the dev override.
use serde::Serialize;
use std::{ffi::OsString, path::PathBuf};

#[derive(Clone, Debug, Serialize)]
pub struct EngineSelection {
    pub exe: PathBuf,
    pub source: &'static str,
}

impl EngineSelection {
    /// Constructor injection is reserved for tests. It precedes every host path source.
    pub fn resolve(injected: Option<PathBuf>, resource: impl FnOnce() -> PathBuf) -> Self {
        if let Some(exe) = injected {
            return Self {
                exe,
                source: "constructor_injection",
            };
        }
        #[cfg(debug_assertions)]
        if let Some(exe) = std::env::var_os("SPECTRUM_ENGINE_EXE") {
            return Self::development(exe);
        }
        Self {
            exe: resource(),
            source: "resolved_resource",
        }
    }

    pub fn development(exe: OsString) -> Self {
        Self {
            exe: PathBuf::from(exe),
            source: "development_override",
        }
    }

    pub fn valid_shape(&self) -> bool {
        self.exe.is_absolute()
            && self
                .exe
                .file_name()
                .is_some_and(|name| name.eq_ignore_ascii_case("app.exe"))
    }
}
