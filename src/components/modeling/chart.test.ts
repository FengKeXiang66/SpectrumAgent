import assert from 'node:assert/strict';
import test from 'node:test';
import { extent, failureMessage, FRAME, histogram, mapValue, niceTicks, regressionCharts, SERIES, splitRuns } from './chart.ts';

const sweep = {
  best_lv: 2, elbow_lv: 3, selected_lv: 1, by_cv_min: 2, by_elbow: 3, manual_override: true,
  definition: 'pooled held-out RMSECV; elbow <= best RMSECV + one SD of best fold RMSE',
  curve: [{ n_components: 1, rmsecv: 3, sd: .1 }, { n_components: 2, rmsecv: 1, sd: .1 }, { n_components: 3, rmsecv: 2, sd: .2 }],
};
const result = {
  semi_quantitative: true, quality_label: '仅可做半定量', metrics: { rpd: null, r2: null },
  predictions: [
    { cube_id: 'a', set: 'calibration', y_true: 0, y_pred: .2, residual: .2 },
    { cube_id: 'b', set: 'calibration', y_true: 2, y_pred: 1.8, residual: -.2 },
    { cube_id: 'c', set: 'prediction', y_true: 1, y_pred: 1.4, residual: .4 },
    { cube_id: 'd', set: 'prediction', y_true: 3, y_pred: 2.7, residual: -.3 },
  ],
};
function finiteOutput(value: unknown) {
  if (typeof value === 'number') assert.ok(Number.isFinite(value), 'prepared chart contains non-finite number');
  else if (Array.isArray(value)) value.forEach(finiteOutput);
  else if (value && typeof value === 'object') Object.values(value).forEach(finiteOutput);
}

test('extents exclude null and non-finite values without changing inputs', () => {
  const values = [null, 3, -2, NaN, Infinity, undefined];
  assert.deepEqual(extent(values), { low: -2, high: 3 });
  assert.equal(extent([null, NaN, -Infinity]), null);
  assert.equal(values.length, 6);
});

test('coordinate mapping covers endpoints, inverted Y, constants and extreme finite domains', () => {
  assert.equal(mapValue(0, { low: 0, high: 10 }, 70, 870), 70);
  assert.equal(mapValue(10, { low: 0, high: 10 }, 435, 55), 55);
  assert.equal(mapValue(5, { low: 5, high: 5 }, 435, 55), 245);
  assert.equal(mapValue(0, { low: -1e308, high: 1e308 }, 0, 100), 50);
  assert.equal(mapValue(NaN, { low: 0, high: 1 }, 0, 100), null);
  assert.equal(mapValue(0, { low: 2, high: 1 }, 0, 100), null);
});

test('nice ticks are deterministic, rounded and integer-only for counts or LVs', () => {
  assert.deepEqual(niceTicks({ low: -1.1, high: 3.7 }), [-1, 0, 1, 2, 3]);
  assert.deepEqual(niceTicks({ low: .02, high: .09 }), [.02, .04, .06, .08]);
  assert.deepEqual(niceTicks({ low: 0, high: 3 }, 5, true), [0, 1, 2, 3]);
  assert.deepEqual(niceTicks({ low: 4, high: 4 }), [4]);
  assert.deepEqual(niceTicks({ low: NaN, high: 4 }), []);
});

test('null and non-finite curve points split paths and never interpolate gaps', () => {
  const values = [1, 2, null, 4, NaN, 6];
  assert.deepEqual(splitRuns(values, value => value === null ? null : { x: value, y: value }),
    [[{ x: 1, y: 1 }, { x: 2, y: 2 }], [{ x: 4, y: 4 }], [{ x: 6, y: 6 }]]);
});

test('histogram uses sqrt sample count capped at 20, shared rounded edges and grouped counts', () => {
  const values = Array.from({ length: 9 }, (_, value) => ({ value, set: value % 2 ? 'prediction' as const : 'calibration' as const }));
  const bins = histogram(values);
  assert.equal(bins.length, 3);
  assert.equal(bins[0].low, 0); assert.equal(bins.at(-1)!.high, 8);
  assert.deepEqual(bins.map(bin => bin.calibration + bin.prediction), [3, 3, 3]);
  assert.equal(bins.reduce((total, bin) => total + bin.calibration, 0), 5);
  assert.deepEqual(histogram(values), bins);
  assert.equal(histogram(Array.from({ length: 500 }, (_, value) => ({ value, set: 'prediction' as const }))).length, 20);
  const negative = histogram([{ value: -.2, set: 'prediction' }, { value: 1.2, set: 'calibration' }]);
  assert.equal(negative[0].low, -1); assert.equal(negative.at(-1)!.high, 2);
});

