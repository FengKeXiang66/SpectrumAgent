import assert from 'node:assert/strict';
import test from 'node:test';
import { clampPanelHeight, DEFAULT_PANEL_HEIGHT, draggedPanelHeight, panelBounds } from './panel-height.ts';

test('panel keeps a visible minimum and leaves space for the workbench at different window heights', () => {
  for (const height of [360, 480, 600, 900, 1440]) {
    const bounds = panelBounds(height);
    assert.ok(bounds.min > 0 && bounds.min <= bounds.max);
    assert.ok(bounds.max <= height * 0.65);
    assert.ok(height - bounds.max >= Math.min(160, height * 0.4));
    assert.equal(clampPanelHeight(-1000, bounds), bounds.min);
    assert.equal(clampPanelHeight(10000, bounds), bounds.max);
  }
});

test('bottom panel grows when dragged upwards, shrinks downwards, and clamps both ends', () => {
  const bounds = panelBounds(900);
  assert.equal(draggedPanelHeight(360, 600, 500, bounds), 460);
  assert.equal(draggedPanelHeight(360, 600, 650, bounds), 310);
  assert.equal(draggedPanelHeight(360, 600, -10000, bounds), bounds.max);
  assert.equal(draggedPanelHeight(360, 600, 10000, bounds), bounds.min);
});

test('a smaller window clamps a previously enlarged panel into its new bounds', () => {
  const bounds = panelBounds(360);
  assert.equal(clampPanelHeight(580, bounds), bounds.max);
  assert.ok(clampPanelHeight(DEFAULT_PANEL_HEIGHT, bounds) > 0);
});
