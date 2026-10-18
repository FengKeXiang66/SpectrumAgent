//! Pure log-attribution tests, not substitutes for real frozen-engine failure cases.
use chrono::DateTime;
use serde_json::{Value, json};
use spectrum_agent::causality::EngineLogCursor;
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::PathBuf,
    sync::atomic::{AtomicU64, Ordering},
};

static NEXT: AtomicU64 = AtomicU64::new(1);
type ResultTest = Result<(), Box<dyn std::error::Error>>;
fn root() -> Result<PathBuf, Box<dyn std::error::Error>> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target/causality-runtime")
        .join(format!(
            "{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    fs::create_dir_all(&path)?;
    Ok(path)
}
fn append(path: &std::path::Path, value: &Value, newline: bool) -> ResultTest {
    let mut file = OpenOptions::new().append(true).create(true).open(path)?;
    file.write_all(&serde_json::to_vec(value)?)?;
    if newline {
        file.write_all(b"\n")?;
    }
    Ok(())
}
fn line() -> Value {
    json!({"event":"handshake_error","logger":"engine.handshake","pid":42,"boot_id":"1234abcd","error":"HANDSHAKE_INVALID_JSON","timestamp":"2026-10-18T00:00:01.123456Z"})
}

#[test]
fn only_new_complete_lines_with_own_integer_pid_in_utc_window_can_be_cause() -> ResultTest {
    let root = root()?;
    let path = root.join("engine-20261018.jsonl");
    append(&path, &line(), true)?;
    let cursor = EngineLogCursor::capture(&root, "20261018".to_owned())?;
    let created = DateTime::parse_from_rfc3339("2026-10-18T00:00:00Z")?.timestamp_millis();
    let exited = created + 2000;
    let mut missing = line();
    missing
        .as_object_mut()
        .ok_or("object fixture")?
        .remove("pid");
    append(&path, &missing, true)?;
    for pid in [
        json!(43),
        json!(true),
        json!("42"),
        json!(42.0),
        json!(null),
    ] {
        let mut row = line();
        row["pid"] = pid;
        append(&path, &row, true)?;
    }
    for (key, value) in [
        ("timestamp", json!("2026-10-17T23:59:59Z")),
        ("timestamp", json!("2026-10-18T00:00:03Z")),
        ("logger", json!("engine")),
        ("event", json!("engine_boot")),
        ("error", json!("HANDSHAKE_OWNER_ALIVE")),
    ] {
        let mut row = line();
        row[key] = value;
        append(&path, &row, true)?;
    }
    assert_eq!(cursor.find_cause(42, created, exited, "20261018")?, None);
    append(&path, &line(), false)?;
    assert_eq!(cursor.find_cause(42, created, exited, "20261018")?, None);
    OpenOptions::new()
        .append(true)
        .open(&path)?
        .write_all(b"\n")?;
    assert_eq!(
        cursor.find_cause(42, created, exited, "20261018")?,
        Some("HANDSHAKE_INVALID_JSON".to_owned())
    );
    println!(
        "CAUSALITY pure function: old/missing/wrong/noninteger PID, wrong logger/event/code, out-of-window, partial JSON excluded; own new complete line accepted"
    );
    Ok(())
}

#[test]
fn midnight_files_and_preexisting_partial_line_are_handled_without_fallback() -> ResultTest {
    let root = root()?;
    let path = root.join("engine-20261018.jsonl");
    append(&path, &line(), false)?;
    let cursor = EngineLogCursor::capture(&root, "20261018".to_owned())?;
    OpenOptions::new()
        .append(true)
        .open(&path)?
        .write_all(b"\n")?;
    let created = DateTime::parse_from_rfc3339("2026-10-18T23:59:59Z")?.timestamp_millis();
    let exited = created + 2000;
    let mut next = line();
    next["timestamp"] = json!("2026-10-19T00:00:00.500+00:00");
    next["error"] = json!("HANDSHAKE_INVALID_FIELDS");
    append(&root.join("engine-20261019.jsonl"), &next, true)?;
    assert_eq!(
        cursor.find_cause(42, created, exited, "20261019")?,
        Some("HANDSHAKE_INVALID_FIELDS".to_owned())
    );
    assert_eq!(cursor.find_cause(99, created, exited, "20261019")?, None);
    println!(
        "CAUSALITY pure function: launch/exit day files tracked, existing partial line excluded, no engine_boot/boot_id PID fallback"
    );
    Ok(())
}
