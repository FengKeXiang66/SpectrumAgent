import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import type { DatasetTransport, ImportResponse, Preview, PreviewOptions } from './types.ts';

// One auditable exit for dataset IPC. No URL, port, method or token is accepted.
export type Request = { op: 'import'; path: string; raw: boolean } | ({ op: 'preview'; id: string } & PreviewOptions);
export function previewRequest(id: string, selection: number | PreviewOptions): Request {
  const options = typeof selection === 'number' ? { band: selection } : selection;
  return { op: 'preview', id,
    ...(options.band !== undefined ? { band: options.band } : {}),
    ...(options.bands !== undefined ? { bands: options.bands } : {}),
    ...(options.stretch !== undefined ? { stretch: options.stretch } : {}),
    ...(options.size !== undefined ? { size: options.size } : {}) };
}
function forward<T>(request: Request): Promise<T> {
  return invoke<T>('datasets_forward', { request });
}

export function datasetClient(chooseDirectories: DatasetTransport['chooseDirectories']): DatasetTransport {
  return {
    chooseDirectories,
    importDirectory: (path, raw) => forward<ImportResponse>({ op: 'import', path, raw }),
    preview: (id, selection) => forward<Preview>(previewRequest(id, selection)),
  };
}

export const datasets = datasetClient(async () => {
  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
  return result === null ? null : Array.isArray(result) ? result : [result];
});
