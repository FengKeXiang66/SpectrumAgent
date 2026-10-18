use serde_json::{Value, json};
use spectrum_agent::{
    handshake::{self, HandshakeIssue},
    state::{FailureKind, Phase, StateMachine},
};

fn valid() -> Value {
    json!({"boot_id":"1234abcd","pid":42,"process_created_at":"2026-10-18T00:00:00.123Z","port":54321,"token":"abcdef0123456789abcdef0123456789","protocol":1,"version":"0.1.0","started_at":"2026-10-18T00:00:01.001Z"})
}

fn reject(value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let encoded = serde_json::to_vec(value)?;
    let result = handshake::parse(&encoded);
    assert!(result.is_err());
    if let Err(error) = result {
        let message = format!("{error:?} {error}");
        assert!(!message.contains("abcdef0123456789abcdef0123456789"));
    }
    Ok(())
}

#[test]
fn valid_handshake_values_and_integer_utc_comparison() -> Result<(), Box<dyn std::error::Error>> {
    let parsed = handshake::parse(&serde_json::to_vec(&valid())?)?;
    assert_eq!(parsed.boot_id, "1234abcd");
    assert_eq!(parsed.pid, 42);
    assert_eq!(parsed.port, 54321);
    assert_eq!(parsed.token(), "abcdef0123456789abcdef0123456789");
    assert_eq!(parsed.started_at_ms - parsed.process_created_at_ms, 878);
    Ok(())
}

#[test]
fn exact_fields_and_top_level_are_enforced() -> Result<(), Box<dyn std::error::Error>> {
    assert!(matches!(
        handshake::parse(b"{"),
        Err(HandshakeIssue::InvalidJson)
    ));
    for top in [
        json!([]),
        json!("string"),
        json!(1),
        json!(null),
        json!(true),
    ] {
        reject(&top)?;
    }
    let original = valid();
    let object = original.as_object().ok_or("fixture must be object")?;
    for key in object.keys() {
        let mut value = original.clone();
        value
            .as_object_mut()
            .ok_or("fixture must be object")?
            .remove(key);
        reject(&value)?;
    }
    let mut extra = original.clone();
    extra["unknown"] = json!("abcdef0123456789abcdef0123456789");
    reject(&extra)?;
    Ok(())
}

#[test]
fn metadata_types_bounds_and_exact_strings_are_enforced() -> Result<(), Box<dyn std::error::Error>>
{
    let cases: [(&str, Vec<Value>); 6] = [
        (
            "boot_id",
            vec![
                json!(null),
                json!(1234),
                json!("123abcd"),
                json!("12345abcd"),
                json!("1234ABCD"),
                json!("zzzzzzzz"),
            ],
        ),
        (
            "token",
            vec![
                json!(null),
                json!(3),
                json!(""),
                json!("a".repeat(31)),
                json!("a".repeat(33)),
                json!("A".repeat(32)),
            ],
        ),
        (
            "pid",
            vec![
                json!(true),
                json!(false),
                json!("42"),
                json!(1.0),
                json!(0),
                json!(-1),
                json!(4294967296_u64),
            ],
        ),
        (
            "port",
            vec![
                json!(true),
                json!(false),
                json!("54321"),
                json!(1.0),
                json!(0),
                json!(-1),
                json!(65536),
            ],
        ),
        (
            "protocol",
            vec![
                json!(true),
                json!(false),
                json!("1"),
                json!(1.0),
                json!(0),
                json!(2),
            ],
        ),
        (
            "version",
            vec![json!(null), json!(1), json!("0.1.1"), json!("0.1.0 ")],
        ),
    ];
    for (field, values) in cases {
        for value in values {
            let mut payload = valid();
            payload[field] = value;
            reject(&payload)?;
        }
    }
    for (field, good) in [("pid", json!(u32::MAX)), ("port", json!(u16::MAX))] {
        let mut payload = valid();
        payload[field] = good;
        assert!(handshake::parse(&serde_json::to_vec(&payload)?).is_ok());
    }
    Ok(())
}

#[test]
fn times_reject_nonexistent_dates_leap_seconds_and_non_millisecond_formats()
-> Result<(), Box<dyn std::error::Error>> {
    for field in ["process_created_at", "started_at"] {
        for value in [
            json!(123),
            json!(null),
            json!("2026-02-30T00:00:00.123Z"),
            json!("2026-10-18T00:00:60.123Z"),
            json!("0000-01-01T00:00:00.123Z"),
            json!("2026-10-18T00:00:00Z"),
            json!("2026-10-18T00:00:00.12Z"),
            json!("2026-10-18T00:00:00.1234Z"),
            json!("2026-10-18T00:00:00.123+00:00"),
            json!("2026-10-18t00:00:00.123Z"),
            json!("2026-10-18T24:00:00.123Z"),
        ] {
            let mut payload = valid();
            payload[field] = value;
            reject(&payload)?;
        }
    }
    assert!(handshake::utc_millis("2024-02-29T23:59:59.999Z").is_some());
    Ok(())
}

#[test]
fn all_transition_pairs_and_stopping_terminal_rule() {
    for from in [
        Phase::Starting,
        Phase::Ready,
        Phase::Failed,
        Phase::Stopping,
    ] {
        for to in [
            Phase::Starting,
            Phase::Ready,
            Phase::Failed,
            Phase::Stopping,
        ] {
            let mut machine = StateMachine::default();
            if from != Phase::Starting {
                assert!(machine.transition(1, from, "setup").is_ok());
            }
            let allowed = matches!(
                (from, to),
                (
                    Phase::Starting,
                    Phase::Ready | Phase::Failed | Phase::Stopping
                ) | (Phase::Ready, Phase::Failed | Phase::Stopping)
                    | (Phase::Failed, Phase::Starting | Phase::Stopping)
            );
            assert_eq!(machine.transition(1, to, "test").is_ok(), allowed);
        }
    }
}

#[test]
fn late_generation_and_expected_exit_cannot_fail_current_attempt() -> Result<(), String> {
    let mut machine = StateMachine::default();
    assert_eq!(
        machine.exit_failure(1),
        Some(FailureKind::ExitedBeforeReady)
    );
    machine
        .transition(1, Phase::Failed, "A_failed")
        .map_err(|e| format!("{e:?}"))?;
    let transition = machine
        .retry_after_cleanup()
        .map_err(|e| format!("{e:?}"))?;
    assert_eq!(transition.generation_id, 2);
    assert!(
        machine
            .transition(1, Phase::Failed, "late_A")
            .map_err(|e| format!("{e:?}"))?
            .is_none()
    );
    assert_eq!(machine.exit_failure(1), None);
    assert_eq!(machine.phase(), Phase::Starting);
    machine
        .transition(2, Phase::Ready, "B_ready")
        .map_err(|e| format!("{e:?}"))?;
    assert_eq!(
        machine.exit_failure(2),
        Some(FailureKind::EngineExitedAfterReady)
    );
    machine
        .transition(2, Phase::Stopping, "close")
        .map_err(|e| format!("{e:?}"))?;
    assert_eq!(machine.exit_failure(2), None);
    assert!(machine.retry_after_cleanup().is_err());
    Ok(())
}
