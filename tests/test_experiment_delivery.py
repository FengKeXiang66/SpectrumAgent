"""Substep cancellation and bounded export delivery."""
import asyncio
from pathlib import Path
from types import SimpleNamespace
import warnings
from zipfile import ZipFile

import numpy as np
import pytest

from test_experiments import workspace
from spectrumagent.api.agent import ZipDownload
from spectrumagent.data import DataError
from spectrumagent.experiments import inputs
from spectrumagent.experiments.inference import InferenceService
from spectrumagent.experiments.report import curve_plot, representative_curves
from spectrumagent.experiments.schema import ImageInput


def test_envi_preparation_checks_cancel_at_the_next_row_block(tmp_path, monkeypatch):
    members, reads = [], []
    for i in range(2):
        hdr, img, roi = (tmp_path/f'{i}.{suffix}' for suffix in ('hdr','img','json'))
        for path in (hdr,img,roi):
            path.write_bytes(b'input')
        members.append(dict(header_path=str(hdr), data_path=str(img), roi_path=str(roi), sample_id=str(i)))

    def fake_envi(header, image, *, raw):
        def read_region(start, end, _left, width):
            reads.append((Path(header).stem, start, end))
            return np.broadcast_to([1., 2.], (end-start, width, 2)).copy()
        return SimpleNamespace(header_path=header, data_path=image, shape=(96,3,2), wavelengths=[1100.,1105.],
                               metadata={'scale_factor':1, 'wavelength units':'nm'}, read_region=read_region)

    monkeypatch.setattr(inputs, 'open_envi', fake_envi)
    monkeypatch.setattr(inputs, 'roi_maps', lambda *args: (np.ones((96,3),int), np.ones((96,3),int)))
    spec = ImageInput(kind='roi_images', members=members, neighborhood=1, wavelength_unit='nm', mapping_window_nm=5.,
                      nearest_tolerance_nm=0., quality=dict(min_mean=0.,min_std=0.,max_zero_fraction=1.,saturation=None))
    progress = []
    def receive(**details):
        if details:
            progress.append((details['file_index'], details['file_total'], details['rows_done'], details['rows_total']))
        if progress and progress[-1][:3] == (2,2,32) and not details:
            raise DataError('EXPERIMENT_CANCELLED', 'requested')

    with pytest.raises(DataError, match='requested'):
        inputs.load_input(spec, np.array([1100.,1105.]), {1:'PE'}, progress=receive)
    assert reads == [('0',0,32),('0',32,64),('0',64,96),('1',0,32)]
    assert [entry for entry in progress if entry[2]] == [(1,2,32,96),(1,2,64,96),(1,2,96,96),(2,2,32,96)]


def test_hashing_checks_cancellation_in_large_file(tmp_path):
    path = tmp_path/'large.img'
    path.write_bytes(b'\0'*(3*1024*1024))
    checked = 0
    def cancel():
        nonlocal checked
        checked += 1
        if checked == 2:
            raise DataError('EXPERIMENT_CANCELLED', 'hashing stopped')
    with pytest.raises(DataError, match='hashing stopped'):
        inputs.sha256(path, cancel)
    assert checked == 2


def test_curves_render_material_names_including_paper(tmp_path,monkeypatch):
    from matplotlib import ft2font
    import matplotlib.figure  # Load matplotlib's font consumers before patching the constructor.
    original = ft2font.FT2Font
    checked = []
    def requires_string(path,*args,**kwargs):
        assert isinstance(path,str)
        checked.append(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(ft2font,'FT2Font',requires_string)
    curves = representative_curves(np.array([[1.,2.],[3.,5.]]), np.array([1,2]), {1:'PE',2:'纸'}, [1100.,1105.])
    plot = tmp_path/'legend.png'
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter('always')
        curve_plot(curves, plot, 'test_input')
    assert not [warning for warning in seen if 'Glyph' in str(warning.message)]
    assert checked
    assert plot.read_bytes().startswith(b'\x89PNG') and plot.stat().st_size > 1024


def test_inference_large_bundle_streams_from_disk_and_cleans_up(tmp_path, workspace):
    source = tmp_path/'0.npz'
    random = np.random.default_rng(7)
    with source.open('wb') as stream:
        for _ in range(65):
            stream.write(random.bytes(1024*1024))
    from spectrumagent.experiments.inputs import sha256
    service = SimpleNamespace(folder=lambda *_:tmp_path,
        _saved_result=lambda *_:{'kind':'npz','artifacts':{'0.npz':{
            'bytes':source.stat().st_size,'sha256':sha256(source)}}})
    response = ZipDownload(lambda target: InferenceService.export(service, 'model', 'run', output=target))
    staged = Path(response.path)
    with ZipFile(staged) as archive:
        assert archive.getinfo('0.npz').file_size == source.stat().st_size
    size = staged.stat().st_size
    assert size > 64*1024*1024
    chunks = []
    async def receive():
        await asyncio.Event().wait()
    async def send(message):
        if message['type'] == 'http.response.body':
            chunks.append(len(message['body']))
    scope = {'type':'http', 'method':'GET', 'headers':[], 'extensions':{}, 'asgi':{'spec_version':'2.4'}}
    asyncio.run(response(scope, receive, send))
    assert sum(chunks) == size and max(chunks) <= 1024*1024
    assert not staged.exists()
