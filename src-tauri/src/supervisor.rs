use crate::{
    causality::EngineLogCursor,
    engine_path::EngineSelection,
    handshake::{self, Handshake, HandshakeIssue},
    health::{HealthClient, HealthResult, SmokeFailure, SmokeMetrics},
    logging::ShellLog,
    process::ManagedProcess,
    state::{FailureKind, Phase, StateMachine},
    win32::{SpawnRequest, WaitResult, Win32, WinError},
};
use chrono::{Local, Utc};
#[cfg(debug_assertions)]
#[path = "dev_supervision.rs"]
mod dev_supervision;
use serde::Serialize;
use serde_json::json;
use std::{
    fs, io,
    path::PathBuf,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, RecvTimeoutError, Sender},
    },
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

#[derive(Clone)]
pub struct SupervisorConfig {
    pub process: SpawnRequest,
    pub data_root: PathBuf,
}

#[derive(Clone, Debug, Serialize)]
pub enum ExitReason {
    Win32 { api: &'static str, code: u32 },
    ProcessExit { code: u32 },
    StartupDeadline,
    IdentityMismatch { layer: &'static str },
    WorkerUnavailable,
}

#[derive(Clone, Debug, Serialize)]
pub struct Failure {
    pub kind: FailureKind,
    pub exit_reason: ExitReason,
    pub preexisting_handshake_invalid: Option<HandshakeIssue>,
    pub engine_error: Option<String>,
    pub handshake_path: PathBuf,
    pub log_path: PathBuf,
    pub data_directory: PathBuf,
}

#[derive(Clone, Debug, Serialize)]
pub struct Snapshot {
    pub generation_id: u64,
    pub phase: Phase,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    pub boot_id: Option<String>,
    pub failure: Option<Failure>,
    pub cleanup_complete: bool,
    pub pending_activation: bool,
}

#[derive(Clone, Debug, Serialize)]
pub enum SupervisorEvent {
    Status(Box<Snapshot>),
    AppExit,
}

enum Message {
    DatasetIdentity(Sender<Result<(u64, Arc<Handshake>), &'static str>>),
    Retry,
    Stop,
    Activate,
    Smoke(Sender<Result<SmokeMetrics, SmokeFailure>>),
    SmokeComplete {
        generation: u64,
        reply: Sender<Result<SmokeMetrics, SmokeFailure>>,
        result: Result<SmokeMetrics, SmokeFailure>,
    },
    Health {
        generation: u64,
        result: Result<Handshake, &'static str>,
    },
    Exit {
        generation: u64,
        result: Result<u32, WinError>,
        observed_ms: i64,
        day: String,
    },
    WorkerFailed {
        generation: u64,
    },
}

#[derive(Clone)]
pub struct SupervisorHandle {
    tx: Sender<Message>,
    snapshot: Arc<Mutex<Snapshot>>,
    join: Arc<Mutex<Option<JoinHandle<()>>>>,
}

impl SupervisorHandle {
    pub fn dataset_identity(&self) -> Result<(u64, Arc<Handshake>), &'static str> {
        let (reply, response) = mpsc::channel();
        self.tx.send(Message::DatasetIdentity(reply)).map_err(|_| "ENGINE_NOT_READY")?;
        response.recv_timeout(Duration::from_secs(2)).map_err(|_| "ENGINE_NOT_READY")?
    }
    /// No caller inputs. Blocking channel wait must run on a worker, never the UI thread.
    pub fn run_smoke(&self) -> Result<SmokeMetrics, SmokeFailure> {
        let (reply, response) = mpsc::channel();
        self.tx
            .send(Message::Smoke(reply))
            .map_err(|_| SmokeFailure::NotReady)?;
        response
            .recv_timeout(Duration::from_secs(22))
            .map_err(|_| SmokeFailure::Transport)?
    }
    pub fn snapshot(&self) -> Result<Snapshot, String> {
        self.snapshot
            .lock()
            .map(|s| s.clone())
            .map_err(|_| "supervisor status lock poisoned".to_owned())
    }
    pub fn retry(&self) -> Result<(), String> {
        self.tx
            .send(Message::Retry)
            .map_err(|_| "supervisor stopped".to_owned())
    }
    pub fn activate(&self) -> Result<(), String> {
        self.tx
            .send(Message::Activate)
            .map_err(|_| "supervisor stopped".to_owned())
    }
    pub fn stop(&self) -> Result<(), String> {
        self.tx
            .send(Message::Stop)
            .map_err(|_| "supervisor stopped".to_owned())
    }
    /// Blocking: call only on a worker thread, never a desktop event-loop callback.
    pub fn shutdown_and_join(&self) -> Result<(), String> {
        let _ = self.stop();
        let join = self
            .join
            .lock()
            .map_err(|_| "join lock poisoned".to_owned())?
            .take();
        if let Some(join) = join {
            join.join()
                .map_err(|_| "supervisor thread failed".to_owned())?;
        }
        Ok(())
    }
    #[cfg(feature = "test-probes")]
    pub fn inject_old_exit_for_test(&self, generation: u64) -> Result<(), String> {
        self.tx
            .send(Message::Exit {
                generation,
                result: Ok(99),
                observed_ms: Utc::now().timestamp_millis(),
                day: Local::now().format("%Y%m%d").to_string(),
            })
            .map_err(|_| "supervisor stopped".to_owned())
    }
}

impl Drop for SupervisorHandle {
    fn drop(&mut self) {
        if Arc::strong_count(&self.join) == 1 {
            let _ = self.tx.send(Message::Stop);
        }
    }
}

struct Attempt {
    child: ManagedProcess,
    waiter: Option<JoinHandle<Result<u32, WinError>>>,
    poller: Option<JoinHandle<()>>,
    cancelled: Arc<AtomicBool>,
    cursor: EngineLogCursor,
    deadline: Instant,
}

impl Attempt {
    fn cleanup(&mut self) -> Vec<String> {
        self.cancelled.store(true, Ordering::Release);
        let mut errors = Vec::new();
        if let Some(waiter) = self.waiter.take() {
            if let Err(error) = self.child.request_termination() {
                errors.push(format!("{}:{}", error.api, error.code));
            }
            match waiter.join() {
                Ok(Ok(_)) => self.child.mark_reaped(),
                Ok(Err(error)) => errors.push(format!("{}:{}", error.api, error.code)),
                Err(_) => errors.push("exit_waiter_join".to_owned()),
            }
            // Confirm exit after the waiter has finished before closing the process handle.
        }
        if let Some(poller) = self.poller.take()
            && poller.join().is_err()
        {
            errors.push("health_poller_join".to_owned());
        }
        errors.extend(
            self.child
                .cleanup()
                .into_iter()
                .map(|e| format!("{}:{}", e.api, e.code)),
        );
        errors
    }
}

impl Drop for Attempt {
    fn drop(&mut self) {
        let _ = self.cleanup();
    }
}

pub struct EngineSupervisor;
impl EngineSupervisor {
    pub fn start_selected(
        selection: EngineSelection,
        data_root: PathBuf,
        api: Arc<dyn Win32>,
    ) -> io::Result<(SupervisorHandle, Receiver<SupervisorEvent>)> {
        // DEV ONLY milestone02 source entry. The existing release branch below
        // is byte-for-byte unchanged; explicit test/dev overrides still win.
        #[cfg(debug_assertions)]
        if selection.source == "resolved_resource" {
            return Self::start_inner(
                SupervisorConfig {
                    process: crate::dev_engine::python_request(&data_root)?,
                    data_root,
                },
                api,
                false,
                "development_python",
            );
        }
        let invalid_shape = !selection.valid_shape();
        let source = selection.source;
        Self::start_inner(
            SupervisorConfig {
                process: SpawnRequest {
                    exe: selection.exe,
                    args: vec![],
                },
                data_root,
            },
            api,
            invalid_shape,
            source,
        )
    }

    /// Host precondition: the Tauri single-instance plugin has acquired the application lock.
    /// No product mutex or handshake lifecycle operation is implemented in this core.
    pub fn start(
        config: SupervisorConfig,
        api: Arc<dyn Win32>,
    ) -> io::Result<(SupervisorHandle, Receiver<SupervisorEvent>)> {
        Self::start_inner(config, api, false, "constructor_injection")
    }

    fn start_inner(
        config: SupervisorConfig,
        api: Arc<dyn Win32>,
        invalid_shape: bool,
        selection_source: &'static str,
    ) -> io::Result<(SupervisorHandle, Receiver<SupervisorEvent>)> {
        let log = ShellLog::new(&config.data_root)?;
        let initial = Snapshot {
            generation_id: 1,
            phase: Phase::Starting,
            pid: None,
            port: None,
            boot_id: None,
            failure: None,
            cleanup_complete: false,
            pending_activation: false,
        };
        let snapshot = Arc::new(Mutex::new(initial.clone()));
        let (tx, rx) = mpsc::channel();
        let (events, event_rx) = mpsc::channel();
        let mut actor = Actor {
            config,
            api,
            log,
            machine: StateMachine::default(),
            snapshot: snapshot.clone(),
            view: initial,
            events,
            tx: tx.clone(),
            rx,
            attempt: None,
            preexisting: None,
            verified: None,
            smoke_generation: None,
            pending_cleanup_errors: Vec::new(),
            invalid_shape,
            selection_source,
        };
        let join = thread::Builder::new()
            .name("engine-supervisor".to_owned())
            .spawn(move || actor.run())?;
        Ok((
            SupervisorHandle {
                tx,
                snapshot,
                join: Arc::new(Mutex::new(Some(join))),
            },
            event_rx,
        ))
    }
}

struct Actor {
    invalid_shape: bool,
    selection_source: &'static str,
    config: SupervisorConfig,
    api: Arc<dyn Win32>,
    log: ShellLog,
    machine: StateMachine,
    snapshot: Arc<Mutex<Snapshot>>,
    view: Snapshot,
    events: Sender<SupervisorEvent>,
    tx: Sender<Message>,
    rx: Receiver<Message>,
    attempt: Option<Attempt>,
    preexisting: Option<HandshakeIssue>,
    verified: Option<Arc<Handshake>>,
    smoke_generation: Option<u64>,
    pending_cleanup_errors: Vec<WinError>,
}

impl Actor {
    fn log(&self, event: &str, fields: serde_json::Value) {
        if self.log.event(event, fields).is_err() {
            eprintln!("SpectrumAgent: shell log write failed");
        }
    }
    fn publish(&self) {
        if let Ok(mut snapshot) = self.snapshot.lock() {
            *snapshot = self.view.clone();
        }
        let _ = self
            .events
            .send(SupervisorEvent::Status(Box::new(self.view.clone())));
    }
    fn transition(&mut self, to: Phase, reason: &str) -> bool {
        match self.machine.transition(self.view.generation_id, to, reason) {
            Ok(Some(transition)) => {
                self.log("state_transition",json!({"generation_id":transition.generation_id,"from":transition.from,"to":transition.to,"reason":transition.reason}));
                self.view.phase = to;
                self.publish();
                true
            }
            _ => false,
        }
    }
    fn fail(&mut self, kind: FailureKind, exit_reason: ExitReason, engine_error: Option<String>) {
        self.view.failure = Some(Failure {
            kind,
            exit_reason,
            preexisting_handshake_invalid: self.preexisting.clone(),
            engine_error,
            handshake_path: self.config.data_root.join("run").join("handshake.json"),
            log_path: self
                .log
                .directory()
                .join(format!("engine-{}.jsonl", Local::now().format("%Y%m%d"))),
            data_directory: self.config.data_root.clone(),
        });
        if self.transition(Phase::Failed, "engine_failure") {
            self.log(
                "engine_failure",
                json!({"generation_id":self.view.generation_id,"failure":self.view.failure}),
            );
        }
        self.cleanup();
    }
    fn cleanup(&mut self) {
        self.verified.take();
        self.smoke_generation = None;
        let mut errors: Vec<String> = std::mem::take(&mut self.pending_cleanup_errors)
            .into_iter()
            .map(|e| format!("{}:{}", e.api, e.code))
            .collect();
        errors.extend(
            self.attempt
                .take()
                .map(|mut attempt| attempt.cleanup())
                .unwrap_or_default(),
        );
        self.view.cleanup_complete = errors.is_empty();
        self.log("generation_cleanup",json!({"generation_id":self.view.generation_id,"errors":errors,"complete":self.view.cleanup_complete}));
        self.publish();
    }
    fn start_attempt(&mut self) {
        #[cfg(debug_assertions)]
        if self.selection_source == "development_python" {
            self.start_debug_attempt();
            return;
        }
        let generation = self.view.generation_id;
        self.log(
            "engine_start_attempt",
            json!({"generation_id":generation,"exe":self.config.process.exe,"selection_source":self.selection_source}),
        );
        let mut old_identity = None;
        self.preexisting = match fs::read(self.config.data_root.join("run").join("handshake.json"))
        {
            Ok(bytes) => match handshake::parse(&bytes) {
                Ok(old) => {
                    old_identity = Some(
                        json!({"pid":old.pid,"boot_id":old.boot_id,"port":old.port,"process_created_at_ms":old.process_created_at_ms}),
                    );
                    None
                }
                Err(issue) => Some(issue),
            },
            Err(e) if e.kind() == io::ErrorKind::NotFound => None,
            Err(_) => Some(HandshakeIssue::ReadFailed),
        };
        self.log(
            "preexisting_handshake_snapshot",
            json!({"generation_id":generation,"preexisting_handshake_invalid":self.preexisting,"old_identity":old_identity}),
        );
        if self.invalid_shape {
            self.fail(
                FailureKind::SpawnFailed,
                ExitReason::Win32 {
                    api: "EnginePathValidation",
                    code: 87,
                },
                None,
            );
            return;
        }
        let cursor = match EngineLogCursor::capture(
            self.log.directory(),
            Local::now().format("%Y%m%d").to_string(),
        ) {
            Ok(cursor) => cursor,
            Err(_) => {
                self.fail(
                    FailureKind::SpawnFailed,
                    ExitReason::WorkerUnavailable,
                    None,
                );
                return;
            }
        };
        let started = Instant::now();
        let child = ManagedProcess::launch_observed(
            self.api.clone(),
            &self.config.process,
            |event, pid| self.log(event, json!({"generation_id":generation,"pid":pid})),
        );
        let child = match child {
            Ok(child) => child,
            Err(failure) => {
                self.view.pid = failure.pid;
                self.pending_cleanup_errors = failure.cleanup_errors;
                self.fail(
                    failure.kind,
                    ExitReason::Win32 {
                        api: failure.error.api,
                        code: failure.error.code,
                    },
                    None,
                );
                return;
            }
        };
        self.view.pid = Some(child.pid);
        self.log("process_identity_recorded", json!({"generation_id":generation,"pid":child.pid,"process_created_at_ms":child.created_at_ms}));
        let cancelled = Arc::new(AtomicBool::new(false));
        let mut attempt = Attempt {
            child,
            waiter: None,
            poller: None,
            cancelled: cancelled.clone(),
            cursor,
            deadline: started + Duration::from_secs(30),
        };
        let Some(raw) = attempt.child.raw() else {
            self.attempt = Some(attempt);
            self.fail(
                FailureKind::ProcessIdentityFailed,
                ExitReason::WorkerUnavailable,
                None,
            );
            return;
        };
        let api = self.api.clone();
        let tx = self.tx.clone();
        let exit_log = self.log.clone();
        let exit_pid = attempt.child.pid;
        attempt.waiter = match thread::Builder::new()
            .name(format!("engine-exit-{generation}"))
            .spawn(move || {
                let result = api.wait(raw, None).and_then(|wait| match wait {
                    WaitResult::Exited => api.exit_code(raw),
                    WaitResult::Timeout => Err(WinError {
                        api: "WaitForSingleObject",
                        code: 258,
                    }),
                });
                let _=exit_log.event("engine_process_exit",json!({"generation_id":generation,"pid":exit_pid,"exit_code":result.as_ref().ok(),"wait_error":result.as_ref().err()}));
                let _ = tx.send(Message::Exit {
                    generation,
                    result: result.clone(),
                    observed_ms: Utc::now().timestamp_millis(),
                    day: Local::now().format("%Y%m%d").to_string(),
                });
                result
            }) {
            Ok(waiter) => Some(waiter),
            Err(_) => {
                self.attempt = Some(attempt);
                self.fail(
                    FailureKind::SpawnFailed,
                    ExitReason::WorkerUnavailable,
                    None,
                );
                return;
            }
        };
        let tx = self.tx.clone();
        let path = self.config.data_root.join("run").join("handshake.json");
        let pid = attempt.child.pid;
        let created = attempt.child.created_at_ms;
        let log = self.log.clone();
        attempt.poller=match thread::Builder::new().name(format!("engine-health-{generation}")).spawn(move || {
            let client=match HealthClient::new() {Ok(client)=>client,Err(_)=>{let _=tx.send(Message::WorkerFailed {generation});return;}};
            let mut last_issue=None;
            while !cancelled.load(Ordering::Acquire) {
                match fs::read(&path).ok().and_then(|bytes|handshake::parse(&bytes).ok()) {
                    Some(handshake) if handshake.pid==pid && handshake.process_created_at_ms==created => {
                        let _=log.event("handshake_identity_verified",json!({"generation_id":generation,"pid":pid,"boot_id":handshake.boot_id,"process_created_at_ms":created}));
                        match client.check(&handshake) {
                            HealthResult::Matching=>{let _=tx.send(Message::Health {generation,result:Ok(handshake)});return;},
                            HealthResult::IdentityMismatch(layer)=>{let _=tx.send(Message::Health {generation,result:Err(layer)});return;},
                            HealthResult::Pending=>{}
                        }
                    },
                    Some(_) => {if last_issue!=Some("foreign_identity") {let _=log.event("handshake_ignored",json!({"generation_id":generation,"reason":"foreign_identity"}));last_issue=Some("foreign_identity");}},
                    None => {if last_issue!=Some("not_valid_yet") {let _=log.event("handshake_wait",json!({"generation_id":generation,"reason":"not_valid_yet"}));last_issue=Some("not_valid_yet");}},
                }
                thread::sleep(Duration::from_millis(40));
            }
        }) {Ok(poller)=>Some(poller),Err(_)=>{self.attempt=Some(attempt);self.fail(FailureKind::SpawnFailed,ExitReason::WorkerUnavailable,None);return;}};
        self.attempt = Some(attempt);
        self.publish();
    }
    fn run(&mut self) {
        self.start_attempt();
        loop {
            if self.machine.phase() == Phase::Starting
                && self
                    .attempt
                    .as_ref()
                    .is_some_and(|attempt| Instant::now() >= attempt.deadline)
            {
                self.fail(
                    FailureKind::StartupTimeout,
                    ExitReason::StartupDeadline,
                    None,
                );
            }
            let message = match self.rx.recv_timeout(Duration::from_millis(20)) {
                Ok(message) => message,
                Err(RecvTimeoutError::Timeout) => {
                    if self.machine.phase() == Phase::Starting
                        && self
                            .attempt
                            .as_ref()
                            .is_some_and(|attempt| Instant::now() >= attempt.deadline)
                    {
                        self.fail(
                            FailureKind::StartupTimeout,
                            ExitReason::StartupDeadline,
                            None,
                        );
                    }
                    continue;
                }
                Err(RecvTimeoutError::Disconnected) => Message::Stop,
            };
            match message {
                Message::DatasetIdentity(reply) => {
                    let identity = self.verified.as_ref()
                        .filter(|_| self.machine.phase() == Phase::Ready)
                        .map(|identity| (self.view.generation_id, identity.clone()))
                        .ok_or("ENGINE_NOT_READY");
                    let _ = reply.send(identity);
                }
                Message::Smoke(reply) => {
                    let Some(identity) = self
                        .verified
                        .as_ref()
                        .filter(|_| self.machine.phase() == Phase::Ready)
                        .cloned()
                    else {
                        let _ = reply.send(Err(SmokeFailure::NotReady));
                        continue;
                    };
                    if self.smoke_generation.is_some() {
                        let _ = reply.send(Err(SmokeFailure::Busy));
                        continue;
                    }
                    let generation = self.view.generation_id;
                    self.smoke_generation = Some(generation);
                    self.log("smoke_requested", json!({"generation_id":generation}));
                    let tx = self.tx.clone();
                    let on_spawn_failure = reply.clone();
                    if thread::Builder::new()
                        .name(format!("engine-smoke-{generation}"))
                        .spawn(move || {
                            let result = HealthClient::new()
                                .map_err(|_| SmokeFailure::Transport)
                                .and_then(|client| client.smoke(&identity));
                            let _ = tx.send(Message::SmokeComplete {
                                generation,
                                reply,
                                result,
                            });
                        })
                        .is_err()
                    {
                        self.smoke_generation = None;
                        let _ = on_spawn_failure.send(Err(SmokeFailure::Transport));
                    }
                }
                Message::SmokeComplete {
                    generation,
                    reply,
                    result,
                } => {
                    if generation != self.view.generation_id || self.machine.phase() != Phase::Ready
                    {
                        let _ = reply.send(Err(SmokeFailure::StaleGeneration));
                        self.log("stale_smoke_result_discarded", json!({"generation_id":self.view.generation_id,"result_generation":generation}));
                        continue;
                    }
                    self.smoke_generation = None;
                    self.log(
                        "smoke_finished",
                        json!({"generation_id":generation,"result":result}),
                    );
                    if let Err(SmokeFailure::IdentityMismatch { layer }) = &result {
                        self.fail(
                            FailureKind::SmokeIdentityMismatch,
                            ExitReason::IdentityMismatch { layer },
                            None,
                        );
                    }
                    let _ = reply.send(result);
                }
                Message::Stop => {
                    self.transition(Phase::Stopping, "application_close");
                    self.cleanup();
                    self.log("app_exit", json!({"generation_id":self.view.generation_id}));
                    let _ = self.events.send(SupervisorEvent::AppExit);
                    return;
                }
                Message::Activate => {
                    self.view.pending_activation = true;
                    self.log("activation_requested",json!({"generation_id":self.view.generation_id,"phase":self.view.phase,"pending_activation":true}));
                    self.publish();
                }
                Message::Retry
                    if self.machine.phase() == Phase::Failed && self.view.cleanup_complete =>
                {
                    if let Ok(transition) = self.machine.retry_after_cleanup() {
                        self.log("state_transition",json!({"generation_id":transition.generation_id,"from":transition.from,"to":transition.to,"reason":transition.reason}));
                        self.view.generation_id = transition.generation_id;
                        self.view.phase = Phase::Starting;
                        self.view.failure = None;
                        self.view.pid = None;
                        self.view.port = None;
                        self.view.boot_id = None;
                        self.view.cleanup_complete = false;
                        self.publish();
                        self.start_attempt();
                    }
                }
                Message::Retry => {}
                Message::Health { generation, result }
                    if generation == self.view.generation_id
                        && self.machine.phase() == Phase::Starting =>
                {
                    #[cfg(debug_assertions)]
                    if self.selection_source == "development_python" {
                        self.complete_debug_health(generation, result);
                        continue;
                    }
                    // The blocking waiter is independent; reject a health response if exit is already observable.
                    let alive = self
                        .attempt
                        .as_ref()
                        .and_then(|a| a.child.raw())
                        .is_some_and(|raw| {
                            matches!(self.api.wait(raw, Some(0)), Ok(WaitResult::Timeout))
                        });
                    if !alive {
                        continue;
                    }
                    match result {
                        Ok(handshake) => {
                            self.view.port = Some(handshake.port);
                            self.view.boot_id = Some(handshake.boot_id.clone());
                            self.log("health_verified",json!({"generation_id":generation,"pid":handshake.pid,"port":handshake.port}));
                            self.verified = Some(Arc::new(handshake));
                            self.transition(Phase::Ready, "health_identity_matched");
                        }
                        Err(layer) => self.fail(
                            FailureKind::HealthIdentityMismatch,
                            ExitReason::IdentityMismatch { layer },
                            None,
                        ),
                    }
                }
                Message::Exit {
                    generation,
                    result,
                    observed_ms,
                    day,
                } if generation == self.view.generation_id => {
                    let Some(mut kind) = self.machine.exit_failure(generation) else {
                        continue;
                    };
                    let reason = match result {
                        Ok(code) => ExitReason::ProcessExit { code },
                        Err(error) => ExitReason::Win32 {
                            api: error.api,
                            code: error.code,
                        },
                    };
                    let mut engine_error = None;
                    if let Some(attempt) = self.attempt.as_mut() {
                        if matches!(reason, ExitReason::ProcessExit { .. }) {
                            attempt.child.mark_reaped();
                        }
                        if kind == FailureKind::ExitedBeforeReady
                            && let Ok(Some(code)) = attempt.cursor.find_cause(
                                attempt.child.pid,
                                attempt.child.created_at_ms,
                                observed_ms,
                                &day,
                            )
                        {
                            kind = FailureKind::HandshakeInvalid;
                            engine_error = Some(code);
                        }
                    }
                    self.fail(kind, reason, engine_error);
                }
                Message::WorkerFailed { generation }
                    if generation == self.view.generation_id
                        && self.machine.phase() == Phase::Starting =>
                {
                    self.fail(
                        FailureKind::SpawnFailed,
                        ExitReason::WorkerUnavailable,
                        None,
                    )
                }
                _ => self.log(
                    "stale_generation_result_discarded",
                    json!({"generation_id":self.view.generation_id}),
                ),
            }
        }
    }
}
