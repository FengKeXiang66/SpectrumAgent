use serde_json::{Value, json};
use spectrum_agent::{
    agent::{self, ForwardError, MAX_RESPONSE_BYTES},
    handshake, settings,
    state::Phase,
    supervisor::Snapshot,
};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::{Duration, Instant},
};

const ID: &str = "00000000-0000-0000-0000-000000000001";
const IDENTITY: &str = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";

fn exchange(
    request: Value,
    settings_domain: bool,
    status: &str,
    headers: &str,
    body: Vec<u8>,
    length: Option<u64>,
) -> Result<Result<Value, ForwardError>, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    listener.set_nonblocking(true)?;
    let port = listener.local_addr()?.port();
    let identity = handshake::parse(&serde_json::to_vec(&json!({
        "boot_id":"1234abcd","pid":123,"port":port,"token":"0123456789abcdef0123456789abcdef",
        "protocol":1,"version":"0.1.0","process_created_at":"2026-10-23T00:00:00.000Z",
        "started_at":"2026-10-23T00:00:00.000Z"}))?)?;
    let mut response = format!("HTTP/1.1 {status}\r\nConnection: close\r\n{headers}");
    if let Some(length) = length {
        response.push_str(&format!("Content-Length: {length}\r\n"));
    }
    response.push_str("\r\n");
    let server = thread::spawn(move || -> std::io::Result<()> {
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut socket = loop {
            match listener.accept() {
                Ok((socket, _)) => break socket,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    if Instant::now() >= deadline {
                        return Err(std::io::Error::other("stub accept timeout"));
                    }
                    thread::sleep(Duration::from_millis(2));
                }
                Err(error) => return Err(error),
            }
        };
        socket.set_nonblocking(false)?;
        socket.set_read_timeout(Some(Duration::from_secs(3)))?;
        let mut incoming = Vec::new();
        let mut buffer = [0u8; 1024];
        loop {
            let n = socket.read(&mut buffer)?;
            if n == 0 {
                return Err(std::io::Error::other("request closed"));
            }
            incoming.extend_from_slice(&buffer[..n]);
            if let Some(head_end) = incoming.windows(4).position(|part| part == b"\r\n\r\n") {
                let head = String::from_utf8_lossy(&incoming[..head_end]).to_ascii_lowercase();
                let length = head
                    .lines()
                    .find_map(|line| line.strip_prefix("content-length: "))
                    .and_then(|text| text.parse::<usize>().ok())
                    .unwrap_or(0);
                if incoming.len() >= head_end + 4 + length {
                    break;
                }
            }
        }
        assert!(
            String::from_utf8_lossy(&incoming)
                .to_ascii_lowercase()
                .contains("authorization: bearer ")
        );
        socket.write_all(response.as_bytes())?;
        // A bounded reader may intentionally close before the body finishes.
        let _ = socket.write_all(&body);
        Ok(())
    });
    let result = if settings_domain {
        settings::forward(&identity, &settings::parse_request(request)?)
    } else {
        agent::forward(&identity, &agent::parse_request(request)?)
    };
    server
        .join()
        .map_err(|_| std::io::Error::other("stub failed"))??;
    Ok(result)
}

fn requests() -> [(Value, bool); 2] {
    [
        (json!({"op":"create_session"}), false),
        (json!({"op":"get_llm"}), true),
    ]
}

