//! Deterministic subprocess fixture. Excluded unless test-probes is enabled.
use chrono::{DateTime, SecondsFormat, Utc};
use serde_json::json;
use spectrum_agent::win32::{NativeWin32, Win32};
use std::{
    fs::{self, OpenOptions},
    io::{Read, Write},
    net::{TcpListener, TcpStream},
    path::PathBuf,
    time::{Duration, Instant},
};
use windows_sys::Win32::System::Threading::GetCurrentProcess;

fn serve_health(connection: &mut TcpStream, mode: &str) -> std::io::Result<bool> {
    connection.set_nonblocking(false)?;
    connection.set_read_timeout(Some(Duration::from_secs(1)))?;
    connection.set_write_timeout(Some(Duration::from_secs(1)))?;
    let mut request = Vec::new();
    while request.len() < 4096 && !request.windows(4).any(|bytes| bytes == b"\r\n\r\n") {
        let mut chunk = [0; 512];
        let count = connection.read(&mut chunk)?;
        if count == 0 {
            return Ok(false);
        }
        request.extend_from_slice(&chunk[..count]);
    }
    let smoke = request.starts_with(b"GET /smoke ");
    if !smoke && !request.starts_with(b"GET /health ") {
        return Ok(false);
    }
    let boot_id = if mode == "wrong-boot" {
        "deadbeef"
    } else {
        "1234abcd"
    };
    let body = if smoke {
        let authorized = String::from_utf8_lossy(&request).lines().any(|line| {
            line.split_once(':').is_some_and(|(name, value)| {
                name.eq_ignore_ascii_case("authorization")
                    && value.trim() == "Bearer abcdef0123456789abcdef0123456789"
            })
        });
        if !authorized {
            return Err(std::io::Error::other("smoke authorization absent"));
        }
        json!({"nan_ratio":0.0,"reflectance_range":[-1.0,1.0],"bands":8,"shape":[8,8,8],"elapsed_ms":0.1}).to_string()
    } else {
        json!({"status":"ok","boot_id":boot_id,"pid":std::process::id(),"version":"0.1.0","uptime_s":0.1}).to_string()
    };
    let mut headers = String::new();
    let status = if smoke && mode == "smoke-auth-failure" {
        401
    } else if smoke && mode == "smoke-no-headers" {
        500
    } else if smoke && mode == "smoke-http-failure" {
        409
    } else if smoke && mode == "smoke-redirect" {
        302
    } else {
        200
    };
    if smoke && !matches!(mode, "smoke-no-headers" | "smoke-auth-failure") {
        let boot = match mode {
            "smoke-wrong-boot" => "deadbeef",
            "smoke-bad-boot" => "INVALID!",
            _ => "1234abcd",
        };
        // Intentionally mixed-case names: clients must honor HTTP case-insensitivity.
        headers.push_str(&format!("x-SpEcTrUmAgEnT-bOoT-iD: {boot}\r\n"));
        if mode != "smoke-no-pid" {
            let pid = match mode {
                "smoke-wrong-pid" => "1".to_owned(),
                "smoke-bad-pid" => "+1".to_owned(),
                _ => std::process::id().to_string(),
            };
            headers.push_str(&format!("X-sPeCtRuMaGeNt-PiD: {pid}\r\n"));
        }
        if mode == "smoke-redirect" {
            headers.push_str("Location: http://127.0.0.1:1/third-path\r\n");
        }
    }
    write!(
        connection,
        "HTTP/1.1 {status} Fixture\r\n{headers}Content-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
        body.len(),
        body
    )?;
    connection.flush()?;
    Ok(true)
}

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args_os().skip(1);
    let mode = args
        .next()
        .ok_or("missing stub mode")?
        .to_string_lossy()
        .into_owned();
    let root = PathBuf::from(args.next().ok_or("missing stub data root")?);
    let mode = if mode == "from-file" {
        fs::read_to_string(root.join("mode.txt"))?.trim().to_owned()
    } else {
        mode
    };
    if mode == "exit" {
        std::process::exit(23);
    }
    if mode == "timeout" {
        loop {
            std::thread::sleep(Duration::from_millis(50));
        }
    }
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    let port = listener.local_addr()?.port();
    listener.set_nonblocking(true)?;
    let process = unsafe { GetCurrentProcess() } as usize; // Pseudo handle: never CloseHandle.
    let created = NativeWin32
        .created_at_ms(process)
        .map_err(|e| format!("{}:{}", e.api, e.code))?;
    let created = DateTime::<Utc>::from_timestamp_millis(created)
        .ok_or("invalid creation time")?
        .to_rfc3339_opts(SecondsFormat::Millis, true);
    let payload = json!({"boot_id":"1234abcd","pid":std::process::id(),"process_created_at":created,"port":port,"token":"abcdef0123456789abcdef0123456789","protocol":1,"version":"0.1.0","started_at":Utc::now().to_rfc3339_opts(SecondsFormat::Millis,true)});
    fs::create_dir_all(root.join("run"))?;
    fs::write(
        root.join("run/handshake.json.tmp"),
        serde_json::to_vec(&payload)?,
    )?;
    fs::rename(
        root.join("run/handshake.json.tmp"),
        root.join("run/handshake.json"),
    )?;
    let mut health_served = false;
    let mut ready_ack = None;
    loop {
        if mode == "ready-exit" && health_served && root.join("ready-ack").is_file() {
            ready_ack.get_or_insert_with(Instant::now);
        }
        if ready_ack.is_some_and(|start: Instant| start.elapsed() > Duration::from_millis(100)) {
            std::process::exit(24);
        }
        match listener.accept() {
            Ok((mut connection, _)) => {
                let result = serve_health(&mut connection, &mode);
                if matches!(result, Ok(true)) {
                    health_served = true;
                }
                // A cancelled/timed-out health request is a connection event, not a process failure.
                let mut events = OpenOptions::new()
                    .create(true)
                    .append(true)
                    .open(root.join("connection-events.jsonl"))?;
                writeln!(
                    events,
                    "{}",
                    json!({"served":result.as_ref().ok(),"error":result.as_ref().err().map(ToString::to_string)})
                )?;
            }
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                std::thread::sleep(Duration::from_millis(5))
            }
            Err(error) => return Err(error.into()),
        }
    }
}

fn main() {
    if let Err(error) = run() {
        if let Some(root) = std::env::args_os().nth(2) {
            let _ = fs::write(
                PathBuf::from(root).join("stub-error.txt"),
                error.to_string(),
            );
        }
        eprintln!("supervisor test stub failed: {error}");
        std::process::exit(70);
    }
}
