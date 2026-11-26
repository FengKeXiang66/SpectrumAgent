import { useEffect, useRef, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { createLabelsCommand } from './label-names.ts';

export type DataIntake = {
  id: string; stage: 'choose_mode' | 'need_images' | 'need_annotations' | 'review' | 'imported' | 'cancelled' | 'labels';
  mode: 'unlabeled' | 'labeled' | null;
  image_names: string[]; annotation_names: string[]; classes: string[];
  image_count: number; paired_count: number; missing_count: number; issue_count: number;
  imported_count: number; ready_count: number;
  labels?: { id: string; code: string; name: string; color_hex: string; existing: boolean }[];
  label_form_open?: boolean;
  label_draft?: string[];
  pairs?: { image_name: string; annotation_name: string; region_count: number; labels: string[] }[];
};

export default function DataIntakeCard({ card, active, enabled, send, edit }: {
  card: DataIntake; active: boolean; enabled: boolean;
  send(text: string): void; edit(text: string): void;
}) {
  const [error, setError] = useState('');
  const [picking, setPicking] = useState(false);
  const [labelNames, setLabelNames] = useState((card.label_draft ?? []).join('\n'));
  const [labelForm, setLabelForm] = useState(card.label_form_open ?? false);
  const live = useRef(true);
  const current = useRef({ active, enabled });
  current.current = { active, enabled };
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  const canAct = active && enabled && !picking;
  const remaining = Math.max(0, card.imported_count - card.ready_count);
  const command = (action: string) => `${action} ${card.id}`;
  const choose = async (directory: boolean) => {
    setError(''); setPicking(true);
    try {
      const images = card.stage === 'need_images';
      const path = await open({ title: images ? '选择原图位置' : '选择标注位置', directory, multiple: false,
        ...(!directory ? { filters: [{ name: images ? 'ENVI 原图' : 'ROI 标注', extensions: images ? ['hdr'] : ['json'] }] } : {}) });
      // A picker is local and reversible. The eventual submission still checks
      // the session/epoch in useSession, and the backend owns the intake ID.
      if (typeof path === 'string' && live.current && current.current.active && current.current.enabled)
        edit(`${images ? '原图' : '标注'}位置为 "${path}"`);
    } catch { setError('无法打开文件选择器，请输入本地路径。'); }
    finally { setPicking(false); }
  };
  return <section className="draft-review" aria-label="数据接入">
    <strong>数据接入</strong>
    {card.image_names.length > 0 && <p>原图：{card.image_names.join('、')}</p>}
    {card.annotation_names.length > 0 && <p>标注：{card.annotation_names.join('、')}</p>}
    {card.stage === 'labels' && <>
      <p>在对话中填写标签名称，提交后由助手创建并保存。</p>
      {!!card.labels?.length && <p role="status">标签已就绪：{card.labels.map(label => label.name).join('、')}</p>}
      <button type="button" disabled={!canAct} aria-expanded={labelForm} onClick={() => setLabelForm(value => !value)}>创建标签</button>
    </>}
    {card.stage === 'choose_mode' && <>
      <p>请选择这批数据的标注情况。</p>
      <div className="work-actions">
        <button disabled={!canAct} onClick={() => send(command('选择导入方式') + ' 未标注')}>尚未标注</button>
        <button disabled={!canAct} onClick={() => send(command('选择导入方式') + ' 已有标注')}>已有标注</button>
        <button disabled={!canAct} onClick={() => send(command('检查同目录标注'))}>检查目录中的标注文件</button>
      </div>
    </>}
    {(card.stage === 'need_images' || card.stage === 'need_annotations') && <>
      <p>{card.stage === 'need_images' ? '请选择原图目录或 ENVI 文件。' : '请选择标注目录或 ROI JSON 文件，也可以在对话框输入路径。'}</p>
      <div className="work-actions">
        <button disabled={!canAct} onClick={() => void choose(true)}>选择目录</button>
        <button disabled={!canAct} onClick={() => void choose(false)}>选择文件</button>
        {card.stage === 'need_annotations' && <button disabled={!canAct} onClick={() => send(command('检查同目录标注'))}>与原图同目录</button>}
        {card.stage === 'need_annotations' && card.imported_count > 0 &&
          <button disabled={!canAct} onClick={() => send(command('进入人工标注'))}>返回超像素人工标注</button>}
      </div>
    </>}
    {card.stage === 'review' && <>
      <p>原图 {card.image_count} 个 · 成功配对 {card.paired_count} 个 · 未配对 {card.missing_count} 个 · 异常 {card.issue_count} 条</p>
      <p>类别：{card.classes.join('、') || '尚未识别到有效类别'}</p>
      {!!card.pairs?.length && <details><summary>查看原图、标注及区域数量</summary>
        <ul>{card.pairs.map((pair, index) => <li key={index}>{pair.image_name} → {pair.annotation_name} · {pair.region_count} 个区域 · {pair.labels.join('、')}</li>)}</ul>
      </details>}
      <p>接入后可直接预处理；未配对样品保留为待标注。</p>
      <div className="work-actions">
        <button disabled={!canAct || !card.paired_count} onClick={() => send(command('使用已配对标注'))}>使用成功配对的 {card.paired_count} 个标注</button>
        <button disabled={!canAct} onClick={() => send(command('调整标注路径'))}>调整标注路径</button>
        <button disabled={!canAct} onClick={() => send(command('查看导入异常'))}>查看异常与未配对原图</button>
      </div>
    </>}
    {card.stage === 'imported' && <>
      <p>已登记 {card.imported_count} 个数据集 · 已保存区域标注 {card.ready_count} 个 · 待标注 {remaining} 个</p>
      {!!card.labels?.length && <p role="status">标签类别已就绪：{card.labels.map(label => label.name).join('、')}</p>}
      {remaining > 0 && <p className="draft-todo">{card.labels?.length
        ? '下一步：生成超像素，在画布中选择标签并点选区域，保存后即可进入预处理。'
        : '下一步：先创建标签类别，再生成超像素并在画布中点选区域。'}</p>}
      {remaining > 0 && <p>创建标签只准备类别名称；点选区域并保存后，才计入已保存区域标注。</p>}
      <div className="work-actions">
        {card.ready_count > 0 && <button className="draft-primary" disabled={!canAct} onClick={() => send(command('进入预处理'))}>进入预处理</button>}
        <button type="button" className={card.labels?.length ? undefined : 'draft-primary'} disabled={!canAct} aria-expanded={labelForm}
          onClick={() => { setError(''); setLabelForm(value => !value); }}>{card.labels?.length ? '添加标签' : '创建标签'}</button>
        <button className={remaining > 0 && card.labels?.length ? 'draft-primary' : undefined} disabled={!canAct}
          onClick={() => send(command('进入人工标注'))}>{remaining > 0 ? '下一步：超像素人工标注' : '调整人工标注'}</button>
        {card.issue_count > 0 && <button disabled={!canAct} onClick={() => send(command('查看导入异常'))}>查看接入异常</button>}
      </div>
      <details><summary>已有区域标注文件？</summary>
        <p>如果已有 ROI JSON，可提供路径直接接入；在画布中人工标注无需填写标注路径。</p>
        <button disabled={!canAct} onClick={() => send(command('调整标注路径'))}>补充标注路径</button>
      </details>
    </>}
      {active && labelForm && ['imported', 'labels'].includes(card.stage) && <form className="intake-label-form" aria-label="批量创建标签" onSubmit={event => {
        event.preventDefault();
        if (!canAct) return;
        try { const text = createLabelsCommand(card.id, labelNames); setError(''); send(text); }
        catch (failure) { setError(failure instanceof Error ? failure.message : '标签名称不合法。'); }
      }}>
        <label htmlFor={`intake-labels-${card.id}`}>标签名称</label>
        <textarea id={`intake-labels-${card.id}`} rows={3} disabled={!canAct} value={labelNames}
          placeholder="例如：PE、PET、PP" onChange={event => setLabelNames(event.target.value)}
          aria-describedby={`intake-label-help-${card.id}`} />
        <p id={`intake-label-help-${card.id}`}>多个名称用顿号、逗号、分号或换行分隔。同名标签会复用，名称区分大小写。</p>
        <button type="submit" disabled={!canAct || !labelNames.trim()}>创建并保存标签</button>
      </form>}
    {active && !['imported', 'cancelled'].includes(card.stage) && <div className="work-actions">
      <button disabled={!canAct} onClick={() => send(command('取消数据导入'))}>取消本次导入</button>
    </div>}
    {!active && <small>历史导入记录，操作已停用。</small>}
    {error && <p role="alert">{error}</p>}
  </section>;
}
