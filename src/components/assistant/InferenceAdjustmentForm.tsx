import { useState, type FormEvent } from 'react';

const quality = [
  {key:'min_mean',label:'最低均值',hint:'无量纲反射率 · 光谱均值须高于此值'},
  {key:'min_std',label:'最低标准差',hint:'无量纲反射率 · 光谱标准差须高于此值',min:0},
  {key:'max_zero_fraction',label:'零值比例上限',hint:'比例（0–1）· 原始零值波段的占比上限',min:0,max:1},
];
const foreground = [
  {key:'threshold',label:'亮度阈值',hint:'无量纲反射率（通常 0–1）· 不高于此值的中心像元按低亮度排除'},
  {key:'left_min',label:'左侧最少屏蔽列数',hint:'单位：列（像元列）· 固定屏蔽左侧边缘',integer:true,min:0},
  {key:'right_min',label:'右侧最少屏蔽列数',hint:'单位：列（像元列）· 固定屏蔽右侧边缘',integer:true,min:0},
  {key:'edge_search_columns',label:'每侧探查列数',hint:'单位：列（像元列）· 从图像两侧向内探查',integer:true,min:0},
  {key:'edge_bad_fraction',label:'边缘异常比例',hint:'比例（大于 0、至多 1）· 每列异常像元占比',max:1},
  {key:'edge_low',label:'边缘亮度下限',hint:'无量纲反射率 · 低于此值视为边缘异常'},
  {key:'edge_high',label:'边缘亮度上限',hint:'无量纲反射率 · 高于此值视为边缘异常'},
];
const saturation = {key:'saturation',label:'饱和上限',hint:'单位：原始 DN · 达到此值的像元按饱和排除'};

type NumberField = {key:string; label:string; hint:string; integer?:boolean; min?:number; max?:number};

function Field({field,disabled,required}:{field:NumberField;disabled?:boolean;required?:boolean}) {
  return <label>{field.label}
    <input type="number" name={field.key} placeholder={field.hint} title={field.hint} step={field.integer ? 1 : 'any'}
      min={field.min} max={field.max} disabled={disabled} required={required}/>
  </label>;
}

export default function InferenceAdjustmentForm({revision,canAct,send,onCancel}:{
  revision:number;canAct:boolean;send:(text:string)=>void;onCancel:()=>void;
}) {
  const [saturationMode,setSaturationMode]=useState('keep');
  const [foregroundMode,setForegroundMode]=useState('keep');
  const [error,setError]=useState('');
  const submit=(event:FormEvent<HTMLFormElement>)=>{
    event.preventDefault();
    if(!canAct)return;
    setError('');
    const data = new FormData(event.currentTarget);
    const read = (name:string) => String(data.get(name)??'').trim();
    const collect = (fields:NumberField[])=>Object.fromEntries(fields.flatMap(({key})=>
      read(key) ? [[key,Number(read(key))]] : [])) as Record<string,number>;
    const q:Record<string,number|null> = collect(quality);
    if(saturationMode==='off') q.saturation=null;
    else if(read('saturation')) q.saturation=Number(read('saturation'));
    let fg:{mode:'none'|'brightness_edges';[key:string]:unknown}|undefined;
    if(foregroundMode==='off') fg={mode:'none'};
    else {
      const values = collect(foreground);
      if (values.edge_bad_fraction!==undefined && values.edge_bad_fraction<=0) {
        setError('边缘异常比例须大于 0。');return;
      }
      const waves = read('wavelengths_nm').split(/[\s,，、;；]+/).filter(Boolean).map(Number);
      if(read('wavelengths_nm') && (!waves.length || waves.some(w=>!Number.isFinite(w)||w<=0)
          || new Set(waves).size!==waves.length)) {
        setError('请填写不同的正数波长，可用逗号或空格分隔。');return;
      }
      if(foregroundMode==='on'||waves.length||Object.keys(values).length) {
        fg={mode:'brightness_edges', ...values, ...(waves.length?{wavelengths_nm:waves}:{})};
      }
    }
    if(!Object.keys(q).length&&!fg){setError('请填写至少一个要修改的参数，或选择开关。');return;}
    send('应用推理参数 '+JSON.stringify({expected_revision:revision,
      ...(Object.keys(q).length?{quality:q}:{}), ...(fg?{foreground:fg}:{})}));
  };
  return <form className="inference-adjustment" aria-label="微调推理参数" onSubmit={submit}>
    <p>只填要改的项，留空保留当前值。填写前景项会启用筛选。待选择前景时，未填写的前景项沿用本次探查结果。</p>
    <fieldset disabled={!canAct}><legend>质量筛选</legend><div className="adjustment-grid">
      {quality.map(field=><Field key={field.key} field={field}/>)}
      <label>饱和筛选<select aria-label="饱和筛选" value={saturationMode} onChange={e=>setSaturationMode(e.target.value)}>
        <option value="keep">保留当前设置</option><option value="set">设置上限</option><option value="off">关闭饱和筛选</option>
      </select></label>
      <Field field={saturation} disabled={saturationMode==='off'} required={saturationMode==='set'}/>
    </div></fieldset>
    <fieldset disabled={!canAct}><legend>前景筛选</legend><div className="adjustment-grid">
      <label>前景开关<select aria-label="前景开关" value={foregroundMode} onChange={e=>setForegroundMode(e.target.value)}>
        <option value="keep">保留当前设置</option><option value="on">启用</option><option value="off">关闭</option>
      </select></label>
      <label>亮度探测波段<input name="wavelengths_nm" disabled={foregroundMode==='off'}
        placeholder="单位：nm · 用逗号或空格分隔，取这些波段的中位数"/></label>
      {foreground.map(field=><Field key={field.key} field={field} disabled={foregroundMode==='off'}/>)}
    </div></fieldset>
    {error&&<p role="alert" className="agent-error">{error}</p>}
    <div className="work-actions">
      <button type="submit" className="draft-primary" disabled={!canAct}>应用修改</button>
      <button type="button" onClick={onCancel}>取消微调</button>
    </div>
  </form>;
}
