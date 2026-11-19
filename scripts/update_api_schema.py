"""Regenerate the checked API snapshot using a fresh isolated workspace app."""
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from backend.paths import AppPaths
from backend.identity import EngineIdentity
from spectrumagent.app import create_app

if __name__=='__main__':
    output=ROOT/'artifacts/task66/schema-build'
    if output.exists():raise ValueError('Use a fresh schema workspace')
    os.environ['SPECTRUMAGENT_PERMANENT_ROOT']=str(output/'permanent')
    app=create_app(AppPaths(output/'data'),EngineIdentity())
    (ROOT/'src-python/spectrumagent/api/openapi.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n','utf-8')
    print('API snapshot regenerated from isolated application.')
