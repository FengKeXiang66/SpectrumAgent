/** Names are explicit user input; preserve case and spaces inside a name. */
export function parseLabelNames(value: string): string[] {
  const names = value.split(/[、,，;；\r\n]+/).map(name => name.trim().replace(/^["“”'‘’]+|["“”'‘’]+$/g, '').trim()).filter(Boolean);
  if (!names.length) throw new Error('请输入至少一个标签名称。');
  if (names.length > 100) throw new Error('每次最多创建 100 个标签。');
  if (names.some(name => name.length > 100 || /[\x00-\x1f\x7f]/.test(name)))
    throw new Error('标签名称最多 100 个字符，不能含控制字符。');
  return [...new Set(names)];
}

export function createLabelsCommand(intakeId: string, value: string): string {
  return `创建导入标签 ${intakeId} ${JSON.stringify(parseLabelNames(value))}`;
}

export function labelCommandText(content: string): string {
  const match = /^创建导入标签\s+[0-9a-f-]{36}\s+([\s\S]+)$/.exec(content);
  if (!match) return content;
  try {
    const names: unknown = JSON.parse(match[1]);
    return Array.isArray(names) && names.every(name => typeof name === 'string') ? `创建标签：${names.join('、')}` : content;
  } catch { return content; }
}
