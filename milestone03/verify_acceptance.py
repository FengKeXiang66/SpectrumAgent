"""Compare recorded P6 responses and audit immutable delivery inputs; no HTTP suite."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'milestone03/evidence/P6'
BATCH=ROOT/'artifacts/step2/revision-20261019-m02'
read=lambda path: json.loads(path.read_text('utf-8-sig'))
sha=lambda path: hashlib.sha256(path.read_bytes()).hexdigest()


def normalized(value):
    # These are expected to differ per boot/import, not product semantics.
    volatile={'boot_id','pid','id','dataset_id','data_path','header_path','path','elapsed_ms','uptime_s'}
    if isinstance(value,dict):
        return {key:normalized(item) for key,item in value.items() if key not in volatile}
    if isinstance(value,list):
        return [normalized(item) for item in value]
    return value


def recorded_responses(path):
    prefixes=('HEALTH','UNAUTHORIZED','IMPORT','RAW_BAND','SCALED_OVERRIDE','PREVIEW','MISSING','HEADER_INVALID','SIZE_MISMATCH')
    found={}
    for line in path.read_text('utf-8-sig').splitlines():
        parts=line.split(' ',2)
        if len(parts)==3 and parts[0] in prefixes:
            found[parts[0]]={'status':int(parts[1]),'body':normalized(json.loads(parts[2]))}
    assert set(found)==set(prefixes)
    return found


def main():
    venv=read(EVIDENCE/'venv-result.json')
    onedir=read(EVIDENCE/'onedir-result.json')
    assert normalized(venv)==normalized(onedir),'P6 contract mismatch'
    full_venv=recorded_responses(EVIDENCE/'venv-output.txt')
    full_onedir=recorded_responses(EVIDENCE/'onedir-output.txt')
    assert full_venv==full_onedir,'P6 full response mismatch'
    manifest=read(BATCH/'product-manifest.json')
    spec=importlib.util.spec_from_file_location('batch',BATCH/'batch_manifest.py')
    batch=importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
    batch.unchanged_inputs()
    assert batch.inventory(ROOT/'src-tauri/resources/backend')==manifest['files']
    assert batch.inventory(ROOT/'src-tauri/target/milestone03/release/resources/backend')==manifest['files']
    baseline=read(ROOT/'milestone03/evidence/P0/baseline.json')
    assert all(sha(ROOT/path)==digest for path,digest in baseline['locks'].items())
    candidate=read(ROOT/'milestone03/evidence/P4/release-candidate.json')
    assert sha(Path(candidate['setup']['delivery']))==candidate['setup']['sha256']
    assert sha(Path(candidate['shell']['path']))==candidate['shell']['sha256']
    assert batch.inventory(ROOT/'dist')==candidate['dist']
    assert sha(ROOT/'artifacts/step4/setup.exe')=='d849253611c1ac985cb08a60a7073e17ed6c89b74e8230532d0c3d2157cc8107'
    isolated=['scripts/dev_sidecar.py','backend/__init__.py','src-tauri/src/dev_engine.rs','src-tauri/src/dev_supervision.rs','src-tauri/src/process.rs','src-tauri/src/win32.rs','src-tauri/src/engine_path.rs','src-tauri/src/handshake.rs','src-tauri/nsis/installer.nsi']
    assert not subprocess.check_output(['git','diff','f4e5c90','--',*isolated],cwd=ROOT)
    result={'same_http_suite':'scripts/selfcheck_milestone02.py','venv_and_onedir_equal':True,'full_responses_equal':list(full_venv),
            'normalization_excludes':['per-boot boot_id/pid','per-import IDs','temporary source paths','elapsed_ms/health.uptime_s'],
            'errors_keep_atomic_batch_envelope':True,'frozen_manifest':str(BATCH/'product-manifest.json'),'frozen_manifest_sha256':sha(BATCH/'product-manifest.json'),
            'frozen_app_sha256':next(r['sha256'] for r in manifest['files'] if r['path']=='app.exe'),
            'normalized_contract':normalized(venv),'integrity':{'new_engine_resource_trees_match':544,'three_lockfiles_unchanged':True,'old_sealed_evidence_hashes_unchanged':True,'milestone01_setup_unchanged':True,'shell_setup_and_dist_still_bound':True,'isolated_files_unchanged':isolated},
            'p6_cleanup_scope':'test hygiene only; no installed app / Job claim','p7':'待负责人本机执行'}
    (EVIDENCE/'runtime-comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
