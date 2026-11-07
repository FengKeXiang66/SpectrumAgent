import { useEffect, useState } from 'react';
import { displayName, type DatasetReference } from '../datasets/types.ts';
import { preprocessing } from '../preprocess/api.ts';
import { modeling, type ClassificationBody, type ClassificationResult } from './api.ts';
import { failureMessage } from './chart.ts';

export default function ClassificationPanel({ records, choices, busy, work, onOpenResults }: {
  records: DatasetReference[]; choices: Record<string, { id: string; version: string }[]>; busy: boolean;
  work(action: () => Promise<void>): Promise<void>; onOpenResults(id: string): void;
}) {
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [lv, setLV] = useState(''), [threshold, setThreshold] = useState(0), [seed, setSeed] = useState(17);
  const [metadata, setMetadata] = useState<{ pixels: number; classes: number } | null>(null);
  const [metadataError, setMetadataError] = useState(''), [preflight, setPreflight] = useState<unknown>(null);
  const [trained, setTrained] = useState<ClassificationResult | null>(null);
  const bound = records.flatMap(record => {
    const run = choices[record.id]?.find(row => row.id === selected[record.id]);
    return run ? [{ cube: record.id, run: run.id, version: run.version }] : [];
  });
  const binding = JSON.stringify(bound);
  useEffect(() => {
    let live = true;
    setMetadata(null); setMetadataError(''); setPreflight(null); setTrained(null);
    const refs = JSON.parse(binding) as typeof bound;
    if (!refs.length) return;
    void (async () => {
      let pixels = 0;
      const labels = new Set<string>();
      for (const ref of refs) {
        const report = await preprocessing.getArtifact(ref.run, 'report');
        if (report.run_id !== ref.run || report.annotation_version_id !== ref.version) throw new Error('预处理报告与绑定的标注版本不一致');
        for (const item of report.curves.classes) {
          if (item.label_index < 0 || item.count <= 0) continue;
          const label = report.label_index[String(item.label_index)];
          if (!label) throw new Error('预处理报告缺少类别映射');
          labels.add(label); pixels += item.count;
        }
      }
      if (live) setMetadata({ pixels, classes: labels.size });
    })().catch(failure => { if (live) setMetadataError(failureMessage(failure)); });
    return () => { live = false; };
  }, [binding]);
  const body = (): ClassificationBody => {
    if (!Number.isFinite(threshold) || threshold < 0 || threshold >= 1) throw new Error('置信度阈值须在 [0,1)');
    if (!Number.isInteger(seed)) throw new Error('随机种子须为整数');
    if (lv && (!Number.isInteger(Number(lv)) || Number(lv) < 1 || Number(lv) > 20)) throw new Error('手动 LV 须为 1–20 的整数');
    return { task: 'classification', cube_ids: bound.map(row => row.cube), annotation_version_ids: bound.map(row => row.version),
      preprocess_run_ids: bound.map(row => row.run), target: 'label', cv_strategy: 'group_kfold', cv_folds: 5,
      split_strategy: 'none', seed, confidence_threshold: threshold, ...(lv ? { n_components: Number(lv) } : {}) };
  };
  const ready = bound.length >= 5 && metadata !== null && metadata.classes >= 2 && metadata.pixels > 0;
  return <section className="classification-panel" aria-label="PLS-DA 分类配置">
    <fieldset disabled={busy}><legend>分类数据与标注版本</legend>
      <p>每个样品选择一个成功的预处理 run，使用该 run 绑定的确认版标注；-1 留白与 -2 不确定排除。</p>
      {records.map(record => <label key={record.id}>{displayName(record)}<select value={selected[record.id] ?? ''} onChange={event => setSelected({ ...selected, [record.id]: event.target.value })}>
        <option value="">不参与</option>{(choices[record.id] ?? []).map(run => <option key={run.id} value={run.id}>run {run.id} · 标注 {run.version}</option>)}</select></label>)}
      <p role="status">已选 {bound.length} 个样品；{metadata ? `确认版已标像素 ${metadata.pixels} 个，类别 ${metadata.classes} 个。` : bound.length ? '正在读取绑定版本的实际类别与像素数…' : '请选择参与训练的样品。'}</p>
      {metadataError && <p role="alert">{metadataError}</p>}
    </fieldset>
    <fieldset disabled={busy}><legend>分组验证与超参</legend>
      <p>固定按样品分组 5-fold · GroupKFold · group_by=sample_id（平台推导，不可关闭）</p>
      <p>同一样品的全部像素始终在同一侧；训练前强制泄漏预检，失败即阻断。</p>
      <label>随机种子<input type="number" step={1} value={seed} onChange={event => setSeed(Number(event.target.value))} /></label>
      <label>手动 LV（1–20，留空使用 CV 最小建议）<input type="number" min={1} max={20} value={lv} onChange={event => setLV(event.target.value)} /></label>
      <p>训练后同时返回 CV 最小与 RMSE 拐点两个真实建议值。</p>
      <label>置信度阈值<input type="number" min={0} max={1} step="any" value={threshold} onChange={event => setThreshold(Number(event.target.value))} /></label>
      <p>默认 0 不启用拒识；类别概率按 softmax 计算，低于阈值的像素标记为 -2 不确定，不进入指标分母。</p>
      <button disabled={!ready} onClick={() => void work(async () => {
        const request = body();
        setPreflight(await modeling.preflight({ cube_ids: request.cube_ids, annotation_version_ids: request.annotation_version_ids,
          preprocess_run_ids: request.preprocess_run_ids, task: 'classification', target: 'label', cv_strategy: 'group_kfold', cv_folds: 5, seed }));
      })}>分类预检</button>
      <button disabled={!ready} onClick={() => void work(async () => {
        setTrained(null);
        const row = await modeling.train(body());
        if (row.task !== 'classification' || row.status !== 'succeeded' || !row.confusion) throw new Error(JSON.stringify(row.error ?? '分类训练尚未成功'));
        setTrained(row);
      })}>{busy ? '正在计算…' : '训练 PLS-DA'}</button>
    </fieldset>
    {preflight !== null && <details open><summary>分类预检结果</summary><pre>{JSON.stringify(preflight, null, 2)}</pre></details>}
    {trained && <section aria-label="分类训练完成"><h3>分类训练完成</h3>
      <p>CV 最小建议 LV：{trained.by_cv_min ?? '不适用'}；RMSE 拐点建议 LV：{trained.by_elbow ?? '不适用'}；使用 LV：{trained.selected_lv ?? '不适用'}</p>
      <button onClick={() => onOpenResults(trained.run_id)}>查看分类结果</button>
    </section>}
  </section>;
}
