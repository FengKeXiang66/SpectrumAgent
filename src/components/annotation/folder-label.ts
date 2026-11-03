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
