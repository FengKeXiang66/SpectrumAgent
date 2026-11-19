use chrono::{Local, Utc};
use serde_json::{Value, json};
use std::{
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    sync::{Arc, Mutex, OnceLock},
};
static PROCESS_LOG_LOCK: OnceLock<Arc<Mutex<()>>> = OnceLock::new();

#[derive(Clone)]
pub struct ShellLog {
    directory: PathBuf,
    lock: Arc<Mutex<()>>,
}

impl ShellLog {
    pub fn new(data_root: &Path) -> io::Result<Self> {
        let directory = data_root.join("logs");
        fs::create_dir_all(&directory)?;
        let log = Self {
            directory,
            lock: PROCESS_LOG_LOCK
                .get_or_init(|| Arc::new(Mutex::new(())))
                .clone(),
        };
        log.event("shell_log_started", json!({}))?;
        Ok(log)
    }
    pub fn directory(&self) -> &Path {
        &self.directory
    }
    pub fn event(&self, event: &str, fields: Value) -> io::Result<()> {
        let _guard = self
            .lock
            .lock()
            .map_err(|_| io::Error::other("shell log lock poisoned"))?;
        let mut object = fields
            .as_object()
            .cloned()
            .ok_or_else(|| io::Error::other("log fields must be an object"))?;
        object.insert("event".to_owned(), json!(event));
        object.insert(
            "timestamp".to_owned(),
            json!(Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Millis, true)),
        );
        let path = self
            .directory
            .join(format!("shell-{}.log", Local::now().format("%Y%m%d")));
        let mut file = OpenOptions::new().create(true).append(true).open(path)?;
        serde_json::to_writer(&mut file, &object)?;
        file.write_all(b"\n")?;
        file.flush()
    }
}
