export type Dataset = {
  name: string;
  shape: [number, number, number];
  dtype: string;
  interleave: 'bsq' | 'bil' | 'bip';
  wavelengths: number[];
  fwhm: number[] | null;
  data_path: string;
  header_path: string;
  metadata: Record<string, unknown>;
};
export type DatasetRecord = { id: string; dataset: Dataset; existing: boolean };
export type ImportResponse = {
  datasets: DatasetRecord[];
  summary: { total: number; imported: number; existing: number };
};
export type Preview = { id: string; band: number; width: number; height: number; mime: 'image/png'; png_base64: string;
  bands?: [number, number, number]; wavelengths?: number[]; fallback?: boolean };
export type PreviewOptions = { band?: number; bands?: string; stretch?: 'auto' | 'none'; size?: 'preview' | 'full' };
export type DatasetTransport = {
  chooseDirectories: () => Promise<string[] | null>;
  importDirectory: (path: string, raw: boolean) => Promise<ImportResponse>;
  preview: (id: string, selection: number | PreviewOptions) => Promise<Preview>;
};

export function mergeRecords(previous: DatasetRecord[], incoming: DatasetRecord[]): DatasetRecord[] {
  const merged = new Map(previous.map(record => [record.id, record]));
  for (const record of incoming) merged.set(record.id, record);
  return [...merged.values()];
}

export function describeError(error: unknown): string {
  if (typeof error === 'object' && error !== null && 'detail' in error) {
    const detail = typeof error.detail === 'string' ? error.detail : '数据请求失败';
    const context = 'context' in error ? `\n${JSON.stringify(error.context, null, 2)}` : '';
    return detail + context;
  }
  return error instanceof Error ? error.message : typeof error === 'string' ? error : '数据请求失败，请查看引擎状态。';
}
