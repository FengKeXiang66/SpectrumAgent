import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Children, createElement, isValidElement, type ReactElement, type ReactNode } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import ts from 'typescript';
import { eraseAndRefresh, formatReviewCos, formatReviewNumber, reviewBandTitle, reviewKey, reviewLegend,
  reviewModel, reviewRuns, reviewX, sharedReviewRange, sortReviewComparisons } from './spectrumReview.ts';
import { editThenRead } from './working.ts';
import type { Comparison, Label, Quality, Working } from './types.ts';

const labels: Label[] = ['PE', 'PET'].map((code, index) => ({
  id: code, code, name: code, color_hex: ['#126688', '#a05224'][index], project_id: 'p',
  schema_id: 's', tree_path: code, shortcut_key: null, sort_order: index, is_background: 0, created_at: '',
}));
const item = (id: number, label: number, cos: number | null, mean: (number | null)[]): Comparison =>
  ({ superpixel_id: id, label_index: label, cos, mean, pixel_count: 8 });
function report(): Quality {
  return {
    threshold: .8, threshold_level: 'test', reference: '当前原谱', suspicious: [],
    comparisons: [item(8, 0, .95, [10, 15, 20]), item(3, 1, .2, [0, .5, 1]), item(9, 0, null, [10, null, 20])],
    references: [{ label_index: 0, mean: [10, 15, 20] }, { label_index: 1, mean: [0, .5, 1] }],
    high_variance: { d_s: [null], tau: null, superpixel_ids: [] }, not_applicable: {},
    completeness: { n_pixels: 24, labeled_pixels: 24, uncertain_pixels: 0, blank_pixels: 0,
      labeled_percent: 100, uncertain_percent: 0, blank_percent: 0, label_counts: { PE: 16, PET: 8 },
      pending_pixels: 0, dominant_label_id: 'PE' },
  };
}

test('review sorting is stable, ascending and null-last without changing backend order', () => {
  const input = report().comparisons;
  const before = structuredClone(input);
  assert.deepEqual(sortReviewComparisons(input).map(reviewKey), ['3:1', '8:0', '9:0']);
  assert.deepEqual(input, before);
  const equal = [item(7, 0, .2, []), item(1, 0, .2, []), item(2, 0, NaN, []), item(3, 0, Infinity, [])];
  assert.deepEqual(sortReviewComparisons(equal).map(reviewKey), ['7:0', '1:0', '2:0', '3:0']);
});

test('all curves and references use one finite y range, including constant and empty inputs', () => {
  const quality = report();
  quality.references[0].mean = [-5, 15, 25];
  const model = reviewModel(quality, labels, 3);
  assert.deepEqual(model.range, [-5, 25]);
  assert.deepEqual(model.curves.find(curve => curve.key === '3:1')!.runs[0], [[0, 25 / 30], [.5, 24.5 / 30], [1, 24 / 30]]);
  assert.deepEqual(reviewRuns([5, 5], [5, 5], 2), [[[0, .5], [1, .5]]]);
  assert.equal(sharedReviewRange([[null, NaN, Infinity, -Infinity], []]), null);
  assert.deepEqual(sharedReviewRange([[0, 1], [-2, 3]]), [-2, 3]);
});

test('band-index x ignores nonlinear or descending wavelengths; hover preserves wavelength metadata', () => {
  assert.deepEqual([0, 1, 2].map(index => reviewX(index, 3)), [0, .5, 1]);
  const model = reviewModel(report(), labels, 3);
  assert.deepEqual(model.curves.find(curve => curve.key === '8:0')!.runs[0].map(point => point[0]), [0, .5, 1]);
  assert.equal(reviewBandTitle(1, [1000, 401, 400]), 'band 1 · 波长 401');
  assert.equal(reviewBandTitle(1, []), 'band 1');
  assert.equal(reviewX(0, 1), .5);
});

test('curveRuns wrapper splits every null/nonfinite gap and retains single finite points', () => {
  assert.deepEqual(reviewRuns([1, null, 3, 4, NaN, null, 7], [1, 7], 7),
    [[[0, 1]], [[2 / 6, 4 / 6], [3 / 6, 3 / 6]], [[1, 0]]]);
  assert.deepEqual(reviewRuns([null, Infinity], [0, 1], 2), []);
});

