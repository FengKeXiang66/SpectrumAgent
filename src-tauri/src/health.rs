use crate::handshake::Handshake;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
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

// No string/URL deserializer or caller-controlled host/path exists.
#[derive(Clone, Copy)]
enum EngineRoute {
    Health,
    Smoke,
}
impl EngineRoute {
    fn path(self) -> &'static str {
        match self {
            Self::Health => "/health",
            Self::Smoke => "/smoke",
        }
    }
    fn url(self, port: u16) -> Result<reqwest::Url, SmokeFailure> {
        let mut url =
            reqwest::Url::parse("http://127.0.0.1/").map_err(|_| SmokeFailure::Transport)?;
        if port == 0 || url.set_port(Some(port)).is_err() {
            return Err(SmokeFailure::Transport);
        }
        url.set_path(self.path());
        Ok(url)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SmokeMetrics {
    pub nan_ratio: f64,
    pub reflectance_range: [f64; 2],
    pub bands: u32,
    pub shape: [u32; 3],
    pub elapsed_ms: f64,
}

#[derive(Clone, Debug, Serialize, PartialEq, Eq)]
pub enum SmokeFailure {
    NotReady,
    Busy,
    StaleGeneration,
    Transport,
    IdentityMismatch { layer: &'static str },
    Http { status: u16 },
    InvalidBody,
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

    // Both routes come from EngineRoute; neither accepts a caller-controlled URL.
    pub fn check(&self, handshake: &Handshake) -> HealthResult {
        let Ok(url) = EngineRoute::Health.url(handshake.port) else {
            return HealthResult::Pending;
        };
        let response = match self.client.get(url).send() {
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

    /// Blocking: callers must use a worker thread. Never return untrusted raw headers/body.
    /// A caller cannot pass any host or third path to the fixed request API:
    /// ```compile_fail
    /// use spectrum_agent::health::HealthClient;
    /// fn cannot_request_other_route(client: &HealthClient) {
    ///     client.smoke("http://127.0.0.1:1234/third-path");
    /// }
    /// ```
    pub fn smoke(&self, handshake: &Handshake) -> Result<SmokeMetrics, SmokeFailure> {
        let response = self
            .client
            .get(EngineRoute::Smoke.url(handshake.port)?)
            .bearer_auth(handshake.token())
            .timeout(Duration::from_secs(20))
            .send()
            .map_err(|_| SmokeFailure::Transport)?;
        // Deliberately before status/body, including 401/redirect/error responses.
        let boot = response
            .headers()
            .get("X-SpectrumAgent-Boot-Id")
            .and_then(|v| v.to_str().ok());
        if !boot.is_some_and(|v| {
            v.len() == 8
                && v.bytes()
                    .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
                && v == handshake.boot_id
        }) {
            return Err(SmokeFailure::IdentityMismatch {
                layer: "smoke_boot_id",
            });
        }
        let pid = response
            .headers()
            .get("X-SpectrumAgent-Pid")
            .and_then(|v| v.to_str().ok());
        if !pid.is_some_and(|v| {
            v.parse::<u32>().ok() == Some(handshake.pid) && v == handshake.pid.to_string()
        }) {
            return Err(SmokeFailure::IdentityMismatch { layer: "smoke_pid" });
        }
        if response.status() != 200 {
            return Err(SmokeFailure::Http {
                status: response.status().as_u16(),
            });
        }
        let value = response
            .json::<SmokeMetrics>()
            .map_err(|_| SmokeFailure::InvalidBody)?;
        if !value.nan_ratio.is_finite()
            || !(0.0..=1.0).contains(&value.nan_ratio)
            || !value.reflectance_range.iter().all(|v| v.is_finite())
            || value.reflectance_range[0] > value.reflectance_range[1]
            || value.bands == 0
            || value.shape.contains(&0)
            || value.shape[2] != value.bands
            || !value.elapsed_ms.is_finite()
            || value.elapsed_ms < 0.0
        {
            return Err(SmokeFailure::InvalidBody);
        }
        Ok(value)
    }
}

#[cfg(test)]
mod route_tests {
    use super::*;
    #[test]
    fn closed_routes_always_use_numeric_loopback_and_literal_paths() -> Result<(), SmokeFailure> {
        for port in [1, 80, 443, 65535] {
            for route in [EngineRoute::Health, EngineRoute::Smoke] {
                let url = route.url(port)?;
                assert_eq!(url.scheme(), "http");
                assert_eq!(url.host_str(), Some("127.0.0.1"));
                assert_eq!(url.path(), route.path());
                assert!(matches!(url.path(), "/health" | "/smoke"));
                assert!(url.query().is_none() && url.fragment().is_none());
                assert!(url.username().is_empty() && url.password().is_none());
            }
        }
        assert!(EngineRoute::Smoke.url(0).is_err());
        Ok(())
    }
}
