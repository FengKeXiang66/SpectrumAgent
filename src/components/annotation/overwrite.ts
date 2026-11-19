import type { Label, Statistics, Version } from './types.ts';

export function overwriteSummary(version: Pick<Version, 'version_no' | 'created_at' | 'labeled_pixels'>,
  current: Statistics, labels: Pick<Label, 'name'>[]): [string, string] {
  const counts = labels.flatMap((label, index) => {
    const count = current.label_counts[String(index)] ?? 0;
    return count > 0 ? [`${label.name} ${count.toLocaleString()} px`] : [];
  });
  counts.push(`留白 ${current.blank_pixels.toLocaleString()} px`);
  if (current.uncertain_pixels > 0) counts.push(`不确定 ${current.uncertain_pixels.toLocaleString()} px`);
  return [
    `将覆写 v${version.version_no}（${version.created_at} 创建，${version.labeled_pixels.toLocaleString()} px 已标注）`,
    `本次保存将写入：${counts.join(' · ')}`,
  ];
}
