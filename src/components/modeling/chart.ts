// Pure chart preparation. Recommendations and quality labels come from artifacts.
export type Split = 'calibration' | 'prediction';
export type Point = { x: number; y: number };
export type Domain = { low: number; high: number };
export const FRAME = { width: 900, height: 520, left: 90, right: 870, top: 55, bottom: 435 } as const;
export const SERIES = [
  { set: 'calibration', label: '校准', color: '#2563a6' },
  { set: 'prediction', label: '预测', color: '#c24c19' },
] as const;
type Tick = { at: number; label: string };
type Line = { points: Point[]; color: string; dashed?: boolean };
export type ChartModel = {
  kind: 'curve' | 'scatter' | 'residual' | 'histogram' | 'coefficient'; title: string;
  status: 'ready' | 'empty' | 'unavailable' | 'loading'; message: string;
  xLabel: string; yLabel: string; xTicks: Tick[]; yTicks: Tick[]; notes: string[];
  qualityLabel: string | null; definition: string | null; legend: { label: string; color: string }[];
  lines: Line[]; points: (Point & { set: Split; square: boolean })[];
  bars: { x: number; y: number; width: number; height: number; set: Split }[];
  markers: (Point & { lv: number; label: string; color: string })[];
};
export type ChartInput = { result?: unknown; sweep?: unknown; runError?: string; sweepError?: string; loading?: boolean };
const finite = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);
const object = (value: unknown): Record<string, unknown> | null =>
  value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : null;
const split = (value: unknown): value is Split => value === 'calibration' || value === 'prediction';

export function extent(values: readonly unknown[]): Domain | null {
  let low = Infinity, high = -Infinity;
  for (const value of values) if (finite(value)) { low = Math.min(low, value); high = Math.max(high, value); }
  return finite(low) && finite(high) ? { low, high } : null;
}

export function mapValue(value: number, domain: Domain, start: number, end: number): number | null {
  if (![value, domain.low, domain.high, start, end].every(finite) || domain.low > domain.high) return null;
  if (domain.low === domain.high) return start / 2 + end / 2;
  const span = domain.high - domain.low;
  const ratio = finite(span) ? (value - domain.low) / span
    : (value / 2 - domain.low / 2) / (domain.high / 2 - domain.low / 2);
  const mapped = start + ratio * (end - start);
  return finite(mapped) ? mapped : null;
}

export function niceTicks(domain: Domain, target = 5, integers = false): number[] {
  if (![domain.low, domain.high, target].every(finite) || domain.low > domain.high || target < 1) return [];
  if (domain.low === domain.high) return [domain.low];
  const raw = (domain.high - domain.low) / target, power = 10 ** Math.floor(Math.log10(raw));
  if (!finite(raw) || power === 0) return [domain.low, domain.high];
  const fraction = raw / power;
  let step = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10) * power;
  if (integers) step = Math.max(1, step);
  const ticks: number[] = [];
  for (let i = 0, first = Math.ceil(domain.low / step) * step; i < 100; i++) {
    const value = first + i * step;
    if (value > domain.high + step * 1e-10) break;
    ticks.push(Math.abs(value) < step * 1e-10 ? 0 : Number(value.toPrecision(12)));
  }
  return [...new Set(ticks.length ? ticks : [domain.low, domain.high])];
}

export function splitRuns<T>(items: readonly T[], project: (item: T) => Point | null): Point[][] {
  const runs: Point[][] = []; let current: Point[] = [];
  for (const item of items) {
    const point = project(item);
    if (point && finite(point.x) && finite(point.y)) current.push(point);
    else if (current.length) { runs.push(current); current = []; }
  }
  if (current.length) runs.push(current);
  return runs;
}

export type Bin = { low: number; high: number; calibration: number; prediction: number };
export function histogram(values: readonly { value: number; set: Split }[]): Bin[] {
  const valid = values.filter(row => finite(row.value) && split(row.set)), domain = extent(valid.map(row => row.value));
  if (!domain) return [];
  const count = Math.min(20, Math.ceil(Math.sqrt(valid.length)));
  const low = Math.floor(domain.low);
  let high = Math.ceil(domain.high);
  if (low === high) high = low + Math.max(1, Math.abs(low) * .05);
  const width = (high - low) / count;
  if (!finite(width) || width <= 0) return [];
  // Outer edges floor/ceil to integers; equal-width inner edges round to 12 significant digits.
  const edge = (i: number) => i === 0 ? low : i === count ? high : Number((low + i * width).toPrecision(12));
  const bins = Array.from({ length: count }, (_, i) => ({ low: edge(i), high: edge(i + 1), calibration: 0, prediction: 0 }));
  for (const row of valid) {
    // Left closed, right open; the last bin also includes its right edge.
    const found = bins.findIndex(bin => row.value < bin.high);
    const index = found < 0 ? count - 1 : found;
    bins[index][row.set]++;
  }
  return bins;
}

