import { invoke } from '@tauri-apps/api/core';
import type { AnnotationApi, AnnotationRequest, DiffuseOptions, EditAction, Geometry, LabelBody, SaveOptions, Seed, SuperpixelOptions } from './types.ts';

// Explicit projections: view-only state (including time estimates) cannot leak
// into IPC even if a caller passes an object with additional runtime properties.
export const requests = {
  superpixels: (id: string, p: SuperpixelOptions = {}): AnnotationRequest => ({ op: 'superpixels', id,
    ...(p.n_segments !== undefined ? { n_segments: p.n_segments } : {}),
    ...(p.compactness !== undefined ? { compactness: p.compactness } : {}),
    ...(p.pca_components !== undefined ? { pca_components: p.pca_components } : {}),
    ...(p.force !== undefined ? { force: p.force } : {}) }),
  diffuse: (id: string, seed: Seed, p: DiffuseOptions = {}): AnnotationRequest => ({ op: 'diffuse', id, seed: promptBody(seed),
    ...(p.threshold !== undefined ? { threshold: p.threshold } : {}),
    ...(p.queue_min_similarity !== undefined ? { queue_min_similarity: p.queue_min_similarity } : {}) }),
  regions: (id: string, geometry: Geometry, action: EditAction, labelId?: string): AnnotationRequest => ({ op: 'regions', id, geometry: geometryBody(geometry), action,
    ...(labelId !== undefined ? { label_id: labelId } : {}) }),
  undo: (id: string): AnnotationRequest => ({ op: 'undo', id }),
  working: (id: string): AnnotationRequest => ({ op: 'working', id }),
  validate: (id: string): AnnotationRequest => ({ op: 'validate', id }),
  save: (id: string, p: SaveOptions = {}): AnnotationRequest => ({ op: 'save', id,
    ...(p.note !== undefined ? { note: p.note } : {}), ...(p.overwrite !== undefined ? { overwrite: p.overwrite } : {}),
    ...(p.confirm !== undefined ? { confirm: p.confirm } : {}) }),
  versions: (id: string): AnnotationRequest => ({ op: 'versions', id }),
  versionOverlay: (id: string, version: string): AnnotationRequest => ({ op: 'version_overlay', id, version }),
  projects: (): AnnotationRequest => ({ op: 'projects' }),
  labels: (projectId: string): AnnotationRequest => ({ op: 'labels', project_id: projectId }),
  addLabel: (body: LabelBody): AnnotationRequest => {
    const project_id = body.project_id;
    if ('from_catalog' in body) return { op: 'add_label', body: { project_id, from_catalog: body.from_catalog, codes: body.codes } };
    if ('schema' in body) {
      const s = body.schema;
      return { op: 'add_label', body: { project_id, schema: { name: s.name, tree_path: s.tree_path, field_type: s.field_type,
        ...(s.unit !== undefined ? { unit: s.unit } : {}), ...(s.config !== undefined ? { config: s.config } : {}) } } };
    }
    return { op: 'add_label', body: { project_id, code: body.code, name: body.name, tree_path: body.tree_path, color_hex: body.color_hex,
      ...(body.shortcut_key !== undefined ? { shortcut_key: body.shortcut_key } : {}),
      ...(body.is_background !== undefined ? { is_background: body.is_background } : {}) } };
  },
  catalog: (): AnnotationRequest => ({ op: 'catalog' }),
};

function promptBody(seed: Seed): Seed {
  if ('point' in seed) return { point: [seed.point[0], seed.point[1]] };
  if ('box' in seed) return { box: [seed.box[0], seed.box[1], seed.box[2], seed.box[3]] };
  return { doodle: seed.doodle.map(([line, sample]) => [line, sample]) };
}
function geometryBody(geometry: Geometry): Geometry {
  return 'superpixels' in geometry ? { superpixels: [...geometry.superpixels] } : { polygon: geometry.polygon.map(([line, sample]) => [line, sample]) };
}

export type InvokeAnnotation = <T>(command: string, args: { request: AnnotationRequest }) => Promise<T>;
export function annotationClient(send: InvokeAnnotation = invoke): AnnotationApi {
  // The only annotation invoke in the frontend. No URL/port/token parameters.
  const forward = <T>(request: AnnotationRequest) => send<T>('annotations_forward', { request });
  return {
    superpixels: (id, p) => forward(requests.superpixels(id, p)),
    diffuse: (id, seed, p) => forward(requests.diffuse(id, seed, p)),
    regions: (id, geometry, action, labelId) => forward(requests.regions(id, geometry, action, labelId)),
    undo: id => forward(requests.undo(id)), working: id => forward(requests.working(id)),
    validate: id => forward(requests.validate(id)), save: (id, p) => forward(requests.save(id, p)),
    versions: id => forward(requests.versions(id)), versionOverlay: (id, version) => forward(requests.versionOverlay(id, version)),
    projects: () => forward(requests.projects()), labels: id => forward(requests.labels(id)),
    addLabel: body => forward(requests.addLabel(body)), catalog: () => forward(requests.catalog()),
  };
}
export const annotations = annotationClient();
