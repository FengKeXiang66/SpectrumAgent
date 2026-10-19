import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import type { DatasetTransport, ImportResponse, Preview } from './types';

// One auditable exit for dataset IPC. No URL, port, method or token is accepted.
type Request = { op: 'import'; path: string; raw: boolean } | { op: 'preview'; id: string; band: number };
function forward<T>(request: Request): Promise<T> {
  return invoke<T>('datasets_forward', { request });
}

export function datasetClient(chooseDirectories: DatasetTransport['chooseDirectories']): DatasetTransport {
  return {
    chooseDirectories,
    importDirectory: (path, raw) => forward<ImportResponse>({ op: 'import', path, raw }),
    preview: (id, band) => forward<Preview>({ op: 'preview', id, band }),
  };
}

export const datasets = datasetClient(async () => {
  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
  return result === null ? null : Array.isArray(result) ? result : [result];
});
