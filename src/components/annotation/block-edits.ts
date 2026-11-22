import type { EditAction } from './types.ts';

export type BlockEdit = { blockId: number; action: EditAction; labelId?: string };
export type PendingBlockEdit = Readonly<BlockEdit & { sequence: number }>;
type Options<T> = {
  submit(edit: PendingBlockEdit): Promise<unknown>;
  read(): Promise<T>;
  onRead(value: T): void;
  onPending(edits: readonly PendingBlockEdit[]): void;
  onActive(active: boolean): void;
  onError(error: unknown, interrupted: number): Promise<void>;
};

// Queue intentions, never pixels or locally inferred labels/statistics. Every
// click remains its own durable edit/undo step; only redundant GETs are grouped.
export function createBlockEditQueue<T>(options: Options<T>) {
  let pending: PendingBlockEdit[] = [], sequence = 0;
  let active = false, disposed = false, recovering = false;
  let completion: Promise<void> = Promise.resolve();
  const notify = () => options.onPending([...pending]);
  const drain = async () => {
    try {
      while (!disposed && pending.length) {
        let submitted = 0;
        // Bound the delay before refreshing the authoritative overlay, even
        // when clicks keep arriving. Do not merge edits or change undo depth.
        while (!disposed && submitted < pending.length && submitted < 4) {
          await options.submit(pending[submitted]);
          submitted++;
        }
        if (disposed) return;
        const value = await options.read();
        if (disposed) return;
        pending.splice(0, submitted);
        options.onRead(value);
        notify();
      }
    } catch (error) {
      if (disposed) return;
      // A failed transport can conceal a committed write. Never replay it or
      // send later clicks until the authoritative state has been reconciled.
      recovering = true;
      const interrupted = pending.length;
      pending = [];
      notify();
      await options.onError(error, interrupted);
    } finally {
      active = false;
      recovering = false;
      if (!disposed) options.onActive(false);
    }
  };
  return {
    enqueue(edit: BlockEdit): boolean {
      if (disposed || recovering) return false;
      pending.push(Object.freeze({ blockId: edit.blockId, action: edit.action,
        ...(edit.labelId !== undefined ? { labelId: edit.labelId } : {}), sequence: ++sequence }));
      notify();
      if (!active) {
        active = true;
        options.onActive(true);
        completion = drain();
      }
      return true;
    },
    idle: () => completion,
    dispose() { disposed = true; pending = []; },
  };
}

export type BlockEditQueue = ReturnType<typeof createBlockEditQueue>;
