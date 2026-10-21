//! Real shipped Rust forwarding against the isolated live sidecar, not WebView invoke.
use spectrum_agent::{handshake, preprocess};
use std::{env, fs, io::{self, Write}};

fn execute() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {
        return Err("expected handshake file, request JSON file, output file".into());
    }
    let identity = handshake::parse(&fs::read(&args[1])?)?;
    let request = preprocess::parse_request(serde_json::from_slice(&fs::read(&args[2])?)?)
        .map_err(|_| "parse_request rejected evidence request")?;
    let report = preprocess::forward(&identity, &request)
        .map_err(|_| "actual Rust forward rejected live response")?;
    if !report.is_object() || report.get("curves").is_none()
        || report.get("body_base64").is_some() || report.get("run_id").is_none() {
        return Err("report is not parsed report JSON".into());
    }
    let bytes = serde_json::to_vec_pretty(&report)?;
    if bytes.windows(identity.token().len()).any(|part| part == identity.token().as_bytes()) {
        return Err("sensitive report rejected".into());
    }
    fs::write(&args[3], bytes)?;
    writeln!(io::stdout(), "real parse_request/forward: report JSON object, no base64 wrapper; NOT WebView invoke")?;
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    execute()
}