test('label colors come from color_hex and references share their class color', () => {
  const model = reviewModel(report(), labels, 3);
  for (const curve of model.curves) assert.equal(curve.color, labels[curve.label_index].color_hex);
  assert.deepEqual(reviewLegend(7, labels), { code: 'label_index 7', color: '#61717e' });
  assert.deepEqual(model.groups.map(group => [group.code, group.count]), [['PE', 2], ['PET', 1]]);
});

test('null cos and tau display explicit fallbacks while finite zero stays numeric', () => {
  assert.equal(formatReviewCos(null), '余弦无法定义');
  assert.equal(formatReviewNumber(null), '—');
  assert.equal(formatReviewNumber(NaN), '—');
  assert.equal(formatReviewCos(0), '0.000000');
  assert.equal(formatReviewNumber(0), '0');
  assert.equal(formatReviewCos(.12345678), '0.123457');
});

type Element = ReactElement<Record<string, unknown>>;
function elements(tree: ReactNode): Element[] {
  const found: Element[] = [];
  function visit(value: ReactNode) {
    if (!isValidElement<Record<string, unknown>>(value)) return;
    found.push(value);
    Children.forEach(value.props.children as ReactNode, visit);
  }
  visit(tree);
  return found;
}

function compile(source: string, url: URL): string {
  return ts.transpileModule(source, { compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext } }).outputText
    .replace(/from (['"])(\.[^'"]+)\1/g, (_match, _quote, path: string) => 'from ' + JSON.stringify(new URL(path, url).href))
    .replace(/(['"])(react(?:\/jsx-runtime)?|@tauri-apps\/api\/core)\1/g,
      (_match, _quote, name: string) => JSON.stringify(import.meta.resolve(name)));
}

let harnessId = 0;
async function harness(quality: Quality | null = report(), disabled = false, onErase?: (block: number) => void) {
  const key = '__spectrum_review_test_' + harnessId++;
  const scope = globalThis as unknown as Record<string, unknown>;
  const states: unknown[] = [];
  let cursor = 0, refreshed = 0;
  const erased: number[] = [];
  scope[key] = {
    useState(initial: unknown) {
      const index = cursor++;
      if (!(index in states)) states[index] = initial;
      return [states[index], (next: unknown) => {
        states[index] = typeof next === 'function' ? (next as (previous: unknown) => unknown)(states[index]) : next;
      }];
    },
  };
  const url = new URL('./SpectrumReview.tsx', import.meta.url);
  const source = readFileSync(url, 'utf8').replace(/^import \{ useState \} from 'react';\r?$/m,
    'const { useState } = globalThis[' + JSON.stringify(key) + '];');
  const module = await import('data:text/javascript;base64,' + Buffer.from(compile(source, url)).toString('base64'));
  const props = () => ({ quality, labels, bands: 3, wavelengths: [400, 401, 1000], disabled,
    onRefresh() { refreshed++; }, onBlockErase(block: number) { erased.push(block); onErase?.(block); } });
  const tree = (): ReactNode => { cursor = 0; return module.default(props()); };
  return { tree, html: () => renderToStaticMarkup(tree()), erased, refreshed: () => refreshed,
    setQuality(next: Quality | null) { quality = next; },
    close() { delete scope[key]; } };
}

test('rendered review defaults to grouped overlays, class references and wavelength hover', async () => {
  const h = await harness();
  try {
    const html = h.html();
    assert.match(html, /按标签分组叠加/);
    assert.match(html, /band index/);
    assert.match(html, /band 1 · 波长 401/);
    assert.equal(elements(h.tree()).filter(node => node.props['data-reference'] === true).length, 2);
    assert.equal(elements(h.tree()).filter(node => node.props['data-reference'] === false).length, 3);
    assert.match(html, /stroke="#126688"/);
    assert.match(html, /stroke-dasharray="6 4"/);
    assert.equal(h.refreshed(), 0);
    const refresh = elements(h.tree()).find(node => node.type === 'button' && node.props.children === '刷新谱线')!;
    (refresh.props.onClick as () => void)();
    assert.equal(h.refreshed(), 1);
    assert.deepEqual(h.erased, []);
  } finally { h.close(); }
});

test('rendered selection mode shows only checked blocks and matching class references', async () => {
  const quality = report(), before = structuredClone(quality);
  const h = await harness(quality);
  try {
    const select = elements(h.tree()).find(node => node.type === 'select')!;
    (select.props.onChange as (event: unknown) => void)({ target: { value: 'selected' } });
    assert.equal(elements(h.tree()).filter(node => node.props['data-curve']).length, 0);
    const checkbox = elements(h.tree()).find(node => node.type === 'input' && node.props['aria-label'] === '显示 #3 · PET')!;
    (checkbox.props.onChange as (event: unknown) => void)({ target: { checked: true } });
    assert.deepEqual(elements(h.tree()).filter(node => node.props['data-curve']).map(node => node.props['data-curve']), ['3:1', 'reference:1']);
    assert.deepEqual(quality, before);
  } finally { h.close(); }
});

test('erase requires the rendered button and busy state disables writes', async () => {
  for (const disabled of [false, true]) {
    const h = await harness(report(), disabled);
    try {
      assert.deepEqual(h.erased, []);
      const button = elements(h.tree()).find(node => node.props['aria-label'] === '剔除超像素 #3')!;
      assert.equal(button.props.disabled, disabled);
      if (!disabled) (button.props.onClick as () => void)();
      assert.deepEqual(h.erased, disabled ? [] : [3]);
    } finally { h.close(); }
  }
});

test('empty and all-null review states disclose no data without malformed paths', async () => {
  const h = await harness(null);
  try {
    assert.match(h.html(), /尚无复核结果/);
    const quality = report();
    quality.comparisons = []; quality.references = [];
    h.setQuality(quality);
    assert.match(h.html(), /暂无已确认的超像素/);
    quality.comparisons = [item(1, 0, null, [null, null, null])];
    quality.references = [{ label_index: 0, mean: [null, null, null] }];
    assert.match(h.html(), /无有限曲线数据/);
    assert.match(h.html(), /余弦无法定义/);
    assert.equal(elements(h.tree()).filter(node => node.type === 'path').length, 0);
  } finally { h.close(); }
});

test('erase reads authoritative working state then validates and publishes one refreshed quality object', async () => {
  const calls: string[] = [], initial = report(), updated = report();
  updated.comparisons = updated.comparisons.filter(row => row.superpixel_id !== 3);
  updated.references = updated.references.filter(row => row.label_index !== 1);
  updated.completeness = { ...updated.completeness, labeled_pixels: 16, blank_pixels: 8 };
  let quality: Quality | null = initial, working: Working | null = null;
  const authoritative: Working = { project_id: 'p', queue: [], superpixel_count: 10, params: null,
    statistics: updated.completeness, overlay: null, blocks: { label: [], purity: [], label_count: [] } };
  const api = { working: async () => { calls.push('working'); return authoritative; } };
  assert.equal(await eraseAndRefresh(3, async block => {
    quality = null;
    working = await editThenRead(api, 'cube', async () => { calls.push('erase:' + block); });
    quality = null;
    return true;
  }, async () => { calls.push('validate'); quality = updated; }), true);
  assert.deepEqual(calls, ['erase:3', 'working', 'validate']);
  assert.equal(quality, updated);
  assert.deepEqual(working, authoritative);
  const projection = working as Working | null;
  assert.ok(projection);
  assert.equal(projection.statistics, authoritative.statistics);
  assert.equal(projection.blocks, authoritative.blocks);
  assert.equal(updated.comparisons.length, initial.comparisons.length - 1);
  const h = await harness(quality);
  try { assert.match(h.html(), /已确认组合 2 条/); assert.equal(h.erased.length, 0); }
  finally { h.close(); }
});

test('failed erase cannot refresh or manufacture a successful review result', async () => {
  let refreshes = 0;
  assert.equal(await eraseAndRefresh(3, async () => false, async () => { refreshes++; }), false);
  const failure = new Error('edit failed');
  await assert.rejects(eraseAndRefresh(3, async () => { throw failure; }, async () => { refreshes++; }), error => error === failure);
  assert.equal(refreshes, 0);
});

test('actual workbench quality markup renders null cos and tau without throwing', async () => {
  const url = new URL('./AnnotationWorkbench.tsx', import.meta.url);
  const key = '__review_workbench_null_contract';
  const scope = globalThis as unknown as Record<string, unknown>;
  const quality = report();
  quality.suspicious = [quality.comparisons[2]]; // Defensive type-consumer injection, not real NaN spectra.
  scope[key] = quality;
  try {
    let source = readFileSync(url, 'utf8').replace('useState<Quality | null>(null)',
      'useState<Quality | null>(globalThis[' + JSON.stringify(key) + '])');
    for (const child of ['AnnotationCanvas', 'LabelPanel', 'CandidateQueue', 'SpectrumReview']) {
      source = source.replace(new RegExp('^import ' + child + '.*$', 'm'), 'const ' + child + ' = () => null;');
    }
    source = source.replace(/^import DisplayToolbar.*$/m, 'const DisplayToolbar = () => null, SpectrumReadout = () => null;')
      .replace(/^import '.*\.css';\r?$/gm, '');
    const module = await import('data:text/javascript;base64,' + Buffer.from(compile(source, url)).toString('base64'));
    const record = { id: 'cube', dataset: { name: 'tiny', header_path: '', shape: [1, 1, 3], wavelengths: [] } };
    const html = renderToStaticMarkup(createElement(module.default, { record, records: [record], datasets: {}, onNavigate() {}, onClose() {} }));
    assert.match(html, /cos 余弦无法定义/);
    assert.match(html, /τ=—/);
  } finally { delete scope[key]; }
});

test('actual review button completes the workbench edit, validate and shared-state refresh', async () => {
  const key = '__review_workbench_event_contract';
  const scope = globalThis as unknown as Record<string, unknown>;
  const initial = report(), updated = report(), calls: string[] = [];
  updated.comparisons = updated.comparisons.filter(item => item.superpixel_id !== 3);
  updated.references = updated.references.filter(item => item.label_index !== 1);
  updated.reference = 'refreshed-current-original';
  updated.completeness = { ...updated.completeness, labeled_pixels: 16, blank_pixels: 8,
    labeled_percent: 100 * 16 / 24, blank_percent: 100 * 8 / 24, label_counts: { PE: 16 } };
  const parameters = { n_segments: 200, compactness: .5, pca_components: 5, k: 3,
    block_size: 32, feature_version: 'test', pca_batch_size: 32 };
  const working: Working = { project_id: 'p', queue: [], superpixel_count: 10, params: parameters,
    statistics: initial.completeness, overlay: null, blocks: { label: [], purity: [], label_count: [] } };
  const nextWorking = { ...working, statistics: updated.completeness };
  const states: unknown[] = [];
  let cursor = 0;
  scope[key] = { working, quality: initial,
    useState(initialValue: unknown) {
      const index = cursor++;
      if (!(index in states)) states[index] = typeof initialValue === 'function' ? (initialValue as () => unknown)() : initialValue;
      return [states[index], (next: unknown) => {
        states[index] = typeof next === 'function' ? (next as (previous: unknown) => unknown)(states[index]) : next;
      }];
    },
    useRef(initialValue: unknown) {
      const index = cursor++;
      if (!(index in states)) states[index] = { current: initialValue };
      return states[index];
    },
    useEffect() {},
  };
  let view: Awaited<ReturnType<typeof harness>> | undefined;
  try {
    const url = new URL('./AnnotationWorkbench.tsx', import.meta.url);
    let source = readFileSync(url, 'utf8')
      .replace(/^import \{ useEffect, useRef, useState \} from 'react';\r?$/m,
        'const {useEffect,useRef,useState} = globalThis[' + JSON.stringify(key) + '];')
      .replace('useState<Working | null>(null)', 'useState<Working | null>(globalThis[' + JSON.stringify(key) + '].working)')
      .replace('useState<Quality | null>(null)', 'useState<Quality | null>(globalThis[' + JSON.stringify(key) + '].quality)')
      .replace(/useState\(\{ n_segments: \d+, compactness: \.5, pca_components: 5 \}\)/,
        'useState(globalThis[' + JSON.stringify(key) + '].working.params)')
      .replace("useState<'superpixels' | 'diffuse' | 'prompt' | 'review'>('superpixels')",
        "useState<'superpixels' | 'diffuse' | 'prompt' | 'review'>('review')")
      .replace('const [busy, setBusy] = useState(true)', 'const [busy, setBusy] = useState(false)')
      .replace('const [synchronized, setSynchronized] = useState(false)', 'const [synchronized, setSynchronized] = useState(true)')
      .replace('busyRef = useRef(true)', 'busyRef = useRef(false)');
    for (const child of ['AnnotationCanvas', 'LabelPanel', 'CandidateQueue', 'SpectrumReview']) {
      source = source.replace(new RegExp('^import ' + child + '.*$', 'm'), 'const ' + child + ' = () => null;');
    }
    source = source.replace(/^import DisplayToolbar.*$/m, 'const DisplayToolbar = () => null, SpectrumReadout = () => null;')
      .replace(/^import '.*\.css';\r?$/gm, '');
    const module = await import('data:text/javascript;base64,' + Buffer.from(compile(source, url)).toString('base64'));
    const record = { id: 'cube', dataset: { name: 'tiny', header_path: '', shape: [1, 1, 3], wavelengths: [] } };
    const api = {
      async regions(id: string, geometry: unknown, action: string, label: unknown) {
        assert.equal(id, 'cube'); assert.deepEqual(geometry, { superpixels: [3] });
        assert.equal(action, 'erase'); assert.equal(label, undefined); calls.push('erase:3');
        return nextWorking;
      },
      async working() { calls.push('working'); return nextWorking; },
      async validate() { calls.push('validate'); return updated; },
    };
    const tree = (): ReactNode => { cursor = 0; return module.default({ record, records: [record],
      datasets: {}, api, onNavigate() {}, onClose() {} }); };
    const review = () => elements(tree()).find(node => node.props.quality !== undefined && node.props.onBlockErase)!;
    assert.equal(review().props.quality, initial);
    view = await harness(initial, false, review().props.onBlockErase as (block: number) => void);
    const button = elements(view.tree()).find(node => node.props['aria-label'] === '剔除超像素 #3')!;
    assert.deepEqual(calls, []);
    (button.props.onClick as () => void)();
    assert.equal(review().props.quality, null);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(calls, ['erase:3', 'working', 'validate', 'working']);
    assert.equal(review().props.quality, updated);
    assert.match(renderToStaticMarkup(tree()), /refreshed-current-original/);
    assert.match(renderToStaticMarkup(tree()), /66.67%/);
    view.setQuality(review().props.quality as Quality);
    assert.match(view.html(), /已确认组合 2 条/);
    assert.equal(elements(view.tree()).filter(node => node.props['data-reference'] === true).length, 1);
  } finally { view?.close(); delete scope[key]; }
});

test('workbench wires manual entry and erase refresh into the same quality state', () => {
  const source = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  assert.match(source, /\['review', '谱线复核'\]/);
  assert.match(source, /value === 'review'\) \{ void refreshReview\(\)/);
  assert.match(source, /<SpectrumReview quality=\{quality\}/);
  assert.match(source, /reviewBlockErase = \(blockId: number\) => eraseAndRefresh\(blockId,[\s\S]*?edit\('erase', \{ superpixels: \[block\] \}\), refreshReview\)/);
  assert.match(source, /const result = await api.validate\(id\);[\s\S]*?setQuality\(result\)/);
  assert.match(source, /formatReviewCos\(item.cos\)/);
  assert.match(source, /formatReviewNumber\(quality.high_variance.tau\)/);
});
