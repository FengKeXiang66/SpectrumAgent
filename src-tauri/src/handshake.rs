use chrono::NaiveDate;
use serde::Serialize;
use serde_json::Value;
use std::fmt;

const FIELDS: [&str; 8] = [
    "boot_id",
    "pid",
    "process_created_at",
    "port",
    "token",
    "protocol",
    "version",
    "started_at",
];

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub enum HandshakeIssue {
    ReadFailed,
    InvalidJson,
    InvalidFields,
    InvalidMetadata { field: &'static str },
}

impl fmt::Display for HandshakeIssue {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{self:?}")
    }
}
impl std::error::Error for HandshakeIssue {}

// Intentionally neither Serialize nor Debug: no generic bridge or logger can expose the token.
pub struct Handshake {
    pub boot_id: String,
    pub pid: u32,
    pub process_created_at_ms: i64,
    pub port: u16,
    pub started_at_ms: i64,
    token: String,
}

impl Handshake {
    pub fn token(&self) -> &str {
        &self.token
    }
}

pub fn utc_millis(text: &str) -> Option<i64> {
    let bytes = text.as_bytes();
    if bytes.len() != 24
        || ![4, 7, 10, 13, 16, 19, 23]
            .into_iter()
            .zip(b"--T::.Z")
            .all(|(i, expected)| bytes[i] == *expected)
    {
        return None;
    }
    if !bytes
        .iter()
        .enumerate()
        .all(|(i, value)| [4, 7, 10, 13, 16, 19, 23].contains(&i) || value.is_ascii_digit())
    {
        return None;
    }
    let number = |start: usize, end: usize| text.get(start..end)?.parse::<u32>().ok();
    let year = number(0, 4)?;
    if year == 0 {
        return None;
    }
    let date = NaiveDate::from_ymd_opt(year as i32, number(5, 7)?, number(8, 10)?)?;
    Some(
        date.and_hms_milli_opt(
            number(11, 13)?,
            number(14, 16)?,
            number(17, 19)?,
            number(20, 23)?,
        )?
        .and_utc()
        .timestamp_millis(),
    )
}

fn lower_hex(value: &str, length: usize) -> bool {
    value.len() == length
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

pub fn parse(bytes: &[u8]) -> Result<Handshake, HandshakeIssue> {
    let value: Value = serde_json::from_slice(bytes).map_err(|_| HandshakeIssue::InvalidJson)?;
    let object = value.as_object().ok_or(HandshakeIssue::InvalidFields)?;
    if object.len() != FIELDS.len() || !FIELDS.iter().all(|key| object.contains_key(*key)) {
        return Err(HandshakeIssue::InvalidFields);
    }
    let bad = |field| HandshakeIssue::InvalidMetadata { field };
    let string = |key| {
        object
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| bad(key))
    };
    let integer = |key| {
        object
            .get(key)
            .and_then(Value::as_u64)
            .ok_or_else(|| bad(key))
    };
    let boot_id = string("boot_id")?;
    if !lower_hex(boot_id, 8) {
        return Err(bad("boot_id"));
    }
    let token = string("token")?;
    if !lower_hex(token, 32) {
        return Err(bad("token"));
    }
    let pid = integer("pid")?;
    if !(1..=u32::MAX as u64).contains(&pid) {
        return Err(bad("pid"));
    }
    let port = integer("port")?;
    if !(1..=u16::MAX as u64).contains(&port) {
        return Err(bad("port"));
    }
    if integer("protocol")? != 1 {
        return Err(bad("protocol"));
    }
    if string("version")? != "0.1.0" {
        return Err(bad("version"));
    }
    let process_created_at_ms =
        utc_millis(string("process_created_at")?).ok_or_else(|| bad("process_created_at"))?;
    let started_at_ms = utc_millis(string("started_at")?).ok_or_else(|| bad("started_at"))?;
    Ok(Handshake {
        boot_id: boot_id.to_owned(),
        pid: pid as u32,
        port: port as u16,
        process_created_at_ms,
        started_at_ms,
        token: token.to_owned(),
    })
}
