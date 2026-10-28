import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';
import type { DatasetRecord, DatasetTransport, ImportResponse, MeanSpectrum, Preview, PreviewOptions, SpectrumRegion } from './types.ts';

// One auditable exit for dataset IPC. No URL, port, method or token is accepted.
export type Request = { op: 'import'; path: string; raw: boolean } | ({ op: 'preview'; id: string } & PreviewOptions)
  | { op: 'spectra_mean'; id: string; region: SpectrumRegion } | { op: 'get'; id: string };
export function spectraMeanRequest(id: string, region: SpectrumRegion): Request {
  return { op: 'spectra_mean', id, region: { l0: region.l0, l1: region.l1, s0: region.s0, s1: region.s1,
    ...(region.raw === undefined ? {} : { raw: region.raw }) } };
}
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

export function datasetClient(chooseDirectories: DatasetTransport['chooseDirectories'], send: typeof forward = forward): DatasetTransport {
  return {
    chooseDirectories,
    get: id => send<DatasetRecord>({ op: 'get', id }),
    importDirectory: (path, raw) => send<ImportResponse>({ op: 'import', path, raw }),
    preview: (id, selection) => send<Preview>(previewRequest(id, selection)),
    spectraMean: (id, region) => send<MeanSpectrum>(spectraMeanRequest(id, region)),
  };
}

export const datasets = datasetClient(async () => {
  const result = await open({ directory: true, multiple: true, filters: [{ name: 'Hyperspectral', extensions: ['hdr', 'img', 'raw', 'bin', 'json', 'txt'] }] });
  return result === null ? null : Array.isArray(result) ? result : [result];
});
