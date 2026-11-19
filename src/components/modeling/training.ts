import type { ClassificationBody, Result } from './api.ts';

export type TrainingJob = { job_id: string; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';
  run_id: string | null; error: unknown; engine_boot_id?: string; snapshot_version?: number; phase?: string;
  elapsed_s?: number; phase_elapsed_s?: number; cancel_requested?: boolean; cancelable?: boolean;
  completed_folds?: number[]; reused_folds?: number[]; baseline_folds?: number[]; total_folds?: number;
  result_status?: string; retry_of?: string | null; training_set_version_id?: string | null; current?: Record<string, unknown>;
  event_cursor?: number; band_selection?: string | null;
  eta_seconds?: number | null; stage_eta_seconds?: number | null; eta?: { state: string; method: string; samples: number; scope: string } };
export type TrainingEvent = { seq: number; at: string; elapsed_s: number; phase: string; [key: string]: unknown };
export type TrainingView = { job: TrainingJob | null; progress: TrainingProgress | null; events: TrainingEvent[]; error: unknown; result: Result | null };
export type TrainingProgress = { job_id: string; status: 'submitting' | 'queued' | 'running' | 'reconnecting' | 'unavailable'; elapsed: number };
type Reporter = (progress: TrainingProgress) => void;
type JobState = { id: string; body: ClassificationBody | null; key: string; started: number; attempted: boolean;
  reporters: Set<Reporter>; promise?: Promise<Result> };

function transport(error: unknown): boolean {
  return !!error && typeof error === 'object' && 'error' in error
    && (error.error === 'TRANSPORT' || error.error === 'ENGINE_NOT_READY');
}