#[test]
fn agent_three_operations_and_two_body_shapes_have_literal_routes()
-> Result<(), Box<dyn std::error::Error>> {
    for (value, path, method, body) in [
        (
            json!({"op":"create_session"}),
            "/api/v1/agent/sessions".into(),
            "POST",
            Some(json!({})),
        ),
        (
            json!({"op":"get_steps","id":ID}),
            format!("/api/v1/agent/sessions/{ID}/steps"),
            "GET",
            None,
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"content":"查询"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"content":"查询"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"check_id":ID,"decision":"approve"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"check_id":ID,"decision":"approve"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"check_id":ID,"decision":"reject"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"check_id":ID,"decision":"reject"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"approve"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"plan_id":ID,"action":"approve"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"skip","step_ref":2,"reason":"跳过此步及之后"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"plan_id":ID,"action":"skip","step_ref":2,"reason":"跳过此步及之后"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"rollback","step_ref":3,"reason":"从末步开始"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"plan_id":ID,"action":"rollback","step_ref":3,"reason":"从末步开始"})),
        ),
        (
            json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"reject","reason":"暂不执行"}}),
            format!("/api/v1/agent/sessions/{ID}/messages"),
            "POST",
            Some(json!({"plan_id":ID,"action":"reject","reason":"暂不执行"})),
        ),
    ] {
        let (url, actual_method, actual_body) = agent::parse_request(value)?.destination(4321)?;
        assert_eq!(url.as_str(), format!("http://127.0.0.1:4321{path}"));
        assert_eq!(actual_method.as_str(), method);
        assert_eq!(actual_body, body);
        assert!(url.query().is_none() && url.fragment().is_none());
    }
    Ok(())
}

#[test]
fn settings_only_existing_get_put_operations_and_no_key_in_config()
-> Result<(), Box<dyn std::error::Error>> {
    for (value, path, method, expected) in [
        (json!({"op":"get_llm"}), "/api/v1/settings/llm", "GET", None),
        (
            json!({"op":"put_llm","body":{"base_url":"https://provider.invalid/v1","model":"m","temperature":0.25,"max_tokens":"128","timeout_ms":2500,"egress_enabled":true}}),
            "/api/v1/settings/llm",
            "PUT",
            Some(
                json!({"base_url":"https://provider.invalid/v1","model":"m","temperature":0.25,"max_tokens":"128","timeout_ms":2500,"egress_enabled":true}),
            ),
        ),
        (
            json!({"op":"put_llm","body":{"egress_enabled":false}}),
            "/api/v1/settings/llm",
            "PUT",
            Some(json!({"egress_enabled":false})),
        ),
        (
            json!({"op":"put_key","key":"synthetic-key"}),
            "/api/v1/settings/llm/key",
            "PUT",
            Some(json!({"key":"synthetic-key"})),
        ),
    ] {
        let (url, actual_method, body) = settings::parse_request(value)?.destination(4321)?;
        assert_eq!(url.as_str(), format!("http://127.0.0.1:4321{path}"));
        assert_eq!(actual_method.as_str(), method);
        assert_eq!(body, expected);
    }
    for body in [
        json!({"key":"secret"}),
        json!({"timeout_ms":true}),
        json!({"egress_enabled":"true"}),
        json!({"egress_enabled":1}),
        json!({"egress_enabled":null}),
        json!({"model":null}),
        json!([]),
    ] {
        assert!(settings::parse_request(json!({"op":"put_llm","body":body})).is_err());
    }
    Ok(())
}

