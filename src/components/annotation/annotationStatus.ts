import type { JsonProjectionStatus } from './types.ts';

// The badge is a pure projection of the backend's disk truth. undefined means
// the versions listing has not been read yet; null means an older engine did
// not return json_projection at all. Neither may be guessed as "未标注".
export type BadgeTone = 'present' | 'absent' | 'pending' | 'unknown';
export type AnnotationBadge = { label: string; tone: BadgeTone; detail: string };

export function annotationBadge(status: JsonProjectionStatus | null | undefined, versionCount: number): AnnotationBadge {
  if (status === undefined) {
    return { label: '读取标注状态…', tone: 'pending', detail: '正在读取当前数据集的 JSON 标注文件状态…' };
  }
  if (status === null) {
    return { label: '标注状态未知', tone: 'unknown', detail: '引擎未返回标注文件状态，请刷新工作态。' };
  }
  if (!status.exists) {
    const versions = versionCount > 0 ? `已有 ${versionCount} 个标注版本，但 JSON 标注文件缺失。` : '';
    return { label: '未标注', tone: 'absent',
      detail: `${versions}尚未生成该图的 JSON 标注文件；保存并聚合后生成。` };
  }
  const parts = [
    status.filename ? `文件名 ${status.filename}` : '',
    typeof status.version_no === 'number' ? `对应 v${status.version_no}` : '',
    status.generated_at ? `生成于 ${status.generated_at}` : '',
  ].filter(Boolean);
  return { label: '已有 JSON 标注文件', tone: 'present',
    detail: parts.length ? parts.join(' · ') : '该图已生成 JSON 标注文件。' };
}
