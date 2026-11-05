import { describeError, type CatalogRecord, type DatasetRecord, type DatasetTransport, type DeletePreview } from './types.ts';

export type DatasetDialog = { kind: 'delete'; record: CatalogRecord; preview: DeletePreview };
export type ActionState = { busy: boolean; dialog: DatasetDialog | null; message: string; error: string; done: number; total: number };
export const emptyActions = (): ActionState => ({ busy: false, dialog: null, message: '选择数据目录，登记数据引用；源文件保持只读。', error: '', done: 0, total: 0 });

export function createDatasetActions(api: DatasetTransport, callbacks: {
  imported(batch: DatasetRecord[]): Promise<void>; deleted(id: string): Promise<void>;
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
          // Permanent deletion leaves no recycle-bin key, so an absent active
          // record is always a plain first import with no confirmation dialog.
          const result = await api.importDirectory(paths[i], raw);
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
        const result = await api.delete(record.id, preview.preview_token, true);
        if (!live) return;
        await callbacks.deleted(record.id);
        update({ message: result.pending_directories.length
          ? `记录已永久删除；${result.pending_directories.length} 个产物目录待下次启动清理。`
          : '已永久删除：数据库记录与产物文件已清除，不可恢复；原始 ENVI 源文件未改动。' });
      } catch (failure) { update({ error: describeError(failure) }); }
      finally { finish(); }
    },
    decide(confirmed: boolean) { const resolve = decision; decision = null; resolve?.(confirmed); },
    dispose() { live = false; const resolve = decision; decision = null; resolve?.(false); },
  };
}
