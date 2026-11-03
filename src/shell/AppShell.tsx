import type { ReactNode } from 'react';
import { NAV, SCREEN_TITLE, navHighlight, type Screen } from './screens';
import './theme.css';

export default function AppShell({ screen, onNavigate, topActions, children, assistant }: {
  screen: Screen; onNavigate(screen: Screen): void; topActions: ReactNode;
  children: ReactNode; assistant: ReactNode;
}) {
  return <div className="app-main" data-current-screen={screen}>
    <aside className="p-nav">
      <div className="p-brand">光谱数据 AI Agent</div>
      <nav aria-label="主导航">
        {NAV.map(group => <section className="p-nav-group" key={group.group} aria-label={group.group}>
          <h2>{group.group}</h2>
          {group.items.map(item => <button key={item.screen} data-nav={item.screen}
            aria-current={navHighlight(screen) === item.screen ? 'page' : undefined}
            onClick={() => onNavigate(item.screen)}>
            <span className="p-nav-icon" aria-hidden="true">{item.icon}</span>{item.label}
            {item.screen === 's05' && <span data-badge aria-hidden="true" />}
          </button>)}
        </section>)}
      </nav>
    </aside>
    <main className="p-main">
      <header className="p-top">
        <span className="p-breadcrumb" aria-label="当前位置">光谱数据 AI Agent / {SCREEN_TITLE[screen]}</span>
        <input type="search" aria-label="搜索（后续批次启用）" placeholder="搜索（后续批次启用）" disabled />
        {topActions}
      </header>
      <div className="p-body" key={screen}>{children}</div>
      {assistant}
    </main>
  </div>;
}
