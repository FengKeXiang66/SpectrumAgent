"""Bind the new release/installer to the frozen engine, preserving milestone01."""
import hashlib
import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BATCH=ROOT/'artifacts/step2/revision-20261019-m02'
spec=importlib.util.spec_from_file_location('batch',BATCH/'batch_manifest.py')
batch=importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
manifest=json.loads((BATCH/'product-manifest.json').read_text('utf-8'))
release=ROOT/'src-tauri/target/milestone03/release'
evidence=ROOT/'milestone03/evidence/P4'
assert batch.inventory(release/'resources/backend')==manifest['files']
assert batch.inventory(ROOT/'src-tauri/resources/backend')==manifest['files']
fingerprints={p.relative_to(release).as_posix():json.loads(p.read_text('utf-8')) for p in (release/'.fingerprint').glob('spectrum-agent-*/*.json')}
bins=[v for p,v in fingerprints.items() if p.endswith('/bin-spectrum-agent.json')]
assert len(bins)==1 and json.loads(bins[0]['features'])==['custom-protocol']
assert [p.name for p in release.glob('*.exe')]==['spectrum-agent.exe']
nsis=release/'nsis/x64/installer.nsi'
text=nsis.read_text('utf-8-sig')
assert '!define VERSION "0.1.1"' in text
assert 'StrCpy $INSTDIR "$LOCALAPPDATA\\Programs\\${PRODUCTNAME}"' in text
assert 'supervisor-stub.exe' not in text and 'supervisor-probe.exe' not in text
shutil.copyfile(nsis,evidence/'installer.nsi')
installer=release/'bundle/nsis/SpectrumAgent_0.1.1_x64-setup.exe'
assert installer.is_file()
old=ROOT/'artifacts/step4/setup.exe'
assert old.stat().st_size==287156790 and batch.sha(old)=='d849253611c1ac985cb08a60a7073e17ed6c89b74e8230532d0c3d2157cc8107'
destination=ROOT/'artifacts/milestone03/SpectrumAgent_0.1.1_x64-setup.exe'
destination.parent.mkdir(parents=True,exist_ok=True)
assert not destination.exists(),'Do not overwrite unknown installer'
shutil.copyfile(installer,destination)
assert batch.sha(installer)==batch.sha(destination)
shell=release/'spectrum-agent.exe'
assert json.loads((evidence/'shell-manifest-binding.json').read_text('utf-8-sig'))['sha256']==batch.sha(shell)
result={'timestamp':datetime.now(timezone.utc).isoformat(),'product_version':'0.1.1','protocol_version':'0.1.0','setup':{'source':str(installer),'delivery':str(destination),'bytes':installer.stat().st_size,'sha256':batch.sha(installer),'copy_matches':True,'delta_from_01_bytes':installer.stat().st_size-287156790,'delta_scope':'combined release UI/engine/IPC/dialog-rfd payload; not an isolated dialog-only measurement'},'shell':{'path':str(shell),'bytes':shell.stat().st_size,'sha256':batch.sha(shell),'features':['custom-protocol'],'test_probes':False},'engine_manifest_sha256':batch.sha(BATCH/'product-manifest.json'),'release_resource_files_match':len(manifest['files']),'milestone01_setup_unchanged':True,'dist':batch.inventory(ROOT/'dist'),'fingerprints':fingerprints,'p7_installed_smoke':'待负责人本机执行'}
with (evidence/'release-candidate.json').open('x',encoding='utf-8') as stream: json.dump(result,stream,indent=2,ensure_ascii=False)
print(json.dumps({k:v for k,v in result.items() if k!='fingerprints'},indent=2,ensure_ascii=False))
