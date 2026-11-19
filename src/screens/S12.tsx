import { useEffect, useRef, useState } from 'react';
import { annotations } from '../components/annotation/api.ts';
import { datasets } from '../components/datasets/api.ts';
import { displayName, type DatasetReference, type TrainingSetMemberInput, type TrainingSetMembersResponse,
  type TrainingSetPreviewResponse, type TrainingSetVersion } from '../components/datasets/types.ts';
import { datasetVersionSelection } from '../components/modeling/dataset-version-store.ts';
import { preflightAlerts, type NearDuplicatePair } from '../components/modeling/preflight-alert-store.ts';
import { preprocessing } from '../components/preprocess/api.ts';
import { recipeEvents } from '../components/preprocess/recipe-events.ts';
import type { Recipe } from '../components/preprocess/types.ts';
import './s12.css';

export default function S12({ records, onOpenModeling }: { records: DatasetReference[]; onOpenModeling: () => void }) {
  const [recipes, setRecipes] = useState<Recipe[]>([]), [recipeId, setRecipeId] = useState('');
  const [confirmed, setConfirmed] = useState<Record<string, { id: string; number: number } | null>>({});
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [versions, setVersions] = useState<TrainingSetVersion[]>([]), [versionId, setVersionId] = useState('');
  const [preview, setPreview] = useState<TrainingSetPreviewResponse | null>(null);
  const [resolved, setResolved] = useState<TrainingSetMembersResponse | null>(null);
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [message, setMessage] = useState('');
  const [alerts, setAlerts] = useState<NearDuplicatePair[]>([]);
  const sequence = useRef({ list: 0, detail: 0, live: true });
  const recordsKey = JSON.stringify([...new Set(records.map(record => record.id))]);
  const failure = (value: unknown) => typeof value === 'object' && value !== null && 'detail' in value ? String((value as { detail: unknown }).detail) : String(value);
  useEffect(() => { sequence.current.live = true; return () => { sequence.current.live = false; sequence.current.list++; sequence.current.detail++; }; }, []);
  const refresh = async () => {
    const ticket = ++sequence.current.list;
    try {
      const [rows, saved] = await Promise.all([datasets.trainingSets(), preprocessing.listRecipes()]);
      if (!sequence.current.live || ticket !== sequence.current.list) return;
      setVersions(rows.filter(row => row.is_frozen === 1)); setRecipes(saved);
    } catch (reason) { if (sequence.current.live && ticket === sequence.current.list) setError(failure(reason)); }
  };
  useEffect(() => { void refresh(); }, []);
  useEffect(() => {
    setAlerts(preflightAlerts.get());
    return preflightAlerts.subscribe(() => setAlerts(preflightAlerts.get()));
  }, []);
  useEffect(() => { const changed = () => { void refresh(); }; recipeEvents.addEventListener('change', changed); return () => recipeEvents.removeEventListener('change', changed); }, []);
  useEffect(() => {
    let live = true;
    const cubes = JSON.parse(recordsKey) as string[];
    setLoading(true); setSelected(Object.fromEntries(cubes.map(cube => [cube, true]))); setError('');
    void Promise.all(cubes.map(async cube => {
      const listing = await annotations.versions(cube);
      const latest = [...listing.versions].sort((a, b) => b.version_no - a.version_no)[0];
      return [cube, latest ? { id: latest.id, number: latest.version_no } : null] as const;
    })).then(rows => { if (live) {
      const map = Object.fromEntries(rows);
      setConfirmed(map);
      setSelected(Object.fromEntries(cubes.map(cube => [cube, !!map[cube]])));
    } })
      .catch(reason => { if (live) setError(failure(reason)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [recordsKey]);
  const members: TrainingSetMemberInput[] = [...new Set(records.map(record => record.id))]
    .flatMap(cube => selected[cube] && confirmed[cube] && recipeId
      ? [{ cube_id: cube, annotation_version_id: confirmed[cube]!.id, recipe_version_id: recipeId }] : []);
  const choose = async (id: string) => {
    const ticket = ++sequence.current.detail;
    setVersionId(id); setResolved(null); setPreview(null); setError(''); setMessage('');
    if (!id) { datasetVersionSelection.set(''); return; }
    datasetVersionSelection.set(id);
    try {
      const result = await datasets.trainingSetMembers(id);
      if (result.version_id !== id || !result.members.length || new Set(result.members.map(member => member.cube_id)).size !== result.members.length)
        throw new Error('训练集成员响应不完整或版本归属不一致');
      if (sequence.current.live && ticket === sequence.current.detail) setResolved(result);
    } catch (reason) { if (sequence.current.live && ticket === sequence.current.detail) setError(failure(reason)); }
  };
  useEffect(() => {
    const saved = datasetVersionSelection.get();
    if (saved && !versionId) void choose(saved);
  }, [versions]);
  const generate = async () => {
    if (!members.length) return;
    setBusy(true); setError(''); setMessage('');
    const ticket = ++sequence.current.detail;
    try {
      const result = await datasets.trainingSetPreview({ members, options: { content_hash_dedup: true } });
      if (sequence.current.live && ticket === sequence.current.detail) {
        setPreview(result); setVersionId(''); setResolved(null);
        setMessage(result.reused ? `同内容复用训练集 ${result.id}` : result.duplicate_of ? `同内容已有版本 ${result.duplicate_of}` : '训练集预览已生成，确认后冻结。');
      }
    } catch (reason) { if (sequence.current.live && ticket === sequence.current.detail) setError(failure(reason)); }
    finally { if (sequence.current.live) setBusy(false); }
  };
  const freeze = async () => {
    if (!preview) return;
    setBusy(true); setError('');
    sequence.current.list++;
    try {
      const frozen = preview.is_frozen === 1 ? preview : await datasets.trainingSetConfirm(preview.id);
      if (frozen.id !== preview.id || frozen.is_frozen !== 1) throw new Error('确认响应不是请求的冻结训练集');
      const rows = await datasets.trainingSets();
      if (!rows.some(row => row.id === frozen.id && row.is_frozen === 1)) throw new Error('冻结版本尚未出现在列表中，请刷新后选择');
      setVersions(rows.filter(row => row.is_frozen === 1)); setPreview(null);
      await choose(frozen.id);
      setMessage('训练集已冻结并设为当前数据集版本。');
    } catch (reason) { if (sequence.current.live) setError(failure(reason)); }
    finally { if (sequence.current.live) setBusy(false); }
  };
  return <section className="dataset-version-screen ui-page" aria-label="数据集版本">
    <header className="dv-heading"><h2>数据集版本</h2><p>建模前固定训练集版本：选定配方与已确认标注范围，生成预览后冻结，建模页只使用这里选定的版本。</p></header>
    {alerts.length > 0 && <div role="status" className="dv-alert-banner">
      建模预检发现 {alerts.length} 对近似重复样品，已在下表用警示色标出。请从每一对中取消一个样品，再重新生成训练集预览并冻结。
    </div>}
    <p role="status">{message}</p>{error && <pre role="alert">{error}</pre>}
    <fieldset className="dv-card" disabled={busy}><legend>版本范围</legend>
      <label>训练配方版本<select aria-label="训练配方版本" value={recipeId} onChange={event => { setRecipeId(event.target.value); setPreview(null); }}>
        <option value="">请选择已保存的配方版本</option>{recipes.flatMap(recipe => recipe.versions.map(version =>
          <option key={version.id} value={version.id}>{recipe.name} · v{version.version_no}</option>))}</select></label>
      <p>按范围内每个样品最新的确认版标注生成训练集；工作草稿不会进入版本。</p>
      <div className="dv-scroll"><table className="dv-table"><thead><tr><th>选择</th><th>样品</th><th>确认版标注</th><th>配方</th><th>预检预警</th></tr></thead><tbody>
        {records.map(record => { const annotation = confirmed[record.id];
          const flags = alerts.filter(pair => pair.a === record.id || pair.b === record.id).map(pair => {
            const otherId = pair.a === record.id ? pair.b : pair.a;
            const other = records.find(row => row.id === otherId);
            return `与 ${other ? displayName(other) : otherId.slice(0, 8)} 相似 ${pair.similarity.toFixed(5)}（二选一）`;
          });
          return <tr key={record.id} className={flags.length ? 'dv-warn-row' : undefined}><td><input type="checkbox" aria-label={`范围 ${displayName(record)}`} disabled={loading || !annotation}
            checked={!!selected[record.id]} onChange={event => setSelected(current => ({ ...current, [record.id]: event.target.checked }))} /></td>
            <td>{displayName(record)}</td><td>{annotation ? `v${annotation.number}` : '缺标注'}</td><td>{recipeId ? '已选配方' : '待选配方'}</td>
            <td>{flags.length ? flags.join('；') : ''}</td></tr>; })}
      </tbody></table></div>
      <button className="dv-primary" disabled={busy || loading || !members.length} onClick={() => { void generate(); }}>生成训练集预览</button>
    </fieldset>
    {preview && <section className="dv-card" aria-label="训练集预览"><h3>训练集预览</h3>
      <p>成员 {preview.member_count} 个 · 缺预处理 {preview.need_preprocess.length} 个</p>
      <ul>{Object.entries(preview.label_summary).map(([label, count]) => <li key={label}>{label}：{count}</li>)}</ul>
      {preview.reused && <p>同内容复用训练集 {preview.id}</p>}{preview.duplicate_of && <p>同内容已有版本 {preview.duplicate_of}</p>}
      {preview.need_preprocess.map(member => <p key={member.cube_id}>{displayName(records.find(row => row.id === member.cube_id) ?? { id: member.cube_id, display_name: member.cube_id })} · 标注 {member.annotation_version_id} · 配方 {member.recipe_version_id}：先补跑缺失的预处理</p>)}
      <button className="dv-primary" disabled={busy} onClick={() => { void freeze(); }}>{preview.is_frozen === 1 ? '选用已冻结版本' : '确认冻结训练集'}</button>
    </section>}
    <fieldset className="dv-card" disabled={busy}><legend>已冻结版本</legend>
      <label>当前数据集版本<select aria-label="已冻结训练集" value={versionId} onChange={event => { void choose(event.target.value); }}>
        <option value="">请选择已冻结训练集</option>{versions.map(version => <option key={version.id} value={version.id}>{version.member_count} 个样品 · {version.confirmed_at?.replace('T', ' ').slice(0, 16)} · {version.id.slice(0, 8)}</option>)}</select></label>
      <button onClick={() => { void refresh(); }}>刷新版本与配方</button>
      {resolved && <><p>成员 {resolved.members.length} 个 · 缺预处理 {resolved.need_preprocess.length} 个</p>
        <div className="dv-scroll"><table className="dv-table"><thead><tr><th>样品</th><th>标注版本</th><th>配方版本</th><th>预处理 run</th></tr></thead><tbody>
          {resolved.members.map(member => <tr key={member.cube_id}><td>{displayName(records.find(row => row.id === member.cube_id) ?? { id: member.cube_id, display_name: member.cube_id })}</td>
            <td>{member.annotation_version_id.slice(0, 8)}</td><td>{member.recipe_version_id.slice(0, 8)}</td><td>{member.preprocess_run_id?.slice(0, 8) ?? '缺失'}</td></tr>)}
        </tbody></table></div></>}
      <button className="dv-primary" disabled={!versionId} onClick={onOpenModeling}>在建模中使用此版本</button>
    </fieldset>
  </section>;
}
