import { createElement as h } from 'react';
import type { DatasetDialog as Dialog } from './actions.ts';
import type { BatchDatasetDialog as BatchDialog } from './actions.ts';

export function byteSize(bytes: number): string {
  return bytes < 1024 * 1024 ? `${bytes.toLocaleString()} B` : `${(bytes / (1024 * 1024)).toFixed(2)} MiB（${bytes.toLocaleString()} B）`;
}

export function BatchDatasetDialog({ dialog, onDecision }: { dialog: BatchDialog; onDecision(confirmed: boolean): void }) {
  const { preview } = dialog, title = '确认批量永久删除';
  return h('div', { className: 'dataset-modal-shade' },
    h('section', { role: 'dialog', 'aria-modal': true, 'aria-label': title, tabIndex: -1, className: 'dataset-dialog',
      ref: (node: HTMLElement | null) => { node?.focus(); },
      onKeyDown: (event: { key: string; shiftKey: boolean; preventDefault(): void; currentTarget: HTMLElement }) => {
        if (event.key === 'Escape') { event.preventDefault(); onDecision(false); }
        if (event.key === 'Tab') {
          const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button')];
          const index = controls.indexOf(document.activeElement as HTMLElement);
          const next = event.shiftKey ? index - 1 : index + 1;
          if (index < 0 || next < 0 || next >= controls.length) {
            event.preventDefault(); controls[event.shiftKey ? controls.length - 1 : 0]?.focus();
          }
        }
      } },
      h('h2', null, title),
      h('p', null, `本次将删除 ${preview.cube_ids.length} 个数据集及 ${preview.training_runs} 条关联实验，永久不可恢复。`),
      h('p', null, '原始 ENVI 源文件不删除。数据库记录与程序产物将被永久删除，不可恢复；删除事件写入只增不改的审计表。'),
      h('h3', null, '闭包内全部数据集（包含自动关联项）'),
      h('ul', null, ...preview.cube_ids.map(id => h('li', { key: id }, h('code', null, id)))),
      h('h3', null, '关联实验清单'),
      preview.linked_runs.length ? h('ul', null, ...preview.linked_runs.map(run => h('li', { key: run.id },
        h('code', null, run.id), `关联 ${run.cube_ids.length} 个数据集 · ${run.status}`,
        h('ul', null, ...run.cube_ids.map(id => h('li', { key: id }, h('code', null, id))))))) : h('p', null, '无跨数据集关联实验。'),
      h('h3', null, '按数据集分组的独占产物'),
      ...preview.per_cube.map(row => h('section', { key: row.cube_id, 'aria-label': `数据集 ${row.cube_id} 的独占产物` },
        h('code', null, row.cube_id),
        h('p', null, `标注记录 ${row.annotation_versions} · 预处理运行 ${row.preprocess_runs} · 推理运行 ${row.inference_runs}`),
        h('p', null, `独占产物 ${byteSize(row.total_bytes)}`),
        row.directories.length ? h('ul', null, ...row.directories.map(directory => h('li', { key: directory.path },
          h('code', null, directory.path), ' · ', byteSize(directory.bytes)))) : h('p', null, '无独占产物目录。'))),
      h('h3', null, '共享目录（单列，不分摊）'),
      preview.shared_directories.length ? h('ul', null, ...preview.shared_directories.map(directory => {
        const count = preview.linked_runs.find(run => run.id === directory.run_id)?.cube_ids.length ?? 1;
        return h('li', { key: directory.path }, h('code', null, directory.path), ' · ', byteSize(directory.bytes),
          h('p', null, `由 ${count} 个数据集共享，只删一次`),
          h('p', null, '审计归属：', h('code', null, directory.representative_cube_id)));
      })) : h('p', null, '无共享产物目录。'),
      h('p', null, `产物总计 ${byteSize(preview.total_bytes)}（共享目录只计一次）`),
      h('div', { className: 'dataset-dialog-actions' }, h('button', { onClick: () => onDecision(false) }, '取消'),
        h('button', { className: 'dataset-danger', onClick: () => onDecision(true) }, '确认批量永久删除'))));
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
          ...([['标注记录', dialog.preview.annotation_versions], ['预处理运行', dialog.preview.preprocess_runs],
            ['训练运行', dialog.preview.training_runs], ['推理运行', dialog.preview.inference_runs]] as const)
            .map(([name, count]) => h('div', { key: name }, h('dt', null, name), h('dd', null, count)))),
        h('p', null, `产物合计 ${byteSize(dialog.preview.total_bytes)}`),
        h('h3', null, '将永久删除的目录'),
        dialog.preview.directories.length ? h('ul', null, ...dialog.preview.directories.map(row =>
          h('li', { key: row.path }, h('code', null, row.path), ' · ', byteSize(row.bytes)))) : h('p', null, '无产物目录，仅删除关联数据库记录。')),
      h('div', { className: 'dataset-dialog-actions' }, h('button', { onClick: () => onDecision(false) }, '取消'),
        h('button', { className: 'dataset-danger', onClick: () => onDecision(true) }, '确认永久删除'))));
}
