import SettingsPanel from '../components/settings/SettingsPanel';
import ProjectPathsPanel from '../components/settings/ProjectPathsPanel';
import SmokePanel from '../components/settings/SmokePanel';
import '../components/settings/settings.css';

export default function S11({ onBack }: { onBack(): void }) {
  return <section className="model-panel settings-screen" aria-label="设置与出域记录">
    <h2>设置与出域记录</h2>
    <p>在设置中管理模型连接与出域开关，出域记录用于查看相关操作。</p>
    <SettingsPanel onClose={onBack} />
    <ProjectPathsPanel summary />
    <SmokePanel />
    <section aria-label="删除口径"><h3>删除口径</h3>
      <p>删除数据集即永久删除：数据库记录与程序产物一并清除，不可恢复；原始 ENVI 源文件保持不变。删除事件写入只增不改的审计表。</p>
    </section>
    <section aria-label="出域禁运清单"><h3>出域禁运清单</h3><ul>
      <li>NAS 路径与文件名</li><li>凭据与访问密钥</li><li>原始光谱文件与像素数据</li>
    </ul></section>
    <section aria-label="出域记录"><h3>出域记录</h3><p>出域记录在阶段二提供</p></section>
  </section>;
}
