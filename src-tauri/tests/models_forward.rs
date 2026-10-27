use serde_json::{Value, json};
use spectrum_agent::{
    handshake,
    models::{forward, parse_request},
};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
};

const ID: &str = "00000000-0000-0000-0000-000000000001";
const TOKEN: &str = "0123456789abcdef0123456789abcdef";

fn exchange(request: Value, status: &str, headers: &str, body: &str) -> Result<Value, String> {
    let coefficients = request["op"] == "get_coefficients";
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = listener.local_addr().unwrap().port();
    let identity=handshake::parse(&serde_json::to_vec(&json!({"boot_id":"1234abcd","pid":123,"port":port,"token":TOKEN,
        "protocol":1,"version":"0.1.0","process_created_at":"2026-10-19T00:00:00.000Z","started_at":"2026-10-19T00:00:00.000Z"})).unwrap()).unwrap();
    let response = format!(
        "HTTP/1.1 {status}\r\nConnection: close\r\n{headers}Content-Length: {}\r\n\r\n{body}",
        body.len()
    );
    let server = thread::spawn(move || {
        let (mut socket, _) = listener.accept().unwrap();
        socket
            .set_read_timeout(Some(std::time::Duration::from_secs(3)))
            .unwrap();
        let mut all = Vec::new();
        let mut buffer = [0u8; 4096];
        loop {
            let n = socket.read(&mut buffer).unwrap();
            assert!(n > 0);
            all.extend_from_slice(&buffer[..n]);
            if let Some(end) = all.windows(4).position(|p| p == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&all[..end]).to_lowercase();
                let length = headers
                    .lines()
                    .find_map(|s| {
                        s.strip_prefix("content-length: ")
                            .and_then(|s| s.parse::<usize>().ok())
                    })
                    .unwrap_or(0);
                if all.len() >= end + 4 + length {
                    break;
                }
            }
        }
        let text = String::from_utf8(all).unwrap().to_lowercase();
        if coefficients {
            assert_eq!(
                text.lines().next().unwrap(),
                format!("get /api/v1/models/registry/{ID}/coefficients http/1.1")
            );
            assert!(text.ends_with("\r\n\r\n")); // GET has no JSON body.
        }
        assert!(text.contains(&format!("authorization: bearer {TOKEN}")));
        assert!(text.lines().next().unwrap().contains("/api/v1/models/"));
        // A bounded client may close immediately after an oversized header.
        let _ = socket.write_all(response.as_bytes());
    });
    let response = forward(&identity, &parse_request(request).unwrap()).map_err(|error| {
        serde_json::to_value(error).unwrap()["error"]
            .as_str()
            .unwrap()
            .to_string()
    });
    server.join().unwrap();
    response
}

#[test]
fn fixed_model_operations_reach_fake_engine_with_native_identity() {
    let headers = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
    let requests = [
        json!({"op":"list_runs"}),
        json!({"op":"preflight_run","body":{}}),
        json!({"op":"create_run","body":{}}),
        json!({"op":"get_run","id":ID}),
        json!({"op":"lv_sweep","id":ID}),
        json!({"op":"list_targets","project_id":ID}),
        json!({"op":"put_target","cube_id":ID,"schema_id":ID,"value":1}),
        json!({"op":"import_targets","project_id":ID,"csv_text":"csv","overwrite":false}),
    ];
    assert_eq!(requests.len(), 8);
    for request in requests {
        assert_eq!(
            exchange(request, "200 OK", headers, "{\"source\":\"annotation\"}").unwrap()["source"],
            "annotation"
        );
    }
    println!("MODELS_FORWARD eight fixed operations passed with native identity");
}

#[test]
fn registered_coefficients_reach_fake_engine_with_native_identity() {
    let headers = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
    let request = json!({"op":"get_coefficients","model_id":ID});
    assert_eq!(
        exchange(request, "200 OK", headers, "{\"coefficients\":[1,-2]}").unwrap()["coefficients"],
        json!([1, -2])
    );
    println!("MODELS_FORWARD get_coefficients read-only GET passed with native identity");
}

#[test]
fn coefficient_requests_reject_invalid_missing_and_extra_fields_before_network() {
    for value in [
        json!({"op":"get_coefficients","model_id":"bad id"}),
        json!({"op":"get_coefficients"}),
        json!({"op":"get_coefficients","model_id":ID,"extra":1}),
        json!({"op":"get_coefficients","model_id":"../health"}),
        json!({"op":"get_coefficients","model_id":""}),
        json!({"op":"get_coefficients","model_id":"x".repeat(65)}),
    ] {
        assert!(parse_request(value).is_err());
    }
}

#[test]
fn rejects_identity_and_sensitive_response_preserves_structured_errors() {
    let headers = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
    assert_eq!(
        exchange(json!({"op":"list_runs"}), "200 OK", "", "{}"),
        Err("DATASET_IDENTITY_MISMATCH".into())
    );
    let body = format!("{{\"secret\":\"{TOKEN}\"}}");
    assert_eq!(
        exchange(json!({"op":"list_runs"}), "200 OK", headers, &body),
        Err("SENSITIVE_RESPONSE".into())
    );
    assert_eq!(
        exchange(
            json!({"op":"list_runs"}),
            "400 Bad Request",
            headers,
            "{\"error\":\"LEAK_PREFLIGHT_FAILED\",\"detail\":\"blocked\",\"context\":{}}"
        ),
        Err("LEAK_PREFLIGHT_FAILED".into())
    );
}

#[test]
fn refuses_extra_method_path_and_traversal_before_network() {
    for value in [
        json!({"op":"list_runs","method":"DELETE"}),
        json!({"op":"list_runs","path":"/api/v1/settings"}),
        json!({"op":"put_target","cube_id":"../escape","schema_id":ID,"value":1}),
        json!({"op":"not_allowed"}),
    ] {
        assert!(parse_request(value).is_err());
    }
    assert!(parse_request(json!({"op":"get_run","id":"run_1"})).is_ok());
    let capability: Value =
        serde_json::from_str(include_str!("../capabilities/main.json")).unwrap();
    assert!(
        capability["permissions"]
            .as_array()
            .unwrap()
            .contains(&json!("allow-models-forward"))
    );
    assert!(
        capability["description"]
            .as_str()
            .unwrap()
            .contains("/api/v1/models")
    );
    assert_eq!(
        include_str!("../src/main.rs")
            .matches("annotations_draft_forward, models_forward")
            .count(),
        2
    );
}

#[test]
fn bounds_responses_and_checks_decoded_secrets() {
    let headers = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
    let escaped: String = TOKEN
        .chars()
        .map(|c| format!("\\u{:04x}", c as u32))
        .collect();
    assert_eq!(
        exchange(
            json!({"op":"list_runs"}),
            "200 OK",
            headers,
            &format!("{{\"secret\":\"{escaped}\"}}")
        ),
        Err("SENSITIVE_RESPONSE".into())
    );
    let large = serde_json::to_string(&json!({"data":"x".repeat(8*1024*1024)})).unwrap();
    assert_eq!(
        exchange(json!({"op":"list_runs"}), "200 OK", headers, &large),
        Err("RESPONSE_TOO_LARGE".into())
    );
}
