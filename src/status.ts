export type Phase = 'Starting' | 'Ready' | 'Failed' | 'Stopping';
export type ExitReason = { ProcessExit: { code: number } } | { Win32: { api: string; code: number } } | { IdentityMismatch: { layer: string } } | 'StartupDeadline' | 'WorkerUnavailable';
export type Failure = { kind: string; exit_reason: ExitReason; engine_error: string | null; handshake_path: string; log_path: string; data_directory: string };
export type Snapshot = { generation_id: number; phase: Phase; pid: number | null; port: number | null; boot_id: string | null; failure: Failure | null; cleanup_complete: boolean };

// A snapshot reply can race an event already delivered for the same generation.
export function acceptSnapshot(previous: Snapshot, next: Snapshot): Snapshot {
  if (next.generation_id < previous.generation_id) return previous;
  if (next.generation_id > previous.generation_id || next.phase === previous.phase) return next;
  const allowed = (previous.phase === 'Starting' && ['Ready', 'Failed', 'Stopping'].includes(next.phase))
    || (previous.phase === 'Ready' && ['Failed', 'Stopping'].includes(next.phase))
    || (previous.phase === 'Failed' && next.phase === 'Stopping');
  return allowed ? next : previous;
}
