import type { ImportResponse } from './types.ts';

// Permanent deletion leaves no recycle-bin key behind. An absent active record
// is always a first import, so there is no new-id confirmation decision here.
export function importMessage(result: ImportResponse): string {
  const { total, imported, existing } = result.summary;
  const existingMessage = total > 0 && imported === 0 ? '该路径已有数据集。' : '';
  return `${existingMessage}本次选中 ${total} 个（新增 ${imported} / 已有 ${existing}）`;
}