test('histogram bins are left-closed with rightmost edge included; rounded inner edges agree with membership', () => {
  const bins = histogram([0, 3, 6, 6].map(value => ({ value, set: 'prediction' as const })));
  assert.deepEqual(bins.map(bin => bin.prediction), [1, 3]);
  const edge = histogram([0, 1, 2, 3, 4, 5, 6, 7, 8].map(value => ({ value, set: 'prediction' as const })))[0].high;
  const rounded = histogram([0, edge, 2, 3, 4, 5, 6, 7, 8].map(value => ({ value, set: 'prediction' as const })));
  assert.equal(rounded[0].prediction, 2); assert.equal(rounded[1].prediction, 4);
});

test('one histogram sample becomes a single nonzero-width bin; invalid values produce no bins', () => {
  const bins = histogram([{ value: 2, set: 'prediction' }]);
  assert.equal(bins.length, 1); assert.equal(bins[0].prediction, 1);
  assert.ok(bins[0].high > bins[0].low);
  assert.deepEqual(histogram([{ value: NaN, set: 'prediction' }]), []);
  finiteOutput(bins);
});

test('four evaluation models include curve, scatter, residual and grouped histogram', () => {
  const original = structuredClone({ result, sweep });
  const charts = regressionCharts({ result, sweep });
  assert.deepEqual(charts.map(chart => chart.kind), ['curve', 'scatter', 'residual', 'histogram']);
  assert.ok(charts.every(chart => chart.status === 'ready'));
  assert.equal(charts[1].points.length, 4); assert.equal(charts[2].points.length, 4);
  for (const chart of charts.slice(1)) {
    assert.ok(chart.legend.some(item => item.label.startsWith('校准')));
    assert.ok(chart.legend.some(item => item.label.startsWith('预测')));
    assert.notEqual(chart.legend[0].color, chart.legend[1].color);
  }
  assert.ok(charts[3].bars.length > 0);
  assert.deepEqual({ result, sweep }, original);
  finiteOutput(charts);
});

test('LV markers use saved recommendations verbatim rather than recomputing an elbow', () => {
  // Saved elbow=3 deliberately differs from the value a local threshold algorithm would return.
  const chart = regressionCharts({ result, sweep })[0];
  const elbow = chart.markers.find(marker => marker.label === '拐点建议 LV')!;
  assert.equal(elbow.lv, sweep.elbow_lv);
  assert.equal(elbow.x, FRAME.right);
  assert.equal(chart.markers.find(marker => marker.label === '交叉验证最小 LV')!.lv, sweep.best_lv);
  assert.equal(chart.markers.find(marker => marker.label === '手动 LV')!.lv, sweep.selected_lv);
  assert.equal(chart.definition, sweep.definition);
  const automatic = regressionCharts({ result, sweep: { ...sweep, manual_override: false } })[0];
  assert.ok(automatic.markers.some(marker => marker.label === '采用 LV'));
});

test('empty curve and all non-finite curves show explicit no-data status without axes', () => {
  for (const curve of [[], [{ n_components: 1, rmsecv: NaN, sd: 1 }], [{ n_components: 1, rmsecv: Infinity, sd: 1 }]]) {
    const chart = regressionCharts({ result, sweep: { ...sweep, curve } })[0];
    assert.equal(chart.message, '无可用曲线数据'); assert.equal(chart.status, 'empty');
    assert.deepEqual(chart.xTicks, []); finiteOutput(chart);
  }
});

test('curve missing values retain separated finite paths and single-point strokes', () => {
  const chart = regressionCharts({ result, sweep: { ...sweep, curve: [
    sweep.curve[0], { n_components: 2, rmsecv: null, sd: 0 }, sweep.curve[2],
  ] } })[0];
  assert.deepEqual(chart.lines.filter(line => line.color === '#26374b').map(line => line.points.length), [1, 1]);
  assert.ok(chart.notes.some(note => note.includes('断线')));
  finiteOutput(chart);
});

test('one prediction is a square, maps constant axes to midlines and has one populated histogram bar', () => {
  const single = { predictions: [{ set: 'prediction', y_true: 2, y_pred: 2, residual: 0 }] };
  const charts = regressionCharts({ result: single, sweep });
  assert.equal(charts[1].points[0].square, true);
  assert.equal(charts[1].points[0].x, (FRAME.left + FRAME.right) / 2);
  assert.equal(charts[1].points[0].y, (FRAME.top + FRAME.bottom) / 2);
  assert.ok(charts[1].notes.includes('参考值无变化'));
  assert.equal(charts[3].bars.filter(bar => bar.height > 0).length, 1);
  finiteOutput(charts);
});

