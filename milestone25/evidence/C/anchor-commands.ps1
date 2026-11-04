& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'useState<CatalogRecord' -e 'setWorkspace({}); setRecords' src/App.tsx
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'callbacks.imported(result.datasets)' src/components/datasets/actions.ts
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'all_datasets:' -e 'export function mergeRecords' -e 'const merged = new Map' -e 'merged.set' -e '[...merged.values()]' -e 'DatasetTransport' src/components/datasets/types.ts
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'all_datasets:' src-python/spectrumagent/api/schemas.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'G2 all_datasets' src/components/datasets/display_names.test.ts
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'UNIQUE(header_key,raw)' -e 'SELECT id,payload FROM dataset_registry WHERE header_key=? AND raw=?' -e 'INSERT INTO dataset_registry (' -e 'all_records = [' -e 'def readable' -e 'current = read_header(Path(stored.header_path)' src-python/spectrumagent/api/registry.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'export type Request' -e 'open({ directory: true' src/components/datasets/api.ts
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -e 'serde(tag' -e 'pub enum DatasetRequest' src-tauri/src/datasets_dev.rs
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'PRAGMA foreign_keys=ON' backend/database.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'NAS_SOURCE_ROOT' -e 'NAS_OUTPUT_ROOT' -e 'def database' -e 'def snapshots' -e 'def preprocessed' -e 'def exports' backend/paths.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'return json.loads(self.session(session_id)' -e 'UPDATE agent_session SET context_json=?' src-python/spectrumagent/agent/state.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F '_DENY_TEXT =' src-python/spectrumagent/agent/llm.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'resolve().is_relative_to(self.paths.exports.resolve())' src-python/spectrumagent/agent/mat.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'DELETE FROM annotation WHERE' -e 'DELETE FROM sample_spectrum WHERE' -e 'DELETE FROM training_mat WHERE' -e 'storage.rmtree(directory)' src-python/spectrumagent/annotation/session.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'deferred = db.execute' -e 'SAVEPOINT modeling_132' -e 'INSERT INTO {name}_132' -e 'PRAGMA defer_foreign_keys=ON' -e 'DROP TABLE {name}' -e 'ALTER TABLE {name}_132' -e 'RELEASE modeling_132' -e 'PRAGMA defer_foreign_keys={int(deferred)}' src-python/spectrumagent/modeling/migrations.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'return paths.root /' -e 'root = paths.exports.resolve()' -e 'folder = root / cube_id' src-python/spectrumagent/annotation/projection_io.py

& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'UPDATE dataset_registry SET payload=? WHERE id=?' src-python/spectrumagent/api/registry.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F 'def trash' backend/paths.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -E '^def (resolve_write|resolve_delete|mkdir|unlink|rmtree|replace)[(]' src-python/spectrumagent/storage/guard.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'pub enum SettingsRequest' -e 'serde(tag' -e 'pub fn destination' -e 'let paths:' -e 'let secrets =' -e 'SettingsRequest::PutKey' src-tauri/src/settings.rs
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'export type SettingsRequest' -e 'settings_forward' src/components/settings/settings-forward.ts
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'def make_router' -e 'APIRouter(prefix=' -e '@router.get' -e '@router.put' src-python/spectrumagent/api/settings.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e 'make_settings_router(paths)' -e '/api/v1/settings' src-python/spectrumagent/app.py
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -F -e '"/api/v1/settings/llm":' -e '"/api/v1/settings/llm/key":' -e '"/api/v1/settings/projects/{project_id}/paths":' src-python/spectrumagent/api/openapi.json
& 'C:/Program Files/Git/usr/bin/grep.exe' -nH -E '^export type DatasetTransport|^  (get:|chooseDirectories:|importDirectory:|catalog:|deletePreview:|delete:|recycleList:|restore:|preview:|spectraMean:)|^};' src/components/datasets/types.ts