export function failureMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  const row = object(error);
  for (const key of ['detail', 'error', 'message']) if (typeof row?.[key] === 'string' && row[key]) return row[key] as string;
  return '请求失败，请重试';
}

function empty(kind: ChartModel['kind'], title: string, message: string, status: ChartModel['status'] = 'empty'): ChartModel {
  return { kind, title, status, message, xLabel: '', yLabel: '', xTicks: [], yTicks: [], notes: [],
    qualityLabel: null, definition: null, legend: [], lines: [], points: [], bars: [], markers: [] };
}
function axes(model: ChartModel, x: Domain, y: Domain, xLabel: string, yLabel: string, integerX = false, integerY = false) {
  model.status = 'ready'; model.message = ''; model.xLabel = xLabel; model.yLabel = yLabel;
  model.xTicks = niceTicks(x, 5, integerX).map(value => ({ at: mapValue(value, x, FRAME.left, FRAME.right)!, label: String(value) }));
  model.yTicks = niceTicks(y, 5, integerY).map(value => ({ at: mapValue(value, y, FRAME.bottom, FRAME.top)!, label: String(value) }));
}
function mapped(x: number, y: number, xd: Domain, yd: Domain): Point | null {
  const a = mapValue(x, xd, FRAME.left, FRAME.right), b = mapValue(y, yd, FRAME.bottom, FRAME.top);
  return a === null || b === null ? null : { x: a, y: b };
}

function curveChart(input: ChartInput): ChartModel {
  const model = empty('curve', 'RMSECV 与潜变量数', '无可用曲线数据');
  if (input.runError || input.sweepError) return { ...model, status: 'unavailable', message: '无法获取潜变量曲线：' + (input.runError || input.sweepError) };
  if (input.loading && !input.sweep) return { ...model, status: 'loading', message: '正在获取潜变量曲线…' };
  const sweep = object(input.sweep);
  if (!sweep || !Array.isArray(sweep.curve)) return { ...model, status: 'unavailable', message: '无法获取潜变量曲线：未提供曲线产物。' };
  const rows = sweep.curve.map(object);
  const valid = rows.filter((row): row is Record<string, number> =>
    !!row && finite(row.n_components) && row.n_components >= 1 && finite(row.rmsecv) && row.rmsecv >= 0 && finite(row.sd) && row.sd >= 0);
  if (!valid.length) return model;
  const xd = extent(valid.map(row => row.n_components))!;
  const yd = extent([0, ...valid.map(row => row.rmsecv + row.sd)])!;
  axes(model, xd, yd, '潜变量数 LV', 'RMSECV', true);
  const project = (row: Record<string, unknown> | null) =>
    row && valid.includes(row as Record<string, number>) ? mapped(row.n_components as number, row.rmsecv as number, xd, yd) : null;
  model.lines = splitRuns(rows, project).map(points => ({ points, color: '#26374b' }));
  for (const row of valid) {
    const lo = mapped(row.n_components, Math.max(0, row.rmsecv - row.sd), xd, yd);
    const hi = mapped(row.n_components, row.rmsecv + row.sd, xd, yd);
    if (lo && hi) model.lines.push({ points: [lo, hi], color: '#b0bdcc' });
  }
  // Use saved LV fields verbatim, even when they differ from a front-end recomputation.
  for (const [key, label, color] of [
    ['best_lv', '交叉验证最小 LV', '#2563a6'], ['elbow_lv', '拐点建议 LV', '#b46a09'],
    ['selected_lv', sweep.manual_override === true ? '手动 LV' : '采用 LV', '#7846ad'],
  ]) {
    const lv = sweep[key], row = valid.find(point => point.n_components === lv);
    const point = row ? project(row) : null;
    if (finite(lv) && point) {
      model.markers.push({ ...point, lv, label, color });
      model.legend.push({ label: label + '：' + lv, color });
    } else model.notes.push('无法获取' + label + '标记：产物字段或对应点缺失。');
  }
  if (typeof sweep.definition === 'string' && sweep.definition) {
    model.definition = sweep.definition;
    model.notes.push('拐点建议采用产物值：首个进入最小 RMSECV 加该点折间标准差范围的最小 LV。');
  } else model.notes.push('无法获取曲线定义。');
  if (typeof sweep.manual_override !== 'boolean') model.notes.push('无法获取手动 LV 状态。');
  if (valid.length < rows.length) model.notes.push('非有限或缺失的曲线点已断线显示。');
  return model;
}

