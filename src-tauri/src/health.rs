use crate::handshake::Handshake;
use reqwest::blocking::Client;
use serde_json::Value;
use std::time::Duration;

pub struct HealthClient {
    client: Client,
}
pub enum HealthResult {
    Pending,
    Matching,
    IdentityMismatch(&'static str),
}

impl HealthClient {
    pub fn new() -> Result<Self, reqwest::Error> {
        Ok(Self {
            client: Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .connect_timeout(Duration::from_millis(250))
                .timeout(Duration::from_millis(500))
                .build()?,
        })
    }

    // The only reqwest request in this crate: numeric loopback and fixed /health.
    // No arbitrary URL, host, path, Authorization or external request is accepted.
    pub fn check(&self, handshake: &Handshake) -> HealthResult {
        let response = match self
            .client
            .get(format!("http://127.0.0.1:{}/health", handshake.port))
            .send()
        {
            Ok(response) if response.status() == 200 => response,
            _ => return HealthResult::Pending,
        };
        let Ok(value) = response.json::<Value>() else {
            return HealthResult::Pending;
        };
        if value.get("boot_id").and_then(Value::as_str) != Some(handshake.boot_id.as_str()) {
            return HealthResult::IdentityMismatch("health_boot_id");
        }
        if value.get("pid").and_then(Value::as_u64) != Some(u64::from(handshake.pid)) {
            return HealthResult::IdentityMismatch("health_pid");
        }
        if value.get("status").and_then(Value::as_str) != Some("ok")
            || value.get("version").and_then(Value::as_str) != Some("0.1.0")
        {
            return HealthResult::IdentityMismatch("health_protocol");
        }
        HealthResult::Matching
    }
}
