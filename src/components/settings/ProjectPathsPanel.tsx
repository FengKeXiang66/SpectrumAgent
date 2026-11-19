import { useEffect, useState } from 'react';
import { open } from '@tauri-apps/plugin-dialog';
import { annotations } from '../annotation/api.ts';
import { settings } from './settings-forward.ts';
import { createPathForm, emptyPathForm, type PathServices } from './project-path-form.ts';
import { ProjectPathsView } from './ProjectPathsView.ts';

const services: PathServices = { projects: annotations.projects, getProjectPaths: settings.getProjectPaths,
  putProjectPaths: settings.putProjectPaths, chooseDirectory: async () => {
    const result = await open({ directory: true, multiple: false });
    return Array.isArray(result) ? result[0] ?? null : result;
  } };

export default function ProjectPathsPanel({ summary = false }: { summary?: boolean }) {
  const [state, setState] = useState(emptyPathForm);
  const [form, setForm] = useState<ReturnType<typeof createPathForm> | null>(null);
  useEffect(() => {
    const current = createPathForm(services, setState, summary ? '' : window.location.search);
    setForm(current); void current.load();
    return () => current.dispose();
  }, [summary]);
  return <ProjectPathsView state={state} summary={summary} onEdit={(field, value) => form?.edit(field, value)}
    onBrowse={field => { void form?.browse(field); }} onSave={() => { void form?.save(); }} onRetry={() => { void form?.load(); }} />;
}
