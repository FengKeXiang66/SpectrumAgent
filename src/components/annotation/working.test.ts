import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { candidateKey, editThenRead, estimateRemaining, orderedLabels, readWorking, recoverSelection, selectedCandidate, similarColors, workingView } from './working.ts';
import { boxFromPoints, fitViewport, freehandGeometry, imagePoint, rectangle, zoomAt } from './canvas/viewport.ts';
import type { Candidate, Label, LabelSchema, Statistics, Working } from './types.ts';

const png = { width: 1, height: 1, png_base64: 'fixture' };
const candidate = (id: number): Candidate => ({ superpixels: [id], pixel_count: 1, seed_superpixels: [id], min_similarity: .9, avg_similarity: .95, cos_s: [1], overlay: png });
const stats: Statistics = { n_pixels: 100, labeled_pixels: 20, uncertain_pixels: 10, blank_pixels: 70,
  labeled_percent: 20, uncertain_percent: 10, blank_percent: 70, label_counts: { '0': 20 }, pending_pixels: 2, dominant_label_id: 'a' };
const working = (queue: Candidate[] = []): Working => ({ project_id: 'from-server', params: null, superpixel_count: 2, queue, statistics: stats, overlay: png });

test('each edit reads working again; write-response pixels, queue and statistics are never reconstructed', async () => {
  const authoritative = working([candidate(2)]), calls: string[] = [];
  const api = { working: async (id: string) => { calls.push(`working:${id}`); return authoritative; } };
  const view = await editThenRead(api, 'cube', async () => { calls.push('regions'); return { queue: [], statistics: { labeled_pixels: 999 } }; });
  assert.deepEqual(calls, ['regions', 'working:cube']);
  assert.equal(view.queue, authoritative.queue);
  assert.equal(view.statistics.labeled_pixels, 20);
  const runtime = { ...authoritative, label_map: new Int32Array([0, -2]), undo_stack: [1] };
  const projection = workingView(runtime);
  assert.ok(!('label_map' in projection) && !('undo_stack' in projection));
});
test('switching cubes and recovering after confirm use only GET working, never diffuse', async () => {
  const server = { a: working([candidate(1), candidate(2)]), b: working([]) }, calls: string[] = [];
  const api = { working: async (id: string) => { calls.push(id); return server[id as keyof typeof server]; } };
  const before = await readWorking(api, 'a');
  const key = candidateKey(before.queue[1]);
  assert.equal(recoverSelection(before, key), key);
  assert.deepEqual((await readWorking(api, 'b')).queue, []);
  server.a = working([candidate(2)]); // Sidecar confirms/removes first candidate.
  const recovered = await readWorking(api, 'a');
  assert.equal(recovered.queue.length, 1);
  assert.equal(selectedCandidate(recovered, key)?.superpixels[0], 2);
  assert.equal(recoverSelection(working([]), key), null);
  assert.deepEqual(calls, ['a', 'b', 'a']);
});
test('a failed edit propagates its envelope and cannot manufacture a successful redraw', async () => {
  let reads = 0;
  const envelope = { error: 'SEGMENTATION_STALE', detail: '先重新生成', context: {} };
  await assert.rejects(editThenRead({ working: async () => { reads++; return working(); } }, 'a', async () => { throw envelope; }), value => value === envelope);
  assert.equal(reads, 0);
});
test('R17 label indexes use sort_order plus SQLite BINARY code order, independent of tree grouping', () => {
  const make = (code: string, sort_order: number) => ({ id: code, code, sort_order }) as Label;
  const tree = [{ labels: [make('Z', 2), make('PE', 1), make('😀', 2)] }, { labels: [make('BG', 0), make('\ue000', 2), make('A', 2)] }] as LabelSchema[];
  assert.deepEqual(orderedLabels(tree).map(label => label.code), ['BG', 'PE', 'A', 'Z', '\ue000', '😀']);
});
test('local remaining-time estimate derives only from confirmation speed and handles no progress', () => {
  assert.equal(estimateRemaining(1000, 20, stats, 2000), null);
  assert.equal(estimateRemaining(1000, 0, stats, 2000), 4);
  assert.equal(estimateRemaining(2000, 0, stats, 1000), null);
  assert.equal(estimateRemaining(1000, 0, null, 2000), null);
});
test('catalog color proximity uses backend colors and the task-card <30 rule', () => {
  const labels = [{ code: 'PP', color_hex: '#2f7fb0' }, { code: 'PE', color_hex: '#5aa469' }] as Label[];
  assert.deepEqual(similarColors('#3488b2', labels).map(label => label.code), ['PP']);
});
test('viewport transforms preserve [line,sample], bounds, zoom anchors and half-open boxes', () => {
  const view = fitViewport(400, 200, 100, 200);
  assert.deepEqual(imagePoint(20, 10, view, 100, 200), [5, 10]);
  assert.equal(imagePoint(400, 200, view, 100, 200), null);
  assert.equal(imagePoint(-1, 0, view, 100, 200), null);
  assert.deepEqual(imagePoint(20, 10, zoomAt(view, 20, 10, 2), 100, 200), [5, 10]);
  assert.deepEqual(boxFromPoints([3, 8], [1, 4]), [1, 4, 4, 9]);
  assert.deepEqual(rectangle([0, 0], [0, 0]), [[0, 0], [0, 1], [1, 1], [1, 0]]);
  assert.deepEqual(freehandGeometry([[0, 0], [1, 0], [1, 1]]), { polygon: [[0, 0], [1, 0], [1, 1]] });
  assert.deepEqual(freehandGeometry([[0, 0]]), { polygon: rectangle([0, 0], [0, 0]) });
  assert.equal(freehandGeometry([[0, 0], [1, 1]]), null);
});
test('component wiring has no local label map or undo history and preserves the outer conversation bar', () => {
  const source = readFileSync(new URL('./AnnotationWorkbench.tsx', import.meta.url), 'utf8');
  const queue = readFileSync(new URL('./CandidateQueue.tsx', import.meta.url), 'utf8');
  const canvas = readFileSync(new URL('./canvas/AnnotationCanvas.tsx', import.meta.url), 'utf8');
  const labelPanel = readFileSync(new URL('./LabelPanel.tsx', import.meta.url), 'utf8');
  for (const component of [source, queue, canvas, labelPanel]) {
    assert.doesNotMatch(component, /\binvoke\s*\(/);
    assert.doesNotMatch(component, /\bsetLabelMap\b|\bsetUndoStack\b|\bsetQueue\b/);
  }
  assert.match(source, /editThenRead\(api, id, operation\)/);
  assert.match(source, /projectId=\{working\.project_id\}/);
  assert.match(queue, /working\?\.queue\.map/);
  assert.match(canvas, /working\?\.queue\.filter/);
  assert.match(source, /api\.undo\(id\)/);
  assert.match(source, /api\.versionOverlay\(id, version\.id\)/);
  assert.doesNotMatch(readFileSync(new URL('./annotation.css', import.meta.url), 'utf8'), /position:\s*fixed/);
  const app = readFileSync(new URL('../../App.tsx', import.meta.url), 'utf8');
  assert.match(app, /<footer aria-label="常驻对话条">/);
});
