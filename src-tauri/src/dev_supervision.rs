//! DEV ONLY venv launcher adaptation. Release uses the original actor path.
use super::*;
use crate::process::validate_dev_process;

impl Actor {
    pub(super) fn start_debug_attempt(&mut self) {
        let generation = self.view.generation_id;
        self.log("engine_start_attempt", json!({"generation_id":generation,"exe":self.config.process.exe,"selection_source":"development_python"}));
        self.preexisting = fs::read(self.config.data_root.join("run/handshake.json"))
            .ok()
            .and_then(|bytes| handshake::parse(&bytes).err());
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
        let child = match ManagedProcess::launch_observed(
            self.api.clone(),
            &self.config.process,
            |event, pid| self.log(event, json!({"generation_id":generation,"pid":pid})),
        ) {
            Ok(child) => child,
            Err(error) => {
                self.pending_cleanup_errors = error.cleanup_errors;
                self.fail(
                    error.kind,
                    ExitReason::Win32 {
                        api: error.error.api,
                        code: error.error.code,
                    },
                    None,
                );
                return;
            }
        };
        let Some(job) = child.dev_job() else {
            self.fail(
                FailureKind::JobSetupFailed,
                ExitReason::WorkerUnavailable,
                None,
            );
            return;
        };
        let Some(launcher) = child.raw() else {
            self.fail(
                FailureKind::ProcessIdentityFailed,
                ExitReason::WorkerUnavailable,
                None,
            );
            return;
        };
        let launcher_pid = child.pid;
        let launcher_created = child.created_at_ms;
        self.log("dev_launcher_identity",json!({"generation_id":generation,"launcher_pid":launcher_pid,"created_at_ms":child.created_at_ms}));
        let cancelled = Arc::new(AtomicBool::new(false));
        let mut attempt = Attempt {
            child,
            waiter: None,
            poller: None,
            cancelled: cancelled.clone(),
            cursor,
            deadline: started + Duration::from_secs(30),
        };
        let api = self.api.clone();
        let tx = self.tx.clone();
        let log = self.log.clone();
        let path = self.config.data_root.join("run").join("handshake.json");
        attempt.poller=match thread::Builder::new().name(format!("dev-python-health-{generation}")).spawn(move || {
            let client=match HealthClient::new(){Ok(client)=>client,Err(_)=>{let _=tx.send(Message::WorkerFailed{generation});return;}};
            while !cancelled.load(Ordering::Acquire) {
                if let Some(identity)=fs::read(&path).ok().and_then(|bytes|handshake::parse(&bytes).ok()) {
                    // Stale handshakes from prior boots are ignored; candidates
                    // born before this launcher cannot be our Python child.
                    if identity.process_created_at_ms >= launcher_created {
                        let checked=api.open_dev_process(identity.pid).and_then(|raw| {
                            let result=validate_dev_process(api.as_ref(),raw,job,identity.process_created_at_ms);
                            let closed=api.close(raw);
                            result.and(closed)
                        });
                        if let Err(error)=checked {
                            let _=log.event("dev_identity_rejected",json!({"generation_id":generation,"python_pid":identity.pid,"error":error}));
                            let _=tx.send(Message::Health{generation,result:Err("dev_job_or_creation_time")});return;
                        }
                        match client.check(&identity) {
                            HealthResult::Matching=>{let _=tx.send(Message::Health{generation,result:Ok(identity)});return;},
                            HealthResult::IdentityMismatch(layer)=>{let _=tx.send(Message::Health{generation,result:Err(layer)});return;},
                            HealthResult::Pending=>{}
                        }
                    }
                }
                if matches!(api.wait(launcher,Some(0)),Ok(WaitResult::Exited)) {
                    let result=api.exit_code(launcher);
                    let _=tx.send(Message::Exit{generation,result,observed_ms:Utc::now().timestamp_millis(),day:Local::now().format("%Y%m%d").to_string()});return;
                }
                thread::sleep(Duration::from_millis(40));
            }
        }) {Ok(poller)=>Some(poller),Err(_)=>{self.attempt=Some(attempt);self.fail(FailureKind::SpawnFailed,ExitReason::WorkerUnavailable,None);return;}};
        self.attempt = Some(attempt);
        self.publish();
    }

    pub(super) fn complete_debug_health(
        &mut self,
        generation: u64,
        result: Result<Handshake, &'static str>,
    ) {
        let identity = match result {
            Ok(identity) => identity,
            Err(layer) => {
                self.fail(
                    FailureKind::HealthIdentityMismatch,
                    ExitReason::IdentityMismatch { layer },
                    None,
                );
                return;
            }
        };
        let Some(attempt) = self.attempt.as_mut() else {
            return;
        };
        let launcher_pid = attempt.child.pid;
        if let Err(error) = attempt
            .child
            .adopt_dev_python(identity.pid, identity.process_created_at_ms)
        {
            self.fail(
                FailureKind::ProcessIdentityFailed,
                ExitReason::Win32 {
                    api: error.api,
                    code: error.code,
                },
                None,
            );
            return;
        }
        let Some(raw) = attempt.child.raw() else {
            self.fail(
                FailureKind::ProcessIdentityFailed,
                ExitReason::WorkerUnavailable,
                None,
            );
            return;
        };
        let api = self.api.clone();
        let tx = self.tx.clone();
        let log = self.log.clone();
        let pid = identity.pid;
        attempt.waiter=match thread::Builder::new().name(format!("dev-python-exit-{generation}")).spawn(move || {
            let result=api.wait(raw,None).and_then(|_|api.exit_code(raw));
            let _=log.event("engine_process_exit",json!({"generation_id":generation,"pid":pid,"launcher_pid":launcher_pid,"exit_code":result.as_ref().ok(),"wait_error":result.as_ref().err()}));
            let _=tx.send(Message::Exit{generation,result:result.clone(),observed_ms:Utc::now().timestamp_millis(),day:Local::now().format("%Y%m%d").to_string()});result
        }) {Ok(waiter)=>Some(waiter),Err(_)=>{self.fail(FailureKind::SpawnFailed,ExitReason::WorkerUnavailable,None);return;}};
        self.view.pid = Some(identity.pid);
        self.view.port = Some(identity.port);
        self.view.boot_id = Some(identity.boot_id.clone());
        self.log("dev_python_identity_verified",json!({"generation_id":generation,"launcher_pid":launcher_pid,"python_pid":identity.pid,"same_job":true,"process_created_at_ms":identity.process_created_at_ms,"boot_id":identity.boot_id}));
        self.verified = Some(Arc::new(identity));
        self.transition(Phase::Ready, "health_identity_matched");
    }
}
