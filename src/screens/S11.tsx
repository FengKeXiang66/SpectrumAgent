export default function S11({ onOpenSettings }: { onOpenSettings(): void }) {
  return <section className="model-panel" aria-label="设置与出域记录">
    <h2>设置与出域记录</h2>
    <p>在设置中管理模型连接与出域开关，出域记录用于查看相关操作。</p>
    <button onClick={onOpenSettings}>打开设置</button>
    <section aria-label="出域记录"><h3>出域记录</h3><p>出域记录在阶段二提供</p></section>
  </section>;
}