function predictionCharts(input: ChartInput): ChartModel[] {
  const charts = [
    empty('scatter', '实测与预测含量', '无可用预测数据'),
    empty('residual', '预测残差', '无可用残差数据'),
    empty('histogram', '预测含量分布', '无可用预测数据'),
  ];
  const result = object(input.result);
  const unavailable = input.runError ? '无法获取评价数据：' + input.runError
    : !result || !Array.isArray(result.predictions) ? '无法获取预测数据：该记录未提供样品预测结果。' : '';
  if (input.loading && !result && !input.runError) return charts.map(chart => ({ ...chart, status: 'loading', message: '正在获取评价数据…' }));
  if (unavailable) return charts.map(chart => ({ ...chart, status: 'unavailable', message: unavailable }));
  const rows = (result!.predictions as unknown[]).map(object);
  if (!rows.length) return charts;
  const pointsFor = (key: 'y_true' | 'y_pred', value: 'y_pred' | 'residual') =>
    rows.flatMap(row => row && split(row.set) && finite(row[key]) && finite(row[value])
      ? [{ x: row[key], y: row[value], set: row.set }] : []);
  const scatter = pointsFor('y_true', 'y_pred'), residual = pointsFor('y_pred', 'residual');
  for (const [index, points, xLabel, yLabel] of [
    [0, scatter, '实测含量', '预测含量'], [1, residual, '预测含量', '残差（预测－实测）'],
  ] as const) {
    const chart = charts[index];
    if (!points.length) { chart.status = 'unavailable'; chart.message = '无法获取' + chart.title + '：缺少有限数据字段。'; continue; }
    const xd = extent(points.map(point => point.x))!, yd = extent([...points.map(point => point.y), ...(index === 1 ? [0] : [])])!;
    axes(chart, xd, yd, xLabel, yLabel);
    chart.points = points.flatMap(point => {
      const value = mapped(point.x, point.y, xd, yd);
      return value ? [{ ...value, set: point.set, square: points.length === 1 }] : [];
    });
    chart.legend = SERIES.map(series => ({ label: series.label + '（' + points.filter(point => point.set === series.set).length + '）', color: series.color }));
    if (index === 1) {
      const y = mapValue(0, yd, FRAME.bottom, FRAME.top)!;
      chart.lines.push({ points: [{ x: FRAME.left, y }, { x: FRAME.right, y }], color: '#6b7785', dashed: true });
    } else {
      const low = Math.max(xd.low, yd.low), high = Math.min(xd.high, yd.high);
      if (low <= high) chart.lines.push({ points: [mapped(low, low, xd, yd)!, mapped(high, high, xd, yd)!], color: '#6b7785', dashed: true });
      if (xd.low === xd.high) chart.notes.push('参考值无变化');
      chart.notes.push('虚线为实测值等于预测值的参考线。');
    }
    if (points.length < rows.length) chart.notes.push('缺失、非有限或集合未知的记录已排除。');
  }
  const values = rows.flatMap(row => row && split(row.set) && finite(row.y_pred) ? [{ value: row.y_pred, set: row.set }] : []);
  const bins = histogram(values), chart = charts[2];
  if (!bins.length) { chart.status = 'unavailable'; chart.message = '无法获取预测含量分布：缺少有限预测值。'; return charts; }
  const xd = { low: bins[0].low, high: bins.at(-1)!.high };
  const yd = { low: 0, high: Math.max(...bins.flatMap(bin => [bin.calibration, bin.prediction])) };
  axes(chart, xd, yd, '预测含量', '样品数', false, true);
  for (const bin of bins) {
    const left = mapValue(bin.low, xd, FRAME.left, FRAME.right)!, right = mapValue(bin.high, xd, FRAME.left, FRAME.right)!;
    const width = (right - left) / 2;
    for (const [i, series] of SERIES.entries()) {
      const y = mapValue(bin[series.set], yd, FRAME.bottom, FRAME.top)!;
      chart.bars.push({ x: left + i * width + 1, y, width: Math.max(0, width - 2), height: FRAME.bottom - y, set: series.set });
    }
  }
  chart.legend = SERIES.map(series => ({ label: series.label + '（' + values.filter(row => row.set === series.set).length + '）', color: series.color }));
  chart.notes.push('等宽直方图 · ' + bins.length + ' 箱；两组共用边界，末箱含右端点。');
  return charts;
}

