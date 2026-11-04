import type { ImportResponse } from './types.ts';

export function newDatasetConfirmation(error: unknown): string | null {
  if (typeof error !== 'object' || error === null || !('error' in error)
      || error.error !== 'REIMPORT_CONFIRMATION_REQUIRED') return null;
  return '作为全新数据集导入（新建 id、从头标注）。旧数据仍留回收站 30 天，期内占双份空间。';
}

export function importMessage(result: ImportResponse): string {
  const { total, imported, existing } = result.summary;
  const existingMessage = total > 0 && imported === 0 ? '该路径已有数据集。' : '';
  return `${existingMessage}本次选中 ${total} 个（新增 ${imported} / 已有 ${existing}）`;
}