#[test]
fn whitelist_rejects_paths_methods_and_mixed_message_shapes() {
    for id in [
        "../health",
        "http://example.com",
        "x?query=1",
        "x#fragment",
        "00000000-0000-0000-0000-000000000001/steps",
    ] {
        assert!(agent::parse_request(json!({"op":"get_steps","id":id})).is_err());
    }
    for request in [
        json!({"op":"create_session","method":"DELETE"}),
        json!({"op":"create_session","body":{}}),
        json!({"op":"get_steps","id":ID,"url":"https://example.com"}),
        json!({"op":"proxy","path":"/health"}),
        json!({"op":"send_message","id":ID,"body":{"content":""}}),
        json!({"op":"send_message","id":ID,"body":{"content":"query","check_id":ID,"decision":"approve"}}),
        json!({"op":"send_message","id":ID,"body":{"check_id":ID,"decision":"maybe"}}),
        json!({"op":"send_message","id":ID,"body":{"check_id":"../health","decision":"approve"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"reject"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"skip","step_ref":2}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"rollback","reason":"原因"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"skip","step_ref":"2","reason":"原因"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"skip","step_ref":0,"reason":"原因"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"unknown"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"approve","content":"混合"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":"../health","action":"approve"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"approve","reason":"原因"}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"approve","step_ref":1}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"approve","reason":null}}),
        json!({"op":"send_message","id":ID,"body":{"plan_id":ID,"action":"reject","reason":" "}}),
    ] {
        assert!(agent::parse_request(request).is_err());
    }
    for request in [
        json!({"op":"get_llm","method":"POST"}),
        json!({"op":"get_llm","path":"/health"}),
        json!({"op":"get_key"}),
        json!({"op":"put_key","key":"secret","url":"https://example.com"}),
    ] {
        assert!(settings::parse_request(request).is_err());
    }
}

#[test]
fn identity_is_checked_before_status_length_and_body_for_both_commands()
-> Result<(), Box<dyn std::error::Error>> {
    for (request, domain) in requests() {
        for headers in [
            "",
            "X-SpectrumAgent-Boot-Id: wrong\r\nX-SpectrumAgent-Pid: 123\r\n",
            "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 999\r\n",
        ] {
            let error = exchange(
                request.clone(),
                domain,
                "500 Error",
                headers,
                b"invalid".to_vec(),
                Some(MAX_RESPONSE_BYTES + 1),
            )?
            .err()
            .ok_or("expected identity error")?;
            assert_eq!(error.error, "DATASET_IDENTITY_MISMATCH");
        }
    }
    Ok(())
}

#[test]
fn declared_and_streaming_limits_are_enforced_for_both_commands()
-> Result<(), Box<dyn std::error::Error>> {
    for (request, domain) in requests() {
        for length in [Some(MAX_RESPONSE_BYTES + 1), None] {
            let body = if length.is_none() {
                vec![b' '; (MAX_RESPONSE_BYTES + 1) as usize]
            } else {
                vec![]
            };
            let error = exchange(request.clone(), domain, "200 OK", IDENTITY, body, length)?
                .err()
                .ok_or("expected limit error")?;
            assert_eq!(error.error, "RESPONSE_TOO_LARGE");
        }
        let mut body = b"{}".to_vec();
        body.resize(MAX_RESPONSE_BYTES as usize, b' ');
        assert_eq!(
            exchange(
                request,
                domain,
                "200 OK",
                IDENTITY,
                body,
                Some(MAX_RESPONSE_BYTES)
            )??,
            json!({})
        );
    }
    // SSE uses the same byte boundary, including a stream with no declared size.
    for length in [Some(MAX_RESPONSE_BYTES + 1), None] {
        let body = if length.is_none() {
            vec![b' '; (MAX_RESPONSE_BYTES + 1) as usize]
        } else {
            vec![]
        };
        let error = exchange(
            json!({"op":"send_message","id":ID,"body":{"content":"查询"}}),
            false,
            "200 OK",
            &format!("{IDENTITY}Content-Type: text/event-stream\r\n"),
            body,
            length,
        )?
        .err()
        .ok_or("expected SSE limit error")?;
        assert_eq!(error.error, "RESPONSE_TOO_LARGE");
    }
    Ok(())
}

#[test]
fn sse_empty_done_suspended_human_check_and_error_close() -> Result<(), Box<dyn std::error::Error>>
{
    for (text, expected) in [
        ("", json!([])),
        (
            "event: done\ndata: {\"content\":\"完成\",\"step_count\":0}\n\n",
            json!([{"event":"done","data":{"content":"完成","step_count":0}}]),
        ),
        (
            "event: human_check\r\ndata: {\"check_id\":\"check-1\",\"summary\":{\"revision\":1}}\r\n\r\n",
            json!([{"event":"human_check","data":{"check_id":"check-1","summary":{"revision":1}}}]),
        ),
        (
            "event: plan\r\ndata: {\"plan_id\":\"round-1\",\"steps\":[{\"seq\":1,\"tool\":\"datasets.list\",\"summary\":{},\"gpu\":false,\"estimate_ms\":null}],\"reason\":\"执行计划待确认\"}\r\n\r\n",
            json!([{"event":"plan","data":{"plan_id":"round-1","steps":[{"seq":1,"tool":"datasets.list","summary":{},"gpu":false,"estimate_ms":null}],"reason":"执行计划待确认"}}]),
        ),
        (
            "event: error\ndata: {\"code\":\"LLM_TRANSPORT\",\"detail\":\"LLM_TRANSPORT\"}",
            json!([{"event":"error","data":{"code":"LLM_TRANSPORT","detail":"LLM_TRANSPORT"}}]),
        ),
    ] {
        let value = exchange(
            json!({"op":"send_message","id":ID,"body":{"content":"查询"}}),
            false,
            "200 OK",
            &format!("{IDENTITY}Content-Type: text/event-stream; charset=utf-8\r\n"),
            text.as_bytes().to_vec(),
            None,
        )??;
        assert_eq!(value, json!({"events":expected}));
    }
    let text = (0..10)
        .map(|i| format!("event: step\ndata: {{\"seq\":{i}}}\n\n"))
        .collect::<String>();
    assert_eq!(
        agent::parse_sse(&text)?["events"]
            .as_array()
            .ok_or("events")?
            .len(),
        10
    );
    for bad in [
        "event: other\ndata: {}\n\n",
        "event: done\ndata: not-json\n\n",
        "data: {}\n\n",
        "event: done\ndata: []\n\n",
    ] {
        assert!(agent::parse_sse(bad).is_err());
    }
    Ok(())
}

#[test]
fn http_errors_keep_status_and_envelope_redirects_not_followed()
-> Result<(), Box<dyn std::error::Error>> {
    for (request, domain) in requests() {
        let body =
            br#"{"error":"INVALID_REQUEST","detail":"invalid","context":{"field":"content"}}"#
                .to_vec();
        let error = exchange(
            request.clone(),
            domain,
            "400 Bad Request",
            IDENTITY,
            body,
            None,
        )?
        .err()
        .ok_or("expected HTTP error")?;
        assert_eq!(error.status_code, Some(400));
        assert_eq!(error.error, "INVALID_REQUEST");
        assert_eq!(error.detail, "invalid");
        assert_eq!(error.context, json!({"field":"content"}));
        let error = exchange(
            request,
            domain,
            "307 Redirect",
            &format!("{IDENTITY}Location: http://127.0.0.1:1/forbidden\r\n"),
            b"{}".to_vec(),
            None,
        )?
        .err()
        .ok_or("redirect")?;
        assert_eq!(error.status_code, Some(307));
    }
    Ok(())
}

#[test]
fn settings_key_and_escaped_credentials_never_cross_error_or_success_envelopes()
-> Result<(), Box<dyn std::error::Error>> {
    let secret = "synthetic-only-key";
    let escaped = secret
        .chars()
        .map(|c| format!("\\u{:04x}", c as u32))
        .collect::<String>();
    for reflected in [secret.to_owned(), escaped] {
        for status in ["200 OK", "400 Bad Request"] {
            let body = format!(r#"{{"error":"REFLECTED","detail":"{reflected}","context":{{}}}}"#)
                .into_bytes();
            let error = exchange(
                json!({"op":"put_key","key":secret}),
                true,
                status,
                IDENTITY,
                body,
                None,
            )?
            .err()
            .ok_or("sensitive")?;
            assert_eq!(error.error, "SENSITIVE_RESPONSE");
            assert!(!serde_json::to_string(&error)?.contains(secret));
        }
    }
    let value = exchange(
        json!({"op":"put_key","key":secret}),
        true,
        "200 OK",
        IDENTITY,
        br#"{"has_key":true}"#.to_vec(),
        None,
    )??;
    assert_eq!(value, json!({"has_key":true}));
    assert!(
        settings::parse_request(json!({"op":"put_key","key":secret,"unexpected":secret}))
            .err()
            .is_some_and(|e| !e.to_string().contains(secret))
    );
    Ok(())
}

#[test]
fn both_commands_reject_stale_generation_or_non_ready_phase() {
    let mut snapshot = Snapshot {
        generation_id: 2,
        phase: Phase::Ready,
        pid: None,
        port: None,
        boot_id: None,
        failure: None,
        cleanup_complete: false,
        pending_activation: false,
    };
    assert!(agent::validate_generation(2, &snapshot).is_ok());
    assert!(
        settings::validate_generation(1, &snapshot)
            .err()
            .is_some_and(|e| e.error == "STALE_RESPONSE")
    );
    snapshot.phase = Phase::Stopping;
    assert!(
        agent::validate_generation(2, &snapshot)
            .err()
            .is_some_and(|e| e.error == "STALE_RESPONSE")
    );
}
