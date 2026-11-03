use std::time::Duration;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum BootAction {
    Wait,
    Reload,
    GiveUp,
}

pub fn boot_decision(boot_seen: bool, reloaded: bool, elapsed: Duration) -> BootAction {
    if boot_seen {
        BootAction::Wait
    } else if !reloaded && elapsed >= Duration::from_secs(5) {
        BootAction::Reload
    } else if reloaded && elapsed >= Duration::from_secs(15) {
        BootAction::GiveUp
    } else {
        BootAction::Wait
    }
}

#[cfg(test)]
mod tests {
    use super::{BootAction, boot_decision};
    use std::time::Duration;

    #[test]
    fn healthy_document_always_waits_across_generations() {
        // Generation does not enter the document-health decision at all.
        for _generation in [1, 2, 99] {
            for reloaded in [false, true] {
                for elapsed in [
                    Duration::ZERO,
                    Duration::from_secs(5),
                    Duration::from_secs(60),
                ] {
                    assert_eq!(boot_decision(true, reloaded, elapsed), BootAction::Wait);
                }
            }
        }
    }

    #[test]
    fn reload_boundary_4999_5000_and_5001_ms() {
        assert_eq!(
            boot_decision(false, false, Duration::from_millis(4999)),
            BootAction::Wait
        );
        assert_eq!(
            boot_decision(false, false, Duration::from_secs(5)),
            BootAction::Reload
        );
        assert_eq!(
            boot_decision(false, false, Duration::from_millis(5001)),
            BootAction::Reload
        );
    }

    #[test]
    fn final_timeout_is_fifteen_seconds_from_window_shown() {
        assert_eq!(
            boot_decision(false, true, Duration::from_millis(14999)),
            BootAction::Wait
        );
        assert_eq!(
            boot_decision(false, true, Duration::from_secs(15)),
            BootAction::GiveUp
        );
        assert_eq!(
            boot_decision(false, true, Duration::from_secs(60)),
            BootAction::GiveUp
        );
    }

    #[test]
    fn before_timeout_wait_and_first_attempt_precedes_give_up() {
        assert_eq!(
            boot_decision(false, false, Duration::ZERO),
            BootAction::Wait
        );
        assert_eq!(
            boot_decision(false, true, Duration::from_secs(5)),
            BootAction::Wait
        );
        assert_eq!(
            boot_decision(false, false, Duration::from_secs(60)),
            BootAction::Reload
        );
    }
}
