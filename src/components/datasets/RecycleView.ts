import { createElement as h } from 'react';
import type { DatasetDialog as Dialog } from './actions.ts';

export function byteSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${bytes.toLocaleString()} B` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB（${bytes.toLocaleString()} B）`;
}

export function DatasetDialog({ dialog, onDecision }: { dialog: Dialog; onDecision(confirmed: boolean): void }) {
  const title = '确认永久删除';
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
      h('div', null,
        h('p', null, dialog.record.display_name),
        h('p', null, '原始 ENVI 源文件保持不变、不删除。以下数据库记录与程序产物将被永久删除，不可恢复；删除事件写入只增不改的审计表。'),
        h('dl', { className: 'dataset-impact' },
          ...([['标注版本', dialog.preview.annotation_versions], ['预处理运行', dialog.preview.preprocess_runs],
            ['训练运行', dialog.preview.training_runs], ['推理运行', dialog.preview.inference_runs]] as const)
            .map(([name, count]) => h('div', { key: name }, h('dt', null, name), h('dd', null, count)))),
        h('p', null, `产物合计 ${byteSize(dialog.preview.total_bytes)}`),
        h('h3', null, '将永久删除的目录'),
        dialog.preview.directories.length ? h('ul', null, ...dialog.preview.directories.map(row =>
          h('li', { key: row.path }, h('code', null, row.path), ' · ', byteSize(row.bytes)))) : h('p', null, '无产物目录，仅删除关联数据库记录。')),
      h('div', { className: 'dataset-dialog-actions' }, h('button', { onClick: () => onDecision(false) }, '取消'),
        h('button', { className: 'dataset-danger', onClick: () => onDecision(true) }, '确认永久删除'))));
}
