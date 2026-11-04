import SettingsPanel from '../components/settings/SettingsPanel';
import { useEffect, useState } from 'react';
import ProjectPathsPanel from '../components/settings/ProjectPathsPanel';
import { datasets } from '../components/datasets/api';
import { describeError, type RecycleList } from '../components/datasets/types';
import { RecycleSummary } from '../components/datasets/RecycleView';
import '../components/settings/settings.css';

export default function S11({ onBack }: { onBack(): void }) {
  const [recycle, setRecycle] = useState<RecycleList | null>(null), [error, setError] = useState(''), [reload, setReload] = useState(0);
  useEffect(() => {
    let live = true;
    setRecycle(null); setError('');
    void datasets.recycleList().then(value => { if (live) setRecycle(value); })
      .catch(failure => { if (live) setError(describeError(failure)); });
    return () => { live = false; };
  }, [reload]);
  return <section className="model-panel settings-screen" aria-label="设置与出域记录">
    <h2>设置与出域记录</h2>
    <p>在设置中管理模型连接与出域开关，出域记录用于查看相关操作。</p>
    <SettingsPanel onClose={onBack} />
    <ProjectPathsPanel summary />
    {error ? <p role="alert">{error}</p> : recycle ? <RecycleSummary value={recycle} /> : <p role="status">正在读取回收站占用…</p>}
    <button onClick={() => setReload(current => current + 1)}>刷新回收站占用</button>
    <section aria-label="出域禁运清单"><h3>出域禁运清单</h3><ul>
      <li>NAS 路径与文件名</li><li>凭据与访问密钥</li><li>原始光谱文件与像素数据</li>
    </ul></section>
    <section aria-label="出域记录"><h3>出域记录</h3><p>出域记录在阶段二提供</p></section>
  </section>;
}
