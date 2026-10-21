"""TASK-06: independent pixel/PNG/API checks, using the project BIL reader."""
import base64
import math
from itertools import permutations
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
from spectrumagent.display.falsecolor import compose_rgb


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


@pytest.mark.parametrize('stretch', ['auto', 'none'])
def test_rgb_joint_mapping_no_second_stretch_or_independent_noise_amplification(stretch):
    r = np.linspace(0, 100, 100).reshape(10, 10)
    g = r*.5
    b = np.linspace(49, 50, 100).reshape(10, 10)
    original = np.stack((r, g, b), axis=2)
    lo, hi = np.percentile(original, [2, 98]) if stretch == 'auto' else (original.min(), original.max())
    expected = np.clip((original-lo)/(hi-lo)*255, 0, 255)
    expected = np.rint(expected) if stretch == 'auto' else expected
    actual = pixels(compose_rgb(r, g, b, stretch))
    np.testing.assert_array_equal(actual, expected.astype(np.uint8))
    assert np.ptp(actual[:, :, 2]) < 10


@pytest.mark.parametrize('value', [4., np.nan])
@pytest.mark.parametrize('stretch', ['auto', 'none'])
def test_rgb_constant_or_all_nan_is_black(value, stretch):
    plane = np.full((2, 3), value)
    assert not pixels(compose_rgb(plane, plane, plane, stretch)).any()


@pytest.mark.parametrize('stretch', ['auto', 'none'])
def test_rgb_nonfinite_is_excluded_and_maps_black(stretch):
    source = np.arange(18., dtype=float).reshape(2, 3, 3)
    source[0, 0] = [np.nan, np.inf, -np.inf]
    valid = source[np.isfinite(source)]
    lo, hi = np.percentile(valid, [2, 98]) if stretch == 'auto' else (valid.min(), valid.max())
    expected = np.zeros(source.shape, dtype=np.uint8)
    scaled = np.clip((source[np.isfinite(source)]-lo)/(hi-lo)*255, 0, 255)
    expected[np.isfinite(source)] = (np.rint(scaled) if stretch == 'auto' else scaled).astype(np.uint8)
    np.testing.assert_array_equal(pixels(compose_rgb(*np.moveaxis(source, 2, 0), stretch)), expected)


@pytest.mark.parametrize('size', ['preview', 'full'])
def test_manual_rgb_channel_order_metadata_and_dimensions_match_gray(display_api, size):
    client, register = display_api
    values = np.arange(4*514*5, dtype=float).reshape(4, 514, 5)
    axis = [900, 1000, 1100, 1200, 1300]
    identifier, _ = register(values, wavelengths=axis)
    rgb = [4, 2, 0]
    result = client.get(f'/api/v1/datasets/{identifier}/preview?bands=4,2,0&size={size}').json()
    gray = client.get(f'/api/v1/datasets/{identifier}/preview?band=0&size={size}').json()
    assert (result['width'], result['height']) == (gray['width'], gray['height'])
    assert result['bands'] == rgb and result['band'] == rgb[0]
    assert result['wavelengths'] == [axis[i] for i in rgb]
    assert result['fallback'] is False
    assert pixels(result['png_base64']).shape[2] == 3


@pytest.mark.parametrize('query,code', [
    ('bands=0,1', 'INVALID_BANDS'), ('bands=0,1,2,3', 'INVALID_BANDS'),
    ('bands=1,1,2', 'INVALID_BANDS'), ('bands=-1,1,2', 'INVALID_BANDS'),
    ('bands=0,x,2', 'INVALID_BANDS'), ('bands=0,1,5', 'INVALID_BANDS'),
    ('band=0&bands=0,1,2', 'INVALID_REQUEST'),
])
def test_manual_rgb_invalid_bands_are_structured(display_api, query, code):
    client, register = display_api
    identifier, _ = register(np.ones((2, 3, 4)))
    response = client.get(f'/api/v1/datasets/{identifier}/preview?'+query)
    assert response.status_code == 400 and response.json()['error'] == code


def test_rgb_cache_revalidates_source_and_invalidates_on_source_changed(display_api, monkeypatch):
    from spectrumagent.api import datasets
    client, register = display_api
    identifier, header = register(np.ones((2, 3, 4)))
    original = datasets.compose_rgb
    calls = []
    def spy(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(datasets, 'compose_rgb', spy)
    endpoint = f'/api/v1/datasets/{identifier}/preview?bands=0,1,2'
    assert client.get(endpoint).status_code == 200
    assert client.get(endpoint).status_code == 200 and len(calls) == 1
    saved = header.read_bytes()
    header.unlink()
    failed = client.get(endpoint)
    assert failed.status_code == 400 and failed.json()['error'] == 'SOURCE_CHANGED'
    header.write_bytes(saved)
    assert client.get(endpoint).status_code == 200 and len(calls) == 2


def test_rgb_cache_is_lru_eight(display_api, monkeypatch):
    from spectrumagent.api import datasets
    client, register = display_api
    identifier, _ = register(np.ones((2, 3, 4)))
    original = datasets.compose_rgb
    calls = []
    def spy(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(datasets, 'compose_rgb', spy)
    requests = [f'/api/v1/datasets/{identifier}/preview?bands='+','.join(map(str, p)) for p in list(permutations(range(4), 3))[:9]]
    for endpoint in [requests[0], *requests]:
        assert client.get(endpoint).status_code == 200
    assert len(calls) == 9
    assert client.get(requests[0]).status_code == 200 and len(calls) == 10