test('constant references with varying predictions remain on X midline with an explicit note', () => {
  const constant = { predictions: result.predictions.map(row => ({ ...row, y_true: 1 })) };
  const charts = regressionCharts({ result: constant, sweep });
  assert.ok(charts[1].points.every(point => point.x === (FRAME.left + FRAME.right) / 2));
  assert.ok(charts[1].notes.includes('参考值无变化'));
  finiteOutput(charts);
});

test('null metrics never enter chart coordinates or quality calculations', () => {
  const a = regressionCharts({ result, sweep });
  const b = regressionCharts({ result: { ...result, metrics: { rpd: Infinity, r2: 1e200 } }, sweep });
  assert.deepEqual(a, b); finiteOutput(a);
});

test('get_run failure produces four explicit unavailable plots, never blank axes', () => {
  const charts = regressionCharts({ result: null, sweep: null, runError: 'RUN_NOT_FOUND' });
  for (const chart of charts) {
    assert.equal(chart.status, 'unavailable');
    assert.match(chart.message, /无法获取.*RUN_NOT_FOUND/);
    assert.equal(chart.xTicks.length, 0); assert.equal(chart.points.length, 0);
  }
});

test('missing LV artifact preserves the three prediction plots and their quality labels', () => {
  const charts = regressionCharts({ result, sweepError: 'ARTIFACT_NOT_FOUND' });
  assert.match(charts[0].message, /无法获取.*ARTIFACT_NOT_FOUND/);
  assert.ok(charts.slice(1).every(chart => chart.status === 'ready'));
  assert.ok(charts.every(chart => chart.qualityLabel === '仅可做半定量'));
});

test('undefined predictions from classification runs are explicit, empty arrays remain no-data', () => {
  for (const predictions of [undefined, null]) {
    const charts = regressionCharts({ result: { status: 'succeeded', metrics: [], predictions }, sweep });
    assert.ok(charts.slice(1).every(chart => chart.status === 'unavailable' && chart.message.includes('未提供')));
    finiteOutput(charts);
  }
  const charts = regressionCharts({ result: { predictions: [] }, sweep });
  assert.ok(charts.slice(1).every(chart => chart.status === 'empty' && chart.message.includes('无可用')));
});

test('missing fields and unknown sets are excluded per chart, with an explicit reason when all are unusable', () => {
  const charts = regressionCharts({ result: { predictions: [
    { set: 'other', y_true: 1, y_pred: 2, residual: 1 },
    { set: 'prediction', y_pred: 2 },
  ] }, sweep });
  assert.ok(charts.slice(1, 3).every(chart => chart.status === 'unavailable' && chart.message.includes('缺少')));
  assert.equal(charts[3].status, 'ready');
  finiteOutput(charts);
});

test('half-quantitative label uses backend flag or label and never derives RPD', () => {
  assert.ok(regressionCharts({ result, sweep }).every(chart => chart.qualityLabel === result.quality_label));
  assert.ok(regressionCharts({ result: { ...result, quality_label: null }, sweep }).every(chart => chart.qualityLabel === '仅可做半定量'));
  assert.ok(regressionCharts({ result: { ...result, quality_label: null, semi_quantitative: false, metrics: { rpd: .1 } }, sweep })
    .every(chart => chart.qualityLabel === null));
});

test('loading has visible messages and a result can render while its curve is still loading', () => {
  assert.ok(regressionCharts({ loading: true }).every(chart => chart.status === 'loading' && chart.message));
  const partial = regressionCharts({ result, loading: true });
  assert.equal(partial[0].status, 'loading'); assert.ok(partial.slice(1).every(chart => chart.status === 'ready'));
});

test('error descriptions handle structured native errors and opaque values without secondary throws', () => {
  assert.equal(failureMessage(new Error('offline')), 'offline');
  assert.equal(failureMessage({ error: 'ARTIFACT_NOT_FOUND' }), 'ARTIFACT_NOT_FOUND');
  assert.equal(failureMessage({ detail: '产物缺失' }), '产物缺失');
  assert.equal(failureMessage(undefined), '请求失败，请重试');
  const cyclic: { self?: unknown } = {}; cyclic.self = cyclic;
  assert.equal(failureMessage(cyclic), '请求失败，请重试');
  assert.notEqual(SERIES[0].color, SERIES[1].color);
});
