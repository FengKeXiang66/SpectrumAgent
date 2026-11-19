export type ModelingScalarSummary = Record<string, string | number | boolean | null>;

const forbidden = /(?:path|filename|confusion|predictions|probabilities|coefficients|wavelengths|geometry|spectra|coordinates)/i;
const unsafeText = /(?:[a-z]:[\\/]|[\\/]|[\[\]{}]|\b(?:NaN|Infinity)\b)/i;

/** Validate tool summaries without accepting serialized arrays or local paths. */
export function validateModelingSummary(value: unknown): ModelingScalarSummary {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('建模摘要不是对象');
  const entries = Object.entries(value);
  for (const [key, item] of entries) {
    if (forbidden.test(key.replace(/n_wavelengths$/, 'dimension')) || unsafeText.test(key) ||
        item !== null && !['string', 'number', 'boolean'].includes(typeof item) ||
        typeof item === 'number' && !Number.isFinite(item) ||
        typeof item === 'string' && unsafeText.test(item)) throw new Error('建模摘要含不安全数据');
  }
  if (new TextEncoder().encode(JSON.stringify(value)).length > 128 * 1024) throw new Error('建模摘要过大');
  return Object.fromEntries(entries) as ModelingScalarSummary;
}
