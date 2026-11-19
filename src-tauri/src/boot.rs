use std::time::Duration;

/// Window title declared in tauri.conf.json. Restored when a late document
/// boot arrives after the monitor already gave up and showed the fallback.
pub const NORMAL_TITLE: &str = "光谱数据 AI Agent";
/// Neutral waiting title shown if the document has not booted within budget.
/// Never claims a failure: diagnostics stay in the shell log / boot_failure.json.
pub const PENDING_TITLE: &str = "光谱数据 AI Agent — 加载中…";

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

/// One-shot guard: only a boot that arrives after a real GiveUp restores the
/// title, and only once. Normal cold starts never touch window.title.
#[derive(Default)]
pub struct TitleRecovery {
    degraded: bool,
}

impl TitleRecovery {
    pub fn mark_degraded(&mut self) {
        self.degraded = true;
    }

    pub fn take_restore(&mut self) -> bool {
        std::mem::take(&mut self.degraded)
    }
}

#[cfg(test)]
mod tests {
    use super::{BootAction, NORMAL_TITLE, PENDING_TITLE, TitleRecovery, boot_decision};
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

    #[test]
    fn title_restores_once_only_after_a_real_give_up() {
        let mut recovery = TitleRecovery::default();
        // Healthy boot never degraded the title: nothing to restore.
        assert!(!recovery.take_restore());
        assert_eq!(boot_decision(true, false, Duration::from_secs(60)), BootAction::Wait);
        assert!(!recovery.take_restore());

        // A GiveUp degrades the title; the next boot restores exactly once.
        assert_eq!(
            boot_decision(false, true, Duration::from_secs(15)),
            BootAction::GiveUp
        );
        recovery.mark_degraded();
        assert!(recovery.take_restore());
        assert!(!recovery.take_restore(), "restoration must be one-shot");
    }

    #[test]
    fn normal_title_is_the_declared_window_title() {
        assert_eq!(NORMAL_TITLE, "光谱数据 AI Agent");
    }

    #[test]
    fn pending_title_waits_without_claiming_a_failure() {
        // A slow document is not a failed document: never show error wording.
        assert!(PENDING_TITLE.contains("加载中"));
        assert!(!PENDING_TITLE.contains("未加载"));
        assert!(!PENDING_TITLE.contains("失败"));
        assert!(!PENDING_TITLE.contains("查看日志"));
        assert_ne!(PENDING_TITLE, NORMAL_TITLE);
    }
}
