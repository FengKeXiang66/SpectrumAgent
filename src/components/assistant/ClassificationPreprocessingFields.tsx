import { classificationOperators, type ExperimentStep } from './preprocessing-form';
import { useState } from 'react';

export default function ClassificationPreprocessingFields({ steps, onChange, disabled }: {
  steps: ExperimentStep[]; onChange(steps: ExperimentStep[]): void; disabled: boolean;
}) {
  const [op, setOp] = useState('savgol');
  const update = (index: number, key: string, value: number | string | null) =>
    onChange(steps.map((step, i) => {
      if (i !== index) return step;
      const next = { ...step };
      if (value === null) delete next[key]; else next[key] = value;
      return next;
    }));
  const numeric = (index: number, key: string, title: string) => <label key={key}>{title}
    <input type="number" step="any" value={steps[index][key] ?? ''} onChange={event =>
      update(index, key, event.target.value === '' ? null : Number(event.target.value))} /></label>;
  return <fieldset disabled={disabled}><legend>分类预处理步骤</legend>
    <p>参数写入训练方案；需要学习的参数仅在训练折内拟合，再应用于验证和测试数据。</p>
    <label>算子<select value={op} onChange={event => setOp(event.target.value)}>
      {classificationOperators.map(value => <option key={value}>{value}</option>)}</select></label>
    <button type="button" onClick={() => onChange([...steps, { op }])}>添加一步</button>
    <ol>{steps.map((step, index) => <li key={`${index}-${step.op}`}><strong>{index + 1} · {step.op}</strong>
      <button type="button" disabled={index === 0} onClick={() => { const next = [...steps]; [next[index - 1], next[index]] = [next[index], next[index - 1]]; onChange(next); }}>上移</button>
      <button type="button" disabled={index === steps.length - 1} onClick={() => { const next = [...steps]; [next[index + 1], next[index]] = [next[index], next[index + 1]]; onChange(next); }}>下移</button>
      <button type="button" onClick={() => onChange(steps.filter((_, i) => i !== index))}>删除</button>
      <div className="preprocessing-fields">
        {step.op === 'savgol' && <>{numeric(index, 'window', 'SG 窗口（奇数）')}{numeric(index, 'polyorder', '多项式阶数')}
          <label>导数阶数<select value={step.derivative ?? ''} onChange={event => update(index, 'derivative', Number(event.target.value))}>
            <option value="" disabled>请选择</option>{[0, 1, 2].map(value => <option key={value}>{value}</option>)}</select></label>
          {numeric(index, 'delta_nm', '波长步长 nm')}
          <label>边界模式<select value={step.mode ?? 'interp'} onChange={event => update(index, 'mode', event.target.value)}>
            {['interp', 'mirror', 'constant', 'nearest', 'wrap'].map(value => <option key={value}>{value}</option>)}</select></label>
          <p>步长须匹配方案中的等间隔波长轴；需要时先通过对话配置波长对齐。</p></>}
        {step.op === 'pca' && numeric(index, 'n_components', '主成分数')}
        {step.op === 'snv' && <label>ddof<select value={step.ddof ?? 1} onChange={event => update(index, 'ddof', Number(event.target.value))}><option>0</option><option>1</option></select></label>}
        {step.op === 'l2' && numeric(index, 'epsilon', 'epsilon（留空使用 1e-12）')}
      </div>
    </li>)}</ol>
  </fieldset>;
}
