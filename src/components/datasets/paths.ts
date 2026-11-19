export function normalizePath(value: string): string {
  if (!/^smb:\/\//i.test(value)) return value;
  const match = /^smb:\/\/([^/]+)\/(.+)$/i.exec(value);
  try {
    if (!match || /[@:?#\\]/.test(match[1]) || /[?#]/.test(match[2])) throw new Error();
    const parts = decodeURIComponent(match[2]).replace(/\/+$/, '').split('/');
    if (parts.some(part => !part || part === '.' || part === '..' || part.includes('\\'))) throw new Error();
    return `\\\\${match[1]}\\${parts.join('\\')}`;
  } catch { throw new Error('SMB 路径须包含服务器与共享目录，且不得包含凭据。'); }
}

export function pathPrefill(search: string): { source_path?: string; output_root?: string } {
  const params = new URLSearchParams(search), source = params.get('src'), output = params.get('out');
  return { ...(source === null ? {} : { source_path: normalizePath(source) }),
    ...(output === null ? {} : { output_root: normalizePath(output) }) };
}
