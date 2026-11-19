use chrono::DateTime;
use serde_json::Value;
use std::{
    collections::BTreeMap,
    fs::{self, File},
    io::{self, Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};

struct Offset {
    bytes: u64,
    partial_line: bool,
}
pub struct EngineLogCursor {
    root: PathBuf,
    offsets: BTreeMap<String, Offset>,
    launch_day: String,
}

impl EngineLogCursor {
    pub fn capture(directory: &Path, launch_day: String) -> io::Result<Self> {
        let mut offsets = BTreeMap::new();
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.starts_with("engine-")
                || !name.ends_with(".jsonl")
                || !entry.file_type()?.is_file()
            {
                continue;
            }
            let mut file = File::open(entry.path())?;
            let bytes = file.metadata()?.len();
            let partial_line = if bytes > 0 {
                file.seek(SeekFrom::End(-1))?;
                let mut last = [0];
                file.read_exact(&mut last)?;
                last[0] != b'\n'
            } else {
                false
            };
            offsets.insert(
                name,
                Offset {
                    bytes,
                    partial_line,
                },
            );
        }
        Ok(Self {
            root: directory.to_owned(),
            offsets,
            launch_day,
        })
    }

    pub fn find_cause(
        &self,
        pid: u32,
        created_at_ms: i64,
        observed_exit_ms: i64,
        exit_day: &str,
    ) -> io::Result<Option<String>> {
        let mut days = vec![self.launch_day.as_str()];
        if exit_day != self.launch_day {
            days.push(exit_day);
        }
        for day in days {
            if day.len() != 8 || !day.bytes().all(|b| b.is_ascii_digit()) {
                return Err(io::Error::other("invalid engine log day"));
            }
            let name = format!("engine-{day}.jsonl");
            let path = self.root.join(&name);
            let mut file = match File::open(path) {
                Ok(file) => file,
                Err(e) if e.kind() == io::ErrorKind::NotFound => continue,
                Err(e) => return Err(e),
            };
            let offset = self.offsets.get(&name);
            let start = offset.map_or(0, |offset| offset.bytes);
            if file.metadata()?.len() < start {
                continue;
            } // Truncation cannot manufacture evidence.
            file.seek(SeekFrom::Start(start))?;
            let mut appended = Vec::new();
            file.read_to_end(&mut appended)?;
            let Some(end) = appended.iter().rposition(|b| *b == b'\n') else {
                continue;
            };
            let mut lines = appended[..=end].split(|b| *b == b'\n');
            if offset.is_some_and(|offset| offset.partial_line) {
                lines.next();
            }
            for line in lines {
                let Ok(value) = serde_json::from_slice::<Value>(line) else {
                    continue;
                };
                if value.get("event").and_then(Value::as_str) != Some("handshake_error")
                    || value.get("logger").and_then(Value::as_str) != Some("engine.handshake")
                    || value.get("pid").and_then(Value::as_u64) != Some(u64::from(pid))
                {
                    continue;
                }
                let Some(stamp) = value
                    .get("timestamp")
                    .and_then(Value::as_str)
                    .and_then(|t| DateTime::parse_from_rfc3339(t).ok())
                else {
                    continue;
                };
                let milliseconds = stamp.timestamp_millis();
                if milliseconds < created_at_ms || milliseconds > observed_exit_ms {
                    continue;
                }
                let Some(code) = value.get("error").and_then(Value::as_str) else {
                    continue;
                };
                if matches!(
                    code,
                    "HANDSHAKE_READ_FAILED"
                        | "HANDSHAKE_INVALID_JSON"
                        | "HANDSHAKE_INVALID_FIELDS"
                        | "HANDSHAKE_INVALID_METADATA"
                        | "HANDSHAKE_OWNER_UNVERIFIABLE"
                ) {
                    return Ok(Some(code.to_owned()));
                }
            }
        }
        Ok(None)
    }
}
