import { describeError } from '../datasets/types.ts';
import { normalizePath, pathPrefill } from '../datasets/paths.ts';
import type { PathValues, ProjectPaths, SettingsApi } from './settings-forward.ts';

export type PathFormState = { values: ProjectPaths; projectId: string; projectName: string;
  phase: 'loading' | 'ready' | 'saving' | 'browsing' | 'error'; error: string; message: string };
export const emptyPathForm = (): PathFormState => ({ values: { source_path: '', output_root: '', data_root: '', output_enabled: false },
  projectId: '', projectName: '', phase: 'loading', error: '', message: '' });
export type PathServices = Pick<SettingsApi, 'getProjectPaths' | 'putProjectPaths'> & {
  projects(): Promise<{ id: string; name: string }[]>; chooseDirectory(): Promise<string | null> };

export function createPathForm(api: PathServices, changed: (state: PathFormState) => void, search = '') {
  let state = emptyPathForm(), live = true;
  const update = (patch: Partial<PathFormState>) => { if (live) { state = { ...state, ...patch }; changed(state); } };
  return {
    async load() {
      update({ phase: 'loading', error: '' });
      try {
        const projects = await api.projects();
        if (!live) return;
        const project = projects.find(row => row.name === '默认项目') ?? projects[0];
        if (!project) throw new Error('尚无可保存路径设置的项目。');
        const saved = await api.getProjectPaths(project.id);
        update({ projectId: project.id, projectName: project.name, values: { ...saved, ...pathPrefill(search) }, phase: 'ready' });
      } catch (failure) { update({ phase: 'error', error: describeError(failure) }); }
    },
    edit(field: keyof PathValues, value: string) {
      if (state.phase === 'ready') update({ values: { ...state.values, [field]: value }, message: '' });
    },
    async browse(field: keyof PathValues) {
      if (state.phase !== 'ready') return;
      update({ phase: 'browsing', error: '' });
      try {
        const path = await api.chooseDirectory();
        if (path !== null) update({ values: { ...state.values, [field]: normalizePath(path) }, message: '' });
      } catch (failure) { update({ error: describeError(failure) }); }
      finally { update({ phase: 'ready' }); }
    },
    async save() {
      if (state.phase !== 'ready') return;
      update({ phase: 'saving', error: '', message: '' });
      try {
        const values = await api.putProjectPaths(state.projectId, {
          source_path: normalizePath(state.values.source_path), output_root: normalizePath(state.values.output_root) });
        update({ values, message: '已保存为该项目默认。输出根保存后重启生效。' });
      } catch (failure) { update({ error: describeError(failure) }); }
      finally { update({ phase: 'ready' }); }
    },
    dispose() { live = false; },
  };
}
