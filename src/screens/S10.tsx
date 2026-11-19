export default function S10({ onOpenData }: { onOpenData(): void }) {
  return <section className="model-panel" aria-label="检索">
    <h2>检索</h2>
    <p>检索在阶段二提供。</p>
    <button onClick={onOpenData}>返回数据屏</button>
  </section>;
}
