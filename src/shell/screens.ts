export type Screen = 's01'|'s02'|'s03'|'s04'|'s05'|'s06'|'s07'|'s08'|'s09'|'s10'|'s11';

export const NAV: { group: string; items: { screen: Screen; label: string; icon: string }[] }[] = [
  { group: '主入口', items: [{ screen: 's01', label: '智能助手', icon: '◈' }] },
  { group: '我的工作', items: [{ screen: 's02', label: '工作台', icon: '◧' }] },
  { group: '分析流程', items: [
    { screen: 's03', label: '数据', icon: '▤' },
    { screen: 's05', label: '标注', icon: '✎' },
    { screen: 's06', label: '预处理', icon: '⚗' },
    { screen: 's07', label: '建模', icon: '⊞' },
    { screen: 's08', label: '结果', icon: '◫' },
  ] },
  { group: '沉淀与复用', items: [
    { screen: 's09', label: '实验台账', icon: '☰' },
    { screen: 's10', label: '检索', icon: '⌕' },
  ] },
  { group: '本机', items: [{ screen: 's11', label: '设置与出域记录', icon: '⚙' }] },
];

export const SCREEN_TITLE: Record<Screen, string> = {
  s01: '智能助手', s02: '工作台', s03: '数据', s04: '数据查看器',
  s05: '标注', s06: '预处理', s07: '建模', s08: '结果',
  s09: '实验台账', s10: '检索', s11: '设置与出域记录',
};

export function navHighlight(screen: Screen): Screen {
  return screen === 's04' ? 's03' : screen;
}
