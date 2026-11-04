import { createElement as h } from 'react';
import type { DatasetDialog as Dialog } from './actions.ts';
import type { RecycleList } from './types.ts';

export function byteSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${bytes.toLocaleString()} B` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB（${bytes.toLocaleString()} B）`;
}
export function releaseDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}

export function RecycleSummary({ value }: { value: RecycleList }) {
  return h('section', { 'aria-label': '回收站占用' }, h('h3', null, '回收站占用'),
    h('p', null, `${value.count} 个条目 · ${byteSize(value.total_bytes)}。回收站内仍占本机磁盘空间。`),
    value.items.length ? h('ul', null, ...value.items.map(row => h('li', { key: row.deletion_id },
      `${row.display_name}：${byteSize(row.total_bytes)}；预计释放日期 ${releaseDate(row.expires_at)}`,
      row.status !== 'READY' && '（不完整，已禁止恢复与自动清理，等待人工处理）')))
      : h('p', null, value.count ? '另有隔离条目，需人工处理；不会自动释放。' : '回收站为空。'),
    h('p', null, '到期后在引擎启动清理时释放；运行中的长任务会推迟清理。'));
}

export function DatasetDialog({ dialog, onDecision }: { dialog: Dialog; onDecision(confirmed: boolean): void }) {
  const title = dialog.kind === 'delete' ? '确认移入回收站' : dialog.kind === 'restore' ? '确认恢复数据集' : '确认重新导入';
  return h('div', { className: 'dataset-modal-shade' },
    h('section', { role: 'dialog', 'aria-modal': true, 'aria-label': title, tabIndex: -1, className: 'dataset-dialog',
      ref: (node: HTMLElement | null) => { node?.focus(); },
      onKeyDown: (event: { key: string; shiftKey: boolean; preventDefault(): void; currentTarget: HTMLElement }) => {
        if (event.key === 'Escape') { event.preventDefault(); onDecision(false); }
        if (event.key === 'Tab') {
          const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button,input')];
          const index = controls.indexOf(document.activeElement as HTMLElement);
          const next = event.shiftKey ? index - 1 : index + 1;
          if (index < 0 || next < 0 || next >= controls.length) {
            event.preventDefault(); controls[event.shiftKey ? controls.length - 1 : 0]?.focus();
          }
        }
      } }, h('h2', null, title),
      dialog.kind === 'delete' && h('div', null,
        h('p', null, dialog.record.display_name),
        h('p', null, '原始 ENVI 源文件保持不变。程序产物与关联记录将移入回收站，30 天内可恢复，占用空间不会立即释放。'),
        h('dl', { className: 'dataset-impact' },
          ...([['标注版本', dialog.preview.annotation_versions], ['预处理运行', dialog.preview.preprocess_runs],
            ['训练运行', dialog.preview.training_runs], ['推理运行', dialog.preview.inference_runs]] as const)
            .map(([name, count]) => h('div', { key: name }, h('dt', null, name), h('dd', null, count)))),
        h('p', null, `产物合计 ${byteSize(dialog.preview.total_bytes)}`),
        h('h3', null, '将移走的目录'),
        dialog.preview.directories.length ? h('ul', null, ...dialog.preview.directories.map(row =>
          h('li', { key: row.path }, h('code', null, row.path), ' · ', byteSize(row.bytes)))) : h('p', null, '无产物目录，仅回收关联记录。')),
      dialog.kind === 'restore' && h('div', null, h('p', null, dialog.record.display_name),
        h('p', null, '文件移回工作区，恢复原 id 及历史标注、版本和台账。'),
        h('p', null, '若同路径已有活跃数据集，须先把新的也删进回收站，或等 30 天到期。')),
      dialog.kind === 'reimport' && h('div', null,
        h('label', null, h('input', { type: 'radio', name: 'reimport_mode', value: 'new', checked: true, readOnly: true }), '作为全新数据集导入'),
        h('p', null, dialog.detail)),
      h('div', { className: 'dataset-dialog-actions' }, h('button', { onClick: () => onDecision(false) }, '取消'),
        h('button', { className: dialog.kind === 'delete' ? 'dataset-danger' : '', onClick: () => onDecision(true) },
          dialog.kind === 'delete' ? '确认移入回收站' : dialog.kind === 'restore' ? '确认恢复' : '确认新建数据集'))));
}