export function trainingMonitor(api: {
  submit(id: string, body: ClassificationBody): Promise<TrainingJob>;
  status(id: string): Promise<TrainingJob>;
  result(id: string): Promise<Result>;
  list?(): Promise<{ items: TrainingJob[]; engine_boot_id: string }>;
  events?(id: string, after: number): Promise<{ events: TrainingEvent[]; cursor: number }>;
  cancel?(id: string): Promise<TrainingJob>;
  resume?(id: string, next: string): Promise<TrainingJob>;
}, pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms))) {
  // Retain the receipt across screen changes and temporarily unavailable polling.
  let current: JobState | null = null;
  let view: TrainingView = { job: null, progress: null, events: [], error: null, result: null };
  const listeners = new Set<() => void>();
  const continuations = new Map<string, string>();
  let generation = 0, discovery: Promise<void> | undefined;
  const publish = (change: Partial<TrainingView>) => { view = { ...view, ...change }; listeners.forEach(fn => fn()); };
  const accept = (receipt: TrainingJob) => {
    if (view.job?.job_id === receipt.job_id && view.job.engine_boot_id === receipt.engine_boot_id
      && (receipt.snapshot_version ?? 0) < (view.job.snapshot_version ?? 0)) return;
    publish({ job: receipt });
  };
  const report = (job: JobState, status: TrainingProgress['status']) => {
    const progress = { job_id: job.id, status, elapsed: Math.floor((Date.now() - job.started) / 1000) };
    publish({ progress });
    job.reporters.forEach(listener => listener(progress));
  };
  const unavailable = { error: 'TRAINING_STATUS_UNAVAILABLE',
    detail: '暂时无法读取训练状态，后台任务可能仍在运行。请继续查询状态，避免重复训练。', context: {} };
  const execute = async (job: JobState): Promise<Result> => {
    const epoch = generation;
    let receipt: TrainingJob | undefined;
    try {
      if (!job.attempted) {
        job.attempted = true;
        report(job, 'submitting');
        try { receipt = await api.submit(job.id, job.body!); }
        catch (error) { if (!transport(error)) throw error; if (epoch === generation) report(job, 'reconnecting'); }
      }
      let failures = 0;
      for (;;) {
        if (epoch !== generation) throw { error: 'TRAINING_JOB_EXPIRED', detail: '引擎会话已切换，请查询新会话任务' };
        if (receipt) {
          if (receipt.job_id !== job.id) throw new Error('训练任务响应编号不一致');
          accept(receipt);
          if (api.events) {
            try {
              const page = await api.events(job.id, Math.max(view.events.at(-1)?.seq ?? 0, (receipt.event_cursor ?? 0) - 50));
              if (epoch !== generation) throw new Error('引擎会话已切换');
              const rows = new Map(view.events.map(e => [e.seq, e]));
              page.events.forEach(e => rows.set(e.seq, e));
              publish({ events: [...rows.values()].sort((a, b) => a.seq - b.seq).slice(-300) });
            } catch (error) { if (epoch !== generation) throw error; publish({ error }); } // Log transport does not change a training outcome.
          }
          if (receipt.status === 'succeeded') {
            if (!receipt.run_id) throw new Error('训练完成回执缺少运行编号');
            const result = await api.result(receipt.run_id);
            if (result.run_id !== receipt.run_id || result.task !== 'classification' || result.status !== 'succeeded') {
              throw new Error('训练结果与完成回执不一致');
            }
            if (epoch !== generation) throw new Error('引擎会话已切换');
            publish({ result, progress: null, error: null });
            if (current === job) current = null;
            return result;
          }
          if (receipt.status === 'failed' || receipt.status === 'cancelled') throw receipt.error ?? new Error('分类训练未完成');
          if (receipt.status !== 'running' && receipt.status !== 'queued') throw new Error('训练任务状态无效');
          report(job, receipt.status);
          await pause(2000);
        }
        try { receipt = await api.status(job.id); failures = 0; }
        catch (error) {
          if (epoch !== generation) throw error;
          if (error && typeof error === 'object' && 'error' in error && error.error === 'TRAINING_JOB_NOT_FOUND' && job.body) {
            // A request that never reached the worker may be retried only with
            // its retained id, never as a new training operation.
            try { receipt = await api.submit(job.id, job.body); continue; }
            catch (reason) { if (!transport(reason)) throw reason; }
          } else if (!transport(error)) throw error;
          receipt = undefined;
          report(job, 'reconnecting');
          if (++failures >= 5) throw unavailable;
          await pause(2000);
        }
      }
    } catch (error) {
      if (epoch !== generation) throw error;
      publish({ error });
      if (transport(error) || error === unavailable) {
        report(job, 'unavailable');
        throw unavailable;
      }
      publish({ progress: null });
      if (current === job) current = null;
      throw error;
    }
  };
  return {
    subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; },
    snapshot: () => view,
    reset() { generation++; current = null; publish({ job: null, progress: null, events: [], error: null, result: null }); },
    async discover() {
      if (current || !api.list) return;
      discovery ??= (async () => {
        const epoch = generation;
        const rows = await api.list!();
        if (epoch !== generation || current) return;
        const receipt = rows.items.find(j => j.status === 'running' || j.status === 'queued') ?? rows.items[0];
        if (!receipt || receipt.job_id === view.job?.job_id) return;
        publish({ job: receipt, events: [], error: null, result: null });
        const job: JobState = { id: receipt.job_id, body: null, key: '', started: Date.now() - (receipt.elapsed_s ?? 0) * 1000, attempted: true, reporters: new Set() };
        current = job;
        job.promise = execute(job).finally(() => { job.promise = undefined; });
        void job.promise.catch(() => {});
      })().finally(() => { discovery = undefined; });
      return discovery;
    },
    async cancel() {
      if (view.job && api.cancel) {
        const id = view.job.job_id, epoch = generation, receipt = await api.cancel(id);
        if (epoch === generation && view.job?.job_id === id) accept(receipt);
      }
    },
    async resume() {
      if (!view.job || !api.resume || current) throw new Error('请先确认原任务已终止');
      const parent = view.job.job_id;
      const epoch = generation;
      // Retain this id after a lost response; querying or resubmitting this exact id is idempotent.
      const next = continuations.get(parent) ?? crypto.randomUUID(); continuations.set(parent, next);
      const receipt = await api.resume(parent, next);
      if (epoch !== generation) return;
      publish({ job: receipt, events: [], error: null, result: null });
      const job: JobState = { id: next, body: null, key: '', started: Date.now(), attempted: true, reporters: new Set() };
      current = job;
      job.promise = execute(job).finally(() => { job.promise = undefined; });
      void job.promise.catch(() => {});
    },
    async refresh() {
      if (!current && view.job) {
        const id = view.job.job_id;
        const receipt = await api.status(id);
        if (view.job?.job_id === id) accept(receipt);
      } else if (current && !current.promise) {
        const job = current;
        job.promise = execute(job).finally(() => { job.promise = undefined; });
        await job.promise;
      }
    },
    pending: () => current?.body ?? null,
    train(body: ClassificationBody, listener: Reporter): Promise<Result> {
      const key = JSON.stringify(body);
      if (current && current.key !== key) return Promise.reject(new Error('已有训练任务待确认，请先查询原任务状态'));
      const job: JobState = current ?? { id: crypto.randomUUID(), body, key, started: Date.now(), attempted: false, reporters: new Set<Reporter>() };
      current = job;
      if (view.job?.job_id !== job.id) publish({ job: null, events: [], error: null, result: null });
      job.reporters.add(listener);
      job.promise ??= execute(job).finally(() => { job.promise = undefined; });
      return job.promise.finally(() => { job.reporters.delete(listener); });
    },
  };
}
