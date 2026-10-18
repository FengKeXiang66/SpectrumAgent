//! Deterministic subprocess fixture. Excluded unless test-probes is enabled.
use chrono::{DateTime, SecondsFormat, Utc};
use serde_json::json;
use spectrum_agent::win32::{NativeWin32, Win32};
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    path::PathBuf,
    time::{Duration, Instant},
};
use windows_sys::Win32::System::Threading::GetCurrentProcess;

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
    let mut health_served = None;
    loop {
        if mode == "ready-exit"
            && health_served
                .is_some_and(|start: Instant| start.elapsed() > Duration::from_millis(600))
        {
            std::process::exit(24);
        }
        match listener.accept() {
            Ok((mut connection, _)) => {
                connection.set_read_timeout(Some(Duration::from_secs(1)))?;
                let mut request = [0_u8; 4096];
                let count = connection.read(&mut request)?;
                if !request[..count].starts_with(b"GET /health ") {
                    return Err("stub received a non-health request".into());
                }
                let boot_id = if mode == "wrong-boot" {
                    "deadbeef"
                } else {
                    "1234abcd"
                };
                let body=json!({"status":"ok","boot_id":boot_id,"pid":std::process::id(),"version":"0.1.0","uptime_s":0.1}).to_string();
                write!(
                    connection,
                    "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: {}\r\n\r\n{}",
                    body.len(),
                    body
                )?;
                connection.flush()?;
                health_served.get_or_insert_with(Instant::now);
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
        eprintln!("supervisor test stub failed: {error}");
        std::process::exit(70);
    }
}
