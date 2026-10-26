use serde_json::{Value, json};
use spectrum_agent::{
    annotations_draft::{self as draft, ForwardError, MAX_RESPONSE_BYTES},
    handshake,
};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::{Duration, Instant},
};

const ID: &str = "00000000-0000-0000-0000-000000000001";
const TOKEN: &str = "0123456789abcdef0123456789abcdef";
const IDENTITY: &str = "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 123\r\n";
type TestResult = Result<(), Box<dyn std::error::Error>>;

fn exchange(
    request: Value,
    status: &str,
    headers: &str,
    body: Vec<u8>,
    length: Option<u64>,
) -> Result<Result<Value, ForwardError>, Box<dyn std::error::Error>> {
    let listener = TcpListener::bind(("127.0.0.1", 0))?;
    listener.set_nonblocking(true)?;
    let port = listener.local_addr()?.port();
    let identity = handshake::parse(&serde_json::to_vec(&json!({
        "boot_id":"1234abcd","pid":123,"port":port,"token":TOKEN,"protocol":1,"version":"0.1.0",
        "process_created_at":"2026-10-24T00:00:00.000Z","started_at":"2026-10-24T00:00:00.000Z"}))?)?;
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
                        return Err(std::io::Error::other("accept timeout"));
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
                return Err(std::io::Error::other("closed request"));
            }
            incoming.extend_from_slice(&buffer[..n]);
            if let Some(end) = incoming.windows(4).position(|p| p == b"\r\n\r\n") {
                let head = String::from_utf8_lossy(&incoming[..end]).to_ascii_lowercase();
                let length = head
                    .lines()
                    .find_map(|s| s.strip_prefix("content-length: "))
                    .and_then(|s| s.parse::<usize>().ok())
                    .unwrap_or(0);
                if incoming.len() >= end + 4 + length {
                    break;
                }
            }
        }
        assert!(String::from_utf8_lossy(&incoming).contains(&format!("Bearer {TOKEN}")));
        socket.write_all(response.as_bytes())?;
        let _ = socket.write_all(&body);
        Ok(())
    });
    let result = draft::forward(&identity, &draft::parse_request(request)?);
    server
        .join()
        .map_err(|_| std::io::Error::other("stub failed"))??;
    Ok(result)
}

fn requests() -> [Value; 2] {
    [
        json!({"op":"get_draft","cube_id":ID}),
        json!({"op":"training_mat","cube_id":ID,"version_id":ID}),
    ]
}

#[test]
fn six_literal_routes_and_methods() -> TestResult {
    for (request, suffix, method, body) in [
        (
            json!({"op":"get_draft","cube_id":ID}),
            "draft".into(),
            "GET",
            None,
        ),
        (
            json!({"op":"store_gesture","cube_id":ID,"body":{"seed":{"point":[2,3]}}}),
            "gestures".into(),
            "POST",
            Some(json!({"seed":{"point":[2,3]}})),
        ),
        (
            json!({"op":"add_region","cube_id":ID,"body":{"revision":0}}),
            "draft/regions".into(),
            "POST",
            Some(json!({"revision":0})),
        ),
        (
            json!({"op":"patch_region","cube_id":ID,"region_id":"r-0001","body":{"revision":1,"deleted":true}}),
            "draft/regions/r-0001".into(),
            "POST",
            Some(json!({"revision":1,"deleted":true})),
        ),
        (
            json!({"op":"confirm","cube_id":ID,"body":{"revision":1}}),
            "draft/confirm".into(),
            "POST",
            Some(json!({"revision":1})),
        ),
        (
            json!({"op":"training_mat","cube_id":ID,"version_id":ID}),
            format!("versions/{ID}/training-mat"),
            "GET",
            None,
        ),
    ] {
        let (url, actual_method, actual_body) = draft::parse_request(request)?.destination(4321)?;
        assert_eq!(
            url.as_str(),
            format!("http://127.0.0.1:4321/api/v1/annotations/{ID}/{suffix}")
        );
        assert_eq!(actual_method.as_str(), method);
        assert_eq!(actual_body, body);
        assert!(url.query().is_none() && url.fragment().is_none());
    }
    Ok(())
}

#[test]
fn paths_methods_candidates_and_extra_fields_are_rejected() {
    for id in [
        "../health",
        "http://example.com",
        "x?query=1",
        "x#fragment",
        "x/other",
    ] {
        assert!(draft::parse_request(json!({"op":"get_draft","cube_id":id})).is_err());
        assert!(
            draft::parse_request(json!({"op":"training_mat","cube_id":ID,"version_id":id}))
                .is_err()
        );
        assert!(
            draft::parse_request(
                json!({"op":"patch_region","cube_id":ID,"region_id":id,"body":{}})
            )
            .is_err()
        );
    }
    for request in [
        json!({"op":"get_draft","cube_id":ID,"method":"DELETE"}),
        json!({"op":"get_draft","cube_id":ID,"path":"/health"}),
        json!({"op":"candidates","cube_id":ID}),
        json!({"op":"rebuild","cube_id":ID}),
        json!({"op":"confirm","cube_id":ID,"body":[]}),
        json!({"op":"store_gesture","cube_id":ID,"body":[]}),
        json!({"op":"store_gesture","cube_id":"../health","body":{}}),
    ] {
        assert!(draft::parse_request(request).is_err());
    }
}

