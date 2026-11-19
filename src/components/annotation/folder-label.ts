import type { CatalogItem, Label } from './types.ts';

export function folderName(headerPath: string): string | null {
  const folder = headerPath.trim().split(/[\\/]/).at(-2)?.trim();
  return folder && !/^[a-z]:$/i.test(folder) ? folder : null;
}

export function matchLabel(labels: readonly Label[], folder: string): Label | null {
  const code = folder.trim().toLowerCase();
  return labels.find(label => !label.is_background && label.code.trim().toLowerCase() === code) ?? null;
}

export function catalogCode(catalog: readonly CatalogItem[], folder: string): string | null {
  const code = folder.trim().toLowerCase();
  return catalog.find(item => item.code.trim().toLowerCase() === code)?.code ?? null;
}

export function validateTreeCandidates(candidates: readonly import('./types.ts').ImportTreeCandidate[]): string | null {
  if (!candidates.length) return '没有候选目录。';
  for (const item of candidates) {
    if (!/^[A-Z0-9_]{1,16}$/.test(item.code)) return `${item.directory}：code 须为 1–16 位大写 ASCII 字母、数字或下划线。`;
    if (!item.name.trim() || !/^#[0-9a-fA-F]{6}$/.test(item.color_hex)) return `${item.directory}：名称或颜色不合法。`;
    if (item.needs_naming && !item.confirmed) return `${item.directory}：请确认占位 code 和名称。`;
  }
  return null;
}

export function labelFailure(error: unknown): string {
  return error instanceof Error ? error.message : typeof error === 'string' ? error : JSON.stringify(error, null, 2);
}
