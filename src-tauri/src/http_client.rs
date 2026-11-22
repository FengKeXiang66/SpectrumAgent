//! Bounded connection pools for fixed loopback forwarders; never store auth here.
use reqwest::blocking::{Client, ClientBuilder};
use std::{collections::HashMap, sync::{Mutex, OnceLock}, time::Duration};

pub fn shared(profile: &'static str, builder: impl FnOnce() -> ClientBuilder) -> Result<Client, reqwest::Error> {
    if std::env::var("SPECTRUMAGENT_HTTP_CLIENT_REUSE").as_deref() == Ok("0") {
        return builder().build();
    }
    static CLIENTS: OnceLock<Mutex<HashMap<&'static str, Client>>> = OnceLock::new();
    let mut clients = CLIENTS.get_or_init(|| Mutex::new(HashMap::new()))
        .lock().unwrap_or_else(|poisoned| poisoned.into_inner());
    if let Some(client) = clients.get(profile) { return Ok(client.clone()); }
    let client = builder().pool_idle_timeout(Duration::from_secs(15)).pool_max_idle_per_host(2).build()?;
    clients.insert(profile, client.clone());
    Ok(client)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{io::{Read, Write}, net::TcpListener, sync::atomic::{AtomicUsize, Ordering}};

    #[test]
    fn reuses_connection_without_reusing_authorization() -> Result<(), Box<dyn std::error::Error>> {
        let listener = TcpListener::bind("127.0.0.1:0")?;
        let port = listener.local_addr()?.port();
        let server = std::thread::spawn(move || -> std::io::Result<Vec<String>> {
            let (mut socket, _) = listener.accept()?;
            socket.set_nonblocking(false)?;
            socket.set_read_timeout(Some(Duration::from_secs(5)))?;
            let mut requests = Vec::new();
            for _ in 0..2 {
                let mut raw = Vec::new();
                let mut byte = [0_u8];
                while !raw.ends_with(b"\r\n\r\n") { socket.read_exact(&mut byte)?; raw.push(byte[0]); }
                requests.push(String::from_utf8_lossy(&raw).to_string());
                socket.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}")?;
            }
            Ok(requests)
        });
        let builds = AtomicUsize::new(0);
        for token in ["first-generation", "second-generation"] {
            let client = shared("test-connection-and-auth", || {
                builds.fetch_add(1, Ordering::SeqCst);
                Client::builder().no_proxy().redirect(reqwest::redirect::Policy::none())
                    .connect_timeout(Duration::from_millis(500)).timeout(Duration::from_secs(5))
            })?;
            assert_eq!(client.get(format!("http://127.0.0.1:{port}/fixed"))
                .bearer_auth(token).send()?.text()?, "{}");
        }
        assert_eq!(builds.load(Ordering::SeqCst), 1);
        let requests = server.join().map_err(|_| std::io::Error::other("test server failed"))??;
        assert!(requests[0].contains("Bearer first-generation"));
        assert!(requests[1].contains("Bearer second-generation"));
        assert!(!requests[1].contains("first-generation"));
        Ok(())
    }
}
