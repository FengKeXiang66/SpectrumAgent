export const DEFAULT_PANEL_HEIGHT = 360;

export function panelBounds(availableHeight: number) {
  const workspace = Math.min(160, availableHeight * 0.4);
  const max = Math.floor(Math.min(availableHeight * 0.65, availableHeight - workspace));
  return { min: Math.min(260, max), max };
}

export function clampPanelHeight(height: number, bounds: { min: number; max: number }) {
  return Math.min(bounds.max, Math.max(bounds.min, height));
}

export function draggedPanelHeight(startHeight: number, startY: number, currentY: number, bounds: { min: number; max: number }) {
  return clampPanelHeight(startHeight + startY - currentY, bounds);
}
