import { useState } from 'react';
import type { CatalogItem, FieldType, Json, Label, LabelBody, LabelSchema } from './types.ts';
import { labelKey, type Preferences } from './shortcuts.ts';
import { similarColors } from './working.ts';

type Props = {
  projectId: string; schemas: LabelSchema[]; labels: Label[]; catalog: CatalogItem[];
  selectedId: string | null; preferences: Preferences; disabled: boolean;
  onSelect(id: string): void; onAdd(body: LabelBody): Promise<void>;
};
export default function LabelPanel({ projectId, schemas, labels, catalog, selectedId, preferences, disabled, onSelect, onAdd }: Props) {
  const [adding, setAdding] = useState(false), [mode, setMode] = useState<'catalog' | 'custom' | 'schema'>('catalog');
  const [codes, setCodes] = useState<string[]>([]);
  const [custom, setCustom] = useState({ code: '', name: '', tree_path: '', color_hex: '' });
  const [field, setField] = useState({ name: '', tree_path: '', field_type: 'enum' as FieldType, unit: '', config: '' });
  const [error, setError] = useState('');
  const existing = new Set(labels.map(label => label.code));
  const add = async () => {
    setError('');
    try {
      if (mode === 'catalog') await onAdd({ project_id: projectId, from_catalog: 'plastic', codes });
      else if (mode === 'custom') await onAdd({ project_id: projectId, ...custom });
      else {
        const config: Json | undefined = field.config.trim() ? JSON.parse(field.config) as Json : undefined;
        await onAdd({ project_id: projectId, schema: { name: field.name, tree_path: field.tree_path, field_type: field.field_type,
          ...(field.unit ? { unit: field.unit } : {}), ...(config !== undefined ? { config } : {}) } });
      }
      setAdding(false); setCodes([]); setCustom({ code: '', name: '', tree_path: '', color_hex: '' });
    } catch (failure) { setError(failure instanceof Error ? failure.message : '登记失败，请查看工作台错误详情。'); }
  };
  return <section className="annotation-card" aria-label="项目标签">
    <h3>标签 <small>结构化登记</small></h3>
    <div className="annotation-labels">
      {labels.map(label => <button type="button" key={label.id} className={selectedId === label.id ? 'annotation-label selected' : 'annotation-label'}
        disabled={disabled} aria-pressed={selectedId === label.id} onClick={() => onSelect(label.id)} title={`${label.name} · ${label.tree_path}`}>
        <i className="annotation-swatch" style={{ backgroundColor: label.color_hex }} /><b>{label.code}</b>
        <span className="annotation-label-name">{label.name}</span>
        <kbd>{labelKey(label, preferences) ?? '鼠标'}</kbd>
      </button>)}
    </div>
    {!selectedId && <p className="annotation-hint">先选择标签，再确认区域；留白不等于背景。</p>}
    <button type="button" disabled={disabled} onClick={() => { setAdding(!adding); setError(''); }}>添加标签 / schema</button>
    {adding && <div className="annotation-add-label">
      <label>登记方式<select value={mode} onChange={event => { setMode(event.target.value as typeof mode); setError(''); }}>
        <option value="catalog">从塑料目录选用</option><option value="custom">自定义 enum 标签</option><option value="schema">schema 字段</option>
      </select></label>
      <form onSubmit={event => { event.preventDefault(); void add(); }}>
        {mode === 'catalog' && <div className="annotation-catalog">
          {catalog.filter(item => !existing.has(item.code)).map(item => {
            const near = similarColors(item.color_hex, labels);
            return <div key={item.code}>
              <label><input type="checkbox" checked={codes.includes(item.code)} onChange={event => setCodes(previous => event.target.checked ? [...previous, item.code] : previous.filter(code => code !== item.code))} />
                <i className="annotation-swatch" style={{ backgroundColor: item.color_hex }} />{item.code} · {item.name}</label>
              {!!near.length && <p className="annotation-color-warning">初始色与 {near.map(label => label.code).join(' / ')} 接近（RGB 色距 &lt;30）。
                <button type="button" onClick={() => {
                  const material = schemas.find(schema => schema.field_type === 'enum' && schema.tree_path === '材料');
                  setCustom({ ...item, tree_path: material ? `${material.tree_path}/塑料/${item.code}` : '' }); setMode('custom');
                }}>改用自定义颜色登记</button></p>}
            </div>;
          })}
          {catalog.every(item => existing.has(item.code)) && <p>目录标签均已登记。</p>}
        </div>}
        {mode === 'custom' && <>
          <label>code<input required value={custom.code} onChange={event => setCustom({ ...custom, code: event.target.value })} /></label>
          <label>中文名<input required value={custom.name} onChange={event => setCustom({ ...custom, name: event.target.value })} /></label>
          <label>标签路径<input required value={custom.tree_path} placeholder="材料/塑料/自定义code" onChange={event => setCustom({ ...custom, tree_path: event.target.value })} /></label>
          <p className="annotation-hint">第一段须为项目 enum 字段：{schemas.filter(schema => schema.field_type === 'enum').map(schema => schema.tree_path).join('、') || '请先添加 enum schema'}。</p>
          <label>颜色 hex<input required pattern="#[0-9a-fA-F]{6}" value={custom.color_hex} placeholder="#RRGGBB" onChange={event => setCustom({ ...custom, color_hex: event.target.value })} /></label>
          {/^#[0-9a-fA-F]{6}$/.test(custom.color_hex) && <i className="annotation-swatch" style={{ backgroundColor: custom.color_hex }} />}
          <p className="annotation-hint">新标签不自动分配数字键，可用鼠标选取。</p>
        </>}
        {mode === 'schema' && <>
          <label>字段名<input required value={field.name} onChange={event => setField({ ...field, name: event.target.value })} /></label>
          <label>单段路径<input required pattern="[^/]+" value={field.tree_path} onChange={event => setField({ ...field, tree_path: event.target.value })} /></label>
          <label>类型<select value={field.field_type} onChange={event => setField({ ...field, field_type: event.target.value as FieldType })}>
            {(['enum', 'bool', 'continuous', 'ordinal'] as const).map(type => <option key={type}>{type}</option>)}
          </select></label>
          <label>单位（可选）<input value={field.unit} onChange={event => setField({ ...field, unit: event.target.value })} /></label>
          <label>结构化配置 JSON（可选）<textarea value={field.config} onChange={event => setField({ ...field, config: event.target.value })} /></label>
        </>}
        <button type="submit" disabled={disabled || (mode === 'catalog' && !codes.length)}>登记</button>
        <button type="button" onClick={() => setAdding(false)}>取消</button>
      </form>
      {error && <p role="alert">{error}</p>}
    </div>}
    <details><summary>项目 schema</summary><ul>{schemas.map(schema => <li key={schema.id}>{schema.name} · {schema.tree_path} · {schema.field_type}{schema.unit ? ` · ${schema.unit}` : ''}</li>)}</ul></details>
  </section>;
}