#[test]
fn identity_precedes_status_body_and_limit() -> TestResult {
    for request in requests() {
        for headers in [
            "",
            "X-SpectrumAgent-Boot-Id: wrong\r\nX-SpectrumAgent-Pid: 123\r\n",
            "X-SpectrumAgent-Boot-Id: 1234abcd\r\nX-SpectrumAgent-Pid: 999\r\n",
        ] {
            let error = exchange(
                request.clone(),
                "500 Error",
                headers,
                b"invalid".to_vec(),
                Some(MAX_RESPONSE_BYTES + 1),
            )?
            .err()
            .ok_or("identity error")?;
            assert_eq!(error.error, "DATASET_IDENTITY_MISMATCH");
        }
    }
    Ok(())
}

#[test]
fn declared_and_streamed_limits_json_and_binary() -> TestResult {
    for request in requests() {
        for declared in [true, false] {
            let headers = format!("{IDENTITY}Content-Type: application/octet-stream\r\n");
            let body = if declared {
                vec![]
            } else {
                vec![b' '; (MAX_RESPONSE_BYTES + 1) as usize]
            };
            let error = exchange(
                request.clone(),
                "200 OK",
                &headers,
                body,
                declared.then_some(MAX_RESPONSE_BYTES + 1),
            )?
            .err()
            .ok_or("limit error")?;
            assert_eq!(error.error, "RESPONSE_TOO_LARGE");
        }
    }
    Ok(())
}

#[test]
fn binary_exact_limit_and_base64_padding() -> TestResult {
    for (bytes, encoded) in [
        (b"a".to_vec(), "YQ=="),
        (b"ab".to_vec(), "YWI="),
        (b"abc".to_vec(), "YWJj"),
    ] {
        let value = exchange(
            requests()[1].clone(),
            "200 OK",
            &format!("{IDENTITY}Content-Type: application/octet-stream\r\n"),
            bytes,
            None,
        )??;
        assert_eq!(
            value,
            json!({"content_type":"application/octet-stream","filename":"training_mat.mat","body_base64":encoded})
        );
    }
    let value = exchange(
        requests()[1].clone(),
        "200 OK",
        &format!("{IDENTITY}Content-Type: application/octet-stream\r\n"),
        vec![0; MAX_RESPONSE_BYTES as usize],
        Some(MAX_RESPONSE_BYTES),
    )??;
    assert_eq!(
        value["body_base64"].as_str().ok_or("base64")?.len(),
        (MAX_RESPONSE_BYTES as usize).div_ceil(3) * 4
    );
    Ok(())
}

#[test]
fn http_errors_and_redirects_preserve_status_and_context() -> TestResult {
    for request in requests() {
        let error = exchange(request.clone(), "409 Conflict", IDENTITY, br#"{"error":"OVERLAP_UNRESOLVED","detail":"overlap","context":{"conflict_count":3,"sample_pixels":[[0,1]]}}"#.to_vec(), None)?.err().ok_or("HTTP error")?;
        assert_eq!(error.status_code, Some(409));
        assert_eq!(
            error.context,
            json!({"conflict_count":3,"sample_pixels":[[0,1]]})
        );
        let error = exchange(
            request,
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
fn raw_and_canonical_credentials_never_escape() -> TestResult {
    let escaped = TOKEN
        .chars()
        .map(|c| format!("\\u{:04x}", c as u32))
        .collect::<String>();
    for request in requests() {
        for reflected in [TOKEN.to_owned(), escaped.clone()] {
            let body = format!(r#"{{"error":"REFLECTED","detail":"{reflected}","context":{{}}}}"#)
                .into_bytes();
            let error = exchange(request.clone(), "400 Bad Request", IDENTITY, body, None)?
                .err()
                .ok_or("secret")?;
            assert_eq!(error.error, "SENSITIVE_RESPONSE");
            assert!(!serde_json::to_string(&error)?.contains(TOKEN));
        }
    }
    let error = exchange(
        requests()[1].clone(),
        "200 OK",
        &format!("{IDENTITY}Content-Type: application/octet-stream\r\n"),
        TOKEN.as_bytes().to_vec(),
        None,
    )?
    .err()
    .ok_or("binary secret")?;
    assert_eq!(error.error, "SENSITIVE_RESPONSE");
    Ok(())
}

#[test]
fn binary_requires_octet_stream() -> TestResult {
    let error = exchange(
        requests()[1].clone(),
        "200 OK",
        IDENTITY,
        b"{}".to_vec(),
        None,
    )?
    .err()
    .ok_or("content type")?;
    assert_eq!(error.error, "INVALID_BODY");
    Ok(())
}
