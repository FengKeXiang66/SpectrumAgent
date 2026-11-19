use serde::Serialize;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum Phase {
    Starting,
    Ready,
    Failed,
    Stopping,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
pub enum FailureKind {
    SpawnFailed,
    JobSetupFailed,
    ResumeFailed,
    ProcessIdentityFailed,
    ExitedBeforeReady,
    HandshakeInvalid,
    StartupTimeout,
    HealthIdentityMismatch,
    SmokeIdentityMismatch,
    EngineExitedAfterReady,
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct Transition {
    pub generation_id: u64,
    pub from: Phase,
    pub to: Phase,
    pub reason: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum StateError {
    InvalidTransition { from: Phase, to: Phase },
    GenerationExhausted,
}

pub struct StateMachine {
    generation: u64,
    phase: Phase,
}

impl Default for StateMachine {
    fn default() -> Self {
        Self {
            generation: 1,
            phase: Phase::Starting,
        }
    }
}

impl StateMachine {
    pub fn generation(&self) -> u64 {
        self.generation
    }
    pub fn phase(&self) -> Phase {
        self.phase
    }

    pub fn transition(
        &mut self,
        generation: u64,
        to: Phase,
        reason: &str,
    ) -> Result<Option<Transition>, StateError> {
        if generation != self.generation {
            return Ok(None);
        }
        let allowed = matches!(
            (self.phase, to),
            (
                Phase::Starting,
                Phase::Ready | Phase::Failed | Phase::Stopping
            ) | (Phase::Ready, Phase::Failed | Phase::Stopping)
                | (Phase::Failed, Phase::Starting | Phase::Stopping)
        );
        if !allowed {
            return Err(StateError::InvalidTransition {
                from: self.phase,
                to,
            });
        }
        let transition = Transition {
            generation_id: generation,
            from: self.phase,
            to,
            reason: reason.to_owned(),
        };
        self.phase = to;
        Ok(Some(transition))
    }

    // The supervisor calls this only after the previous process has been reaped.
    pub fn retry_after_cleanup(&mut self) -> Result<Transition, StateError> {
        if self.phase != Phase::Failed {
            return Err(StateError::InvalidTransition {
                from: self.phase,
                to: Phase::Starting,
            });
        }
        let next = self
            .generation
            .checked_add(1)
            .ok_or(StateError::GenerationExhausted)?;
        self.generation = next;
        let from = self.phase;
        self.phase = Phase::Starting;
        Ok(Transition {
            generation_id: next,
            from,
            to: self.phase,
            reason: "retry_after_cleanup".to_owned(),
        })
    }

    pub fn exit_failure(&self, generation: u64) -> Option<FailureKind> {
        if generation != self.generation {
            return None;
        }
        match self.phase {
            Phase::Starting => Some(FailureKind::ExitedBeforeReady),
            Phase::Ready => Some(FailureKind::EngineExitedAfterReady),
            Phase::Failed | Phase::Stopping => None,
        }
    }
}
