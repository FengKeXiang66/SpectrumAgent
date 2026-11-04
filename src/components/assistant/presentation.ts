import type { DatasetReference } from '../datasets/types.ts';
import { displayName } from '../datasets/types.ts';
import type { AgentEvent, ChatEntry } from './sse.ts';
import type { WorkspaceContext } from './api.ts';
import type { Working } from '../annotation/types.ts';
import { candidateKey } from '../annotation/working.ts';

export type DatasetChoice = { id: string; label: string; index: number };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const uuidInText = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/gi;

export function datasetChoices(entries: ChatEntry[], records: DatasetReference[]): DatasetChoice[] {
  const listing = [...entries].reverse().find(entry => entry.event === 'step' && entry.data.tool === 'datasets.list' && entry.data.status === 'ok');
  if (!listing || listing.event !== 'step') return [];
  const summary = listing.data.result_summary;
  const indexed = Object.keys(summary).flatMap(key => {
    const match = /^dataset_(\d+)_id$/.exec(key);
    const id = summary[key];
    return match && typeof id === 'string' && uuid.test(id) ? [{ id, index: Number(match[1]) }] : [];
  }).sort((left, right) => left.index - right.index);
  if (indexed.length) return indexed.map(({ id, index }) => ({ id, index,
    label: records.filter(record => record.id === id).map(displayName)[0]
      || (typeof summary[`dataset_${index}_name`] === 'string' ? String(summary[`dataset_${index}_name`]) : `数据集 ${index}`) }));
  const ids = typeof summary.dataset_ids === 'string' ? summary.dataset_ids.split(',').map(value => value.trim()).filter(value => uuid.test(value)) : [];
  return [...new Set(ids)].map((id, index) => ({ id, index: index + 1,
    label: records.filter(record => record.id === id).map(displayName)[0] || `数据集 ${index + 1}` }));
}

export function readableText(text: string, choices: DatasetChoice[], records: DatasetReference[]): string {
  // Keep references accurate while avoiding UUID tables in ordinary replies.
  return text.replace(uuidInText, id => {
    const choice = choices.find(item => item.id.toLowerCase() === id.toLowerCase());
    const record = records.find(item => item.id.toLowerCase() === id.toLowerCase());
    return choice ? `${choice.index}号 ${choice.label}（${id.slice(0, 8)}）`
      : record ? `${displayName(record)}（${id.slice(0, 8)}）` : `引用 ${id.slice(0, 8)}`;
  });
}

export function changedCubes(events: AgentEvent[], workspace: WorkspaceContext = {}): string[] {
  const cubes = events.flatMap(event => {
    if (event.event !== 'step' || event.data.status !== 'ok' || !/^(annotations\.|preprocess\.)/.test(event.data.tool)) return [];
    const cube = event.data.result_summary.cube_id ?? workspace.cube_id;
    return typeof cube === 'string' && uuid.test(cube) ? [cube] : [];
  });
  return [...new Set(cubes)];
}

export function selectWorkspace(current: WorkspaceContext, next: WorkspaceContext): WorkspaceContext {
  // A gesture belongs to one cube. Switching selection never carries it over.
  if (next.cube_id !== current.cube_id) return { ...(next.cube_id ? { cube_id: next.cube_id } : {}),
    ...(next.gesture_ref ? { gesture_ref: next.gesture_ref } : {}) };
  return { ...current, ...next };
}

export function proposedCandidates(events: AgentEvent[]): { cube_id: string; candidate_ref: string }[] {
  return events.flatMap(event => {
    if (event.event !== 'step' || event.data.tool !== 'annotations.propose' || event.data.status !== 'ok') return [];
    const { cube_id, candidate_ref, status } = event.data.result_summary;
    return status === 'preview' && typeof cube_id === 'string' && uuid.test(cube_id)
      && typeof candidate_ref === 'string' && /^c-[0-9a-f]{32}$/.test(candidate_ref) ? [{ cube_id, candidate_ref }] : [];
  });
}

export function candidatePreviewKey(working: Working | null, reference: string): string | null {
  const candidate = working?.queue.find(item => item.candidate_ref === reference);
  return candidate ? candidateKey(candidate) : null;
}
