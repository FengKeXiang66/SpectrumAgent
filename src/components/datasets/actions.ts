import { describeError, type CatalogRecord, type DatasetRecord, type DatasetTransport, type DeletePreview, type RecycleRecord } from './types.ts';
import { newDatasetConfirmation } from './importDecision.ts';

export type DatasetDialog = { kind: 'delete'; record: CatalogRecord; preview: DeletePreview }
  | { kind: 'restore'; record: RecycleRecord } | { kind: 'reimport'; detail: string };
export type ActionState = { busy: boolean; dialog: DatasetDialog | null; message: string; error: string; done: number; total: number };
export const emptyActions = (): ActionState => ({ busy: false, dialog: null, message: '选择数据目录，登记数据引用；源文件保持只读。', error: '', done: 0, total: 0 });

export function createDatasetActions(api: DatasetTransport, callbacks: {
  imported(batch: DatasetRecord[]): Promise<void>; deleted(id: string): Promise<void>; restored(id: string): Promise<void>;
}, changed: (state: ActionState) => void) {
  let state = emptyActions(), live = true, decision: ((confirmed: boolean) => void) | null = null;
  const update = (patch: Partial<ActionState>) => { if (live) { state = { ...state, ...patch }; changed(state); } };
  const ask = (dialog: DatasetDialog) => new Promise<boolean>(resolve => { decision = resolve; update({ dialog }); });
  const start = () => {
    if (!live || state.busy) return false;
    update({ busy: true, error: '', dialog: null, done: 0, total: 0 }); return true;
  };
  const finish = () => update({ busy: false, dialog: null });
  return {
    async choose(raw: boolean) {
      if (!start()) return;
      let imported = 0, existing = 0, total = 0;
      try {
        const paths = await api.chooseDirectories();
        if (!live) return;
        if (!paths?.length) { update({ message: '已取消选择。' }); return; }
        update({ total: paths.length });
        for (let i = 0; i < paths.length; i++) {
          update({ message: `正在登记目录 ${i + 1}/${paths.length}…` });
          let result;
          try { result = await api.importDirectory(paths[i], raw); }
          catch (failure) {
            if (!live) return;
            const detail = newDatasetConfirmation(failure);
            if (!detail) throw failure;
            if (!await ask({ kind: 'reimport', detail }) || !live) {
              update({ message: `已取消当前目录。本次已完成 ${total} 个（新增 ${imported} / 已有 ${existing}）。` }); return;
            }
            update({ dialog: null });
            result = await api.importDirectory(paths[i], raw, true);
          }
          if (!live) return;
          imported += result.summary.imported; existing += result.summary.existing; total += result.summary.total;
          // Only the selected batch enters the view. all_datasets remains a wire
          // compatibility field; catalog refreshes names without widening scope.
          await callbacks.imported(result.datasets);
          if (!live) return;
          update({ done: i + 1 });
        }
        update({ message: `${total > 0 && imported === 0 ? '该路径已有数据集。' : ''}本次选中 ${total} 个（新增 ${imported} / 已有 ${existing}）` });
      } catch (failure) {
        update({ error: describeError(failure), message: `当前目录未登记；先前已完成 ${total} 个（新增 ${imported} / 已有 ${existing}）保持已登记。` });
      } finally { finish(); }
    },
    async requestDelete(record: CatalogRecord) {
      if (!start()) return;
      try {
        const preview = await api.deletePreview(record.id);
        if (!live) return;
        if (!await ask({ kind: 'delete', record, preview }) || !live) return;
        update({ dialog: null });
        await api.delete(record.id, preview.preview_token, true);
        if (!live) return;
        await callbacks.deleted(record.id);
        update({ message: '已移入回收站，30 天内可恢复；本机空间尚未释放。' });
      } catch (failure) { update({ error: describeError(failure) }); }
      finally { finish(); }
    },
    async requestRestore(record: RecycleRecord) {
      if (Date.parse(record.expires_at) <= Date.now()) { update({ error: '该条目已超过 30 天恢复期，等待到期清理。' }); return; }
      if (record.status !== 'READY' || !start()) return;
      try {
        if (!await ask({ kind: 'restore', record }) || !live) return;
        update({ dialog: null });
        const result = await api.restore(record.deletion_id, true);
        if (!live) return;
        await callbacks.restored(result.cube_id);
        update({ message: '已恢复，数据集 id 与历史标注、版本、台账保持原值。' });
      } catch (failure) {
        update({ error: describeError(failure) + '\n若同路径已有活跃数据集，须先把新的也删进回收站，或等 30 天到期。' });
      } finally { finish(); }
    },
    decide(confirmed: boolean) { const resolve = decision; decision = null; resolve?.(confirmed); },
    dispose() { live = false; const resolve = decision; decision = null; resolve?.(false); },
  };
}
