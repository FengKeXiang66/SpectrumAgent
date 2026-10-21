"""TASK-06: independent pixel/PNG/API checks, using the project BIL reader."""
import base64
import math
from pathlib import Path
import struct
import zlib

from fastapi.testclient import TestClient
import numpy as np
import pytest

from backend.identity import EngineIdentity
from backend.paths import AppPaths
from spectrumagent.api.datasets import png_gray
from spectrumagent.app import create_app


@pytest.fixture
def display_api(tmp_path):
    identity = EngineIdentity()
    paths = AppPaths(tmp_path / 'app')
    with TestClient(create_app(paths, identity)) as client:
        client.headers['Authorization'] = 'Bearer ' + identity.token

        def register(values, *, wavelengths=None, raw=False):
            values = np.asarray(values, dtype='<f8')
            folder = tmp_path / f'cube-{len(list(tmp_path.glob("cube-*")))}'
            folder.mkdir()
            values.transpose(0, 2, 1).tofile(folder / 'cube.img')
            h, w, b = values.shape
            wl = list(range(b)) if wavelengths is None else wavelengths
            axis = 'wavelength={' + ','.join(map(str, wl)) + '}\n' if wl else ''
            header = folder / 'cube.hdr'
            header.write_text(f'ENVI\nsamples={w}\nlines={h}\nbands={b}\ndata type=5\ninterleave=bil\nbyte order=0\nreflectance scale factor=1\n'+axis, 'utf-8')
            response = client.post('/api/v1/datasets/import', json={'path': str(header), 'raw': raw})
            assert response.status_code == 200
            return response.json()['datasets'][0]['id'], header

        yield client, register


def pixels(encoded):
    data = base64.b64decode(encoded)
    width, height = struct.unpack('>II', data[16:24])
    channels = {0: 1, 2: 3, 6: 4}[data[25]]
    offset, compressed = 8, b''
    while offset < len(data):
        n = struct.unpack('>I', data[offset:offset+4])[0]
        if data[offset+4:offset+8] == b'IDAT':
            compressed += data[offset+8:offset+8+n]
        offset += n+12
    rows = np.frombuffer(zlib.decompress(compressed), np.uint8).reshape(height, width*channels+1)
    assert np.all(rows[:, 0] == 0)
    return rows[:, 1:].reshape(height, width, channels)


@pytest.mark.parametrize('size', ['preview', 'full'])
def test_single_band_selection_and_size(display_api, size):
    client, register = display_api
    values = np.arange(4*514*5, dtype=float).reshape(4, 514, 5)
    identifier, _ = register(values)
    band = values.shape[2]-1
    info = client.get(f'/api/v1/datasets/{identifier}/preview?band={band}&size={size}').json()
    stride = 1 if size == 'full' else math.ceil(514/512)
    assert (info['height'], info['width']) == (math.ceil(4/stride), math.ceil(514/stride))
    assert info['band'] == band
    assert not {'bands', 'wavelengths', 'fallback'} & info.keys()


def test_none_png_matches_head_minmax_truncation_byte_for_byte(display_api):
    client, register = display_api
    values = np.array([0, .1, .3, .6, 1, 8.3], dtype=float).reshape(2, 3, 1)
    identifier, _ = register(values)
    image = values[:, :, 0]
    expected = np.clip((image-image.min())/(image.max()-image.min())*255, 0, 255).astype(np.uint8)
    response = client.get(f'/api/v1/datasets/{identifier}/preview?band=0&stretch=none')
    assert response.status_code == 200
    assert response.json()['png_base64'] == png_gray(expected)


@pytest.mark.parametrize('query', ['', '?band=-1', '?band=99', '?band=0&size=wrong'])
def test_single_band_bad_parameters_are_structured(display_api, query):
    client, register = display_api
    identifier, _ = register(np.ones((2, 3, 4)))
    response = client.get(f'/api/v1/datasets/{identifier}/preview'+query)
    assert response.status_code == 400
    assert {'error', 'detail', 'context'} <= response.json().keys()


def test_default_auto_matches_finite_percentiles_and_round(display_api):
    client, register = display_api
    values = np.arange(101., dtype=float).reshape(1, 101, 1)
    values[0, -1, 0] = 1e6
    identifier, _ = register(values)
    response = client.get(f'/api/v1/datasets/{identifier}/preview?band=0')
    lo, hi = np.percentile(values, [2, 98])
    expected = np.rint(np.clip((values-lo)/(hi-lo)*255, 0, 255)).astype(np.uint8)
    np.testing.assert_array_equal(pixels(response.json()['png_base64']), expected)


@pytest.mark.parametrize('stretch', ['none', 'auto'])
def test_gray_nonfinite_is_black_and_excluded_from_range(display_api, stretch):
    client, register = display_api
    values = np.array([np.nan, np.inf, -np.inf, 5., 8., 12.]).reshape(2, 3, 1)
    identifier, _ = register(values)
    response = client.get(f'/api/v1/datasets/{identifier}/preview?band=0&stretch={stretch}')
    data = pixels(response.json()['png_base64']).reshape(-1)
    assert np.all(data[:3] == 0)
    lo, hi = np.percentile([5, 8, 12], [2, 98]) if stretch == 'auto' else (5, 12)
    expected = np.clip((np.array([5, 8, 12])-lo)/(hi-lo)*255, 0, 255)
    expected = np.rint(expected) if stretch == 'auto' else expected
    np.testing.assert_array_equal(data[3:], expected.astype(np.uint8))


@pytest.mark.parametrize('stretch', ['none', 'auto'])
def test_gray_constant_is_black(display_api, stretch):
    client, register = display_api
    identifier, _ = register(np.full((3, 4, 1), 8.))
    response = client.get(f'/api/v1/datasets/{identifier}/preview?band=0&stretch={stretch}')
    assert not pixels(response.json()['png_base64']).any()


def test_invalid_stretch_is_structured(display_api):
    client, register = display_api
    identifier, _ = register(np.ones((2, 3, 4)))
    response = client.get(f'/api/v1/datasets/{identifier}/preview?band=0&stretch=bad')
    assert response.status_code == 400 and response.json()['error'] == 'INVALID_REQUEST'