export function regressionCharts(input: ChartInput): ChartModel[] {
  const result = object(input.result);
  const label = typeof result?.quality_label === 'string' && result.quality_label ? result.quality_label
    : result?.semi_quantitative === true ? '仅可做半定量' : null;
  return [curveChart(input), ...predictionCharts(input)].map(chart => ({ ...chart, qualityLabel: label }));
}

export type CoefficientInput = { result?: unknown; loading?: boolean; error?: unknown; qualityLabel?: string | null };
export function coefficientChart(input: CoefficientInput): ChartModel[] {
  const row = object(input.result);
  const model = empty('coefficient', '波段回归系数', '无可用系数数据');
  model.qualityLabel = typeof row?.quality_label === 'string' && row.quality_label ? row.quality_label : input.qualityLabel ?? null;
  model.notes = ['虚线为零值参考线；系数符号反映该波段对预测值的贡献方向。'];
  const unavailable = (message: string) => [{ ...model, status: 'unavailable' as const, message }];
  if (input.error) return unavailable('无法获取波段系数：' + failureMessage(input.error));
  if (input.loading) return [{ ...model, status: 'loading', message: '正在获取波段系数…' }];
  if (!row) return unavailable('无法获取波段系数：未提供系数产物。');
  if (typeof row.name === 'string' && finite(row.version)) model.title = row.name + ' · v' + row.version + ' 波段系数';
  const k = row.n_features, n = row.n_wavelengths, coefs = row.coefficients, waves = row.wavelengths;
  if (!finite(k) || !Number.isInteger(k) || k < 0 || !finite(n) || !Number.isInteger(n) || n < 0
      || typeof row.comparable !== 'boolean') return unavailable('无法获取波段系数：特征或波长计数无效。');
  const alternative = '可结合域外适用性图及模型评价图判断模型行为。';
  if (n === 0) {
    model.notes.push(alternative);
    return unavailable('该模型未记录波长轴（数据集波长未知），无法按波长绘制系数。');
  }
  if (k !== n) {
    model.notes.push(alternative);
    return unavailable('该模型特征数 ' + k + ' 与波长数 ' + n + ' 不一致（预处理改变了波段维度），无法按波长绘制系数。');
  }
  if (!row.comparable) {
    model.notes.push(alternative);
    return unavailable('该模型预处理包含不保留逐波段对应的算子，特征与波长不再逐点对应，本图不绘制。');
  }
  model.notes.push('系数对应该模型训练所用预处理后的 ' + k + ' 个特征，与 ' + n + ' 个输入波段一一对应。');
  if (!Array.isArray(coefs) || !Array.isArray(waves)) return unavailable('无法获取波段系数：缺少系数或波长数组。');
  if (coefs.length === 0) return [model];
  if (coefs.length !== k || waves.length !== n || !coefs.every(finite) || !waves.every(finite)) {
    return unavailable('无法获取波段系数：数组形状或有限数值校验失败。');
  }
  const xd = extent(waves)!, yd = extent([0, ...coefs])!;
  model.status = 'ready'; model.message = ''; model.xLabel = '波长'; model.yLabel = '回归系数';
  model.xTicks = niceTicks(xd, 6).map(value => ({ at: mapValue(value, xd, FRAME.left, FRAME.right)!, label: String(value) }));
  model.yTicks = niceTicks(yd, 5).map(value => ({ at: mapValue(value, yd, FRAME.bottom, FRAME.top)!, label: String(value) }));
  const zero = mapValue(0, yd, FRAME.bottom, FRAME.top)!;
  model.lines.push({ points: [{ x: FRAME.left, y: zero }, { x: FRAME.right, y: zero }], color: '#a4b2c1', dashed: true });
  const points = coefs.map((coef, i) => mapped(waves[i], coef, xd, yd)!);
  if (points.length === 1) model.points = [{ ...points[0], set: 'calibration', square: true }];
  else model.lines.push({ points, color: SERIES[0].color });
  model.legend = [{ label: '回归系数', color: SERIES[0].color }, { label: '零值参考线', color: '#a4b2c1' }];
  if (waves.some((value, i) => i > 0 && value <= waves[i - 1])) model.notes.push('按产物波长顺序绘制');
  if (finite(row.selected_lv) && Number.isInteger(row.selected_lv) && row.selected_lv > 0) model.definition = '采用 LV：' + row.selected_lv;
  return [model];
}
