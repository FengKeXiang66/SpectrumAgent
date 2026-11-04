import { createElement as h } from 'react';
import type { PathValues } from './settings-forward.ts';
import type { PathFormState } from './project-path-form.ts';

export type ProjectPathsProps = { state: PathFormState; summary?: boolean;
  onEdit(field: keyof PathValues, value: string): void; onBrowse(field: keyof PathValues): void;
  onSave(): void; onRetry(): void };

export function ProjectPathsView(p: ProjectPathsProps) {
  const disabled = p.state.phase !== 'ready';
  return h('section', { className: 'project-paths', 'aria-label': p.summary ? '当前项目路径' : '项目路径设置' },
    h('h2', null, p.summary ? '当前项目路径' : '数据源与产物输出根'),
    p.state.projectName && h('p', null, `项目：${p.state.projectName}`),
    h('p', null, '输出根当前仅保存、不生效。产物仍写入本机数据根；未检查 NAS 连通性或挂载状态。'),
    p.state.phase === 'loading' && h('p', { role: 'status' }, '正在读取项目路径…'),
    p.state.error && h('p', { role: 'alert' }, p.state.error),
    p.state.phase === 'error' && h('button', { onClick: p.onRetry }, '重新读取项目路径'),
    p.state.projectId && (p.summary
      ? h('dl', null, ...(['source_path', 'output_root'] as const).map(field => h('div', { key: field },
        h('dt', null, field === 'source_path' ? '数据源（程序只读）' : '产物输出根（未启用）'),
        h('dd', null, p.state.values[field] || '未配置'))))
      : h('form', { onSubmit: event => { event.preventDefault(); p.onSave(); } },
        ...(['source_path', 'output_root'] as const).map(field => h('div', { className: 'project-path-row', key: field },
          h('label', null, field === 'source_path' ? '数据源（本机 / UNC）' : '产物输出根',
            h('input', { name: field, value: p.state.values[field], disabled, autoComplete: 'off', spellCheck: false,
              onChange: (event: { target: { value: string } }) => p.onEdit(field, event.target.value) })),
          h('button', { type: 'button', disabled, onClick: () => p.onBrowse(field) }, '浏览…'),
          field === 'source_path' && h('span', { className: 'readonly-badge' }, '源目录只读（程序不写）'))),
        h('button', { type: 'submit', disabled }, p.state.phase === 'saving' ? '保存中…' : '保存为该项目默认'))),
    p.state.values.data_root && h('p', null, '实际产物数据根：', h('code', null, p.state.values.data_root)),
    p.state.message && h('p', { role: 'status' }, p.state.message),
    !p.summary && h('p', { className: 'dataset-format-note' },
      '当前：ENVI（.hdr + .dat/.img）、纯二进制 + 头文件。多波段 GeoTIFF / COG：第二批验证；HDF5 / NetCDF、Specim：阶段二支持。'));
}
