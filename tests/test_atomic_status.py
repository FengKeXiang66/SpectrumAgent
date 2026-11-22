"""Pollers must only see complete documents during atomic status publication."""
from concurrent.futures import ThreadPoolExecutor
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from test_experiments import workspace


def test_concurrent_status_reader_and_writer(workspace):
    from spectrumagent.experiments.service import read_json,write_json
    target=workspace.root/'status.json'
    write_json(target,{'version':0,'payload':'x'*1024})
    def publish():
        for version in range(1,101):write_json(target,{'version':version,'payload':'x'*1024})
    with ThreadPoolExecutor(max_workers=1) as pool:
        work=pool.submit(publish)
        while not work.done():
            value=read_json(target)
            assert 0<=value['version']<=100 and value['payload']=='x'*1024
        work.result()
    assert read_json(target)['version']==100
