"""A fast signature may deduplicate intermediate reads, never establish content identity."""
import os
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src-python')]
from spectrumagent.annotation.engines.superpixels import SuperpixelEngine


def test_hashes_are_shared_only_inside_an_operation(tmp_path,monkeypatch):
    header=tmp_path/'cube.hdr';data=tmp_path/'cube.dat'
    header.write_bytes(b'header');data.write_bytes(b'first')
    registry=SimpleNamespace(readable=lambda *a,**k:(SimpleNamespace(header_path=str(header),data_path=str(data)),False))
    engine=SuperpixelEngine(registry)
    import spectrumagent.preprocess.run as runs
    original=runs.file_sha256;calls=[]
    def count(path):calls.append(path);return original(path)
    monkeypatch.setattr(runs,'file_sha256',count)
    with engine.identity_scope('cube'):
        first=engine.source_identity('cube')
        assert engine.source_identity('cube')==first
        assert len(calls)==2
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(engine.source_identity,'cube').result()==first
        assert len(calls)==4  # An independent request cannot borrow this scope.
        assert engine.source_identity('cube',full=True)==first
        assert len(calls)==6
    assert engine.source_identity('cube')==first
    assert len(calls)==8


def test_same_size_and_restored_mtime_still_rehashes_at_boundaries(tmp_path):
    header=tmp_path/'cube.hdr';data=tmp_path/'cube.dat'
    header.write_bytes(b'header');data.write_bytes(b'first')
    registry=SimpleNamespace(readable=lambda *a,**k:(SimpleNamespace(header_path=str(header),data_path=str(data)),False))
    engine=SuperpixelEngine(registry)
    with engine.identity_scope('cube'):
        first=engine.source_identity('cube')
        original=data.stat()
        data.write_bytes(b'other')
        os.utime(data,ns=(original.st_atime_ns,original.st_mtime_ns))
        assert engine.source_identity('cube',full=True)[0]!=first[0]
    assert engine.source_identity('cube')[0]!=first[0]
