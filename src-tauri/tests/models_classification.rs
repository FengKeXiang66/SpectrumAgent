#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]
use serde_json::{Value, json};
use spectrum_agent::{
    handshake,
    models::{forward, parse_request},
};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::Duration,
};

#[test]
fn create_run_value_forwards_the_exact_classification_body() {
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = listener.local_addr().unwrap().port();
    let body = json!({"task":"classification","cube_ids":["cube"],"annotation_version_ids":["annotation"],
        "preprocess_run_ids":["preprocess"],"target":"label","cv_strategy":"group_kfold","cv_folds":5,
        "seed":17,"split_strategy":"none","confidence_threshold":0.35,"n_components":2});
    let request = parse_request(json!({"op":"create_run","body":body.clone()})).unwrap();
    let server = thread::spawn(move || {
        let (mut socket, _) = listener.accept().unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut received = Vec::new();
        let mut buffer = [0u8; 4096];
        loop {
            let count = socket.read(&mut buffer).unwrap();
            assert!(count > 0);
            received.extend_from_slice(&buffer[..count]);
            if let Some(end) = received.windows(4).position(|item| item == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&received[..end]).to_lowercase();
                let length: usize = headers
                    .lines()
                    .find_map(|line| line.strip_prefix("content-length: "))
                    .unwrap()
                    .parse()
                    .unwrap();
                if received.len() < end + 4 + length {
                    continue;
                }
                assert_eq!(
                    headers.lines().next().unwrap(),
                    "post /api/v1/models/runs http/1.1"
                );
                assert_eq!(
                    serde_json::from_slice::<Value>(&received[end + 4..end + 4 + length]).unwrap(),
                    body
                );
                break;
            }
        }
        let response = "{\"status\":\"succeeded\"}";
        write!(socket, "HTTP/1.1 200 OK\r\nConnection: close\r\nX-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\nContent-Length: {}\r\n\r\n{}", response.len(), response).unwrap();
    });
    let identity = handshake::parse(
        &serde_json::to_vec(&json!({"boot_id":"1234abcd","pid":123,"port":port,
        "token":"0123456789abcdef0123456789abcdef","protocol":1,"version":"0.1.0",
        "process_created_at":"2026-10-19T00:00:00.000Z","started_at":"2026-10-19T00:00:00.000Z"}))
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        forward(&identity, &request).unwrap(),
        json!({"status":"succeeded"})
    );
    server.join().unwrap();
}
