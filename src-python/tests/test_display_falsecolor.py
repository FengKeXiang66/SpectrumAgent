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
from spectrumagent.display.falsecolor import compose_rgb, select_feature_bands


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


class ArrayCube:
    def __init__(self, array):
        self.array = np.asarray(array, dtype=np.float64)
        self.requests = []

    def read_subimage(self, rows, cols, bands):
        self.requests.append((rows, cols, bands))
        return self.array[np.ix_(rows, cols, bands)]


def varied_three():
    grid = np.arange(30.).reshape(5, 6)
    return np.stack((grid, np.sin(grid*3), np.zeros_like(grid)), axis=2)


def test_feature_no_wavelengths_uses_index_dispersion():
    reader = ArrayCube(np.random.default_rng(0).normal(size=(260, 20, 8)))
    r, g, b, fallback = select_feature_bands(reader, reader.array.shape, [])
    assert fallback and 0 <= b < g < r < reader.array.shape[2]
    assert r-b >= .15*(reader.array.shape[2]-1)
    assert reader.requests[0][0] == list(range(0, 260, math.ceil(260/128)))
    assert reader.requests[0][1] == list(range(0, 20, math.ceil(260/128)))


def test_feature_insufficient_candidates_falls_back_to_wavelength_quantiles():
    reader = ArrayCube(varied_three())
    wl = [900, 1100, 1300]
    *rgb, fallback = select_feature_bands(reader, reader.array.shape, wl)
    assert fallback and len(set(rgb)) == 3
    expected = [int(np.argmin(np.abs(np.asarray(wl)-(wl[0]+p*(wl[-1]-wl[0]))))) for p in (0., .5, 1.)]
    assert rgb == expected[::-1]


@pytest.mark.parametrize('bands', [1, 2])
def test_feature_less_than_three_bands_is_structured_400(display_api, bands):
    client, register = display_api
    identifier, _ = register(np.ones((2, 3, bands)))
    response = client.get(f'/api/v1/datasets/{identifier}/preview?bands=auto')
    assert response.status_code == 400 and response.json()['error'] == 'INVALID_BANDS'


def test_feature_constant_corr_nan_is_zero_not_fallback():
    reader = ArrayCube(np.ones((4, 6, 8)))
    r, g, b, fallback = select_feature_bands(reader, reader.array.shape, list(range(8)))
    assert not fallback and 0 <= b < g < r < 8
    assert r-b >= .15*7


def test_feature_no_dispersed_combination_falls_back():
    grid = np.arange(8)[:, None]+np.arange(9)[None, :]
    values = np.concatenate((np.repeat(grid[:, :, None], 10, axis=2),
                             np.random.default_rng(0).normal(size=(8, 9, 10))), axis=2)
    reader = ArrayCube(values)
    wl = [i*.001 for i in range(10)]+list(np.linspace(100, 200, 10))
    r, g, b, fallback = select_feature_bands(reader, values.shape, wl)
    assert fallback and len({r, g, b}) == 3
    assert wl[r]-wl[b] >= .15*(wl[-1]-wl[0])


def test_feature_quantile_duplicates_use_distinct_index_safety_net():
    reader = ArrayCube(varied_three())
    *rgb, fallback = select_feature_bands(reader, reader.array.shape, [900]*3)
    assert fallback and set(rgb) == {0, (reader.array.shape[2]-1)//2, reader.array.shape[2]-1}


def test_feature_corr_shape_assertion_catches_wrong_index_space(monkeypatch):
    from spectrumagent.display import falsecolor
    reader = ArrayCube(np.random.default_rng(0).normal(size=(5, 8, 10)))
    original = falsecolor.np.corrcoef
    def wrong_shape(x):
        corr = original(x)
        return np.pad(corr, ((0, 1), (0, 1)))
    monkeypatch.setattr(falsecolor.np, 'corrcoef', wrong_shape)
    with pytest.raises(AssertionError):
        select_feature_bands(reader, reader.array.shape, list(range(10)))


def test_feature_cache_uses_algorithm_version_and_revalidates_source(display_api, monkeypatch, caplog):
    from spectrumagent.api import datasets
    client, register = display_api
    identifier, header = register(np.random.default_rng(0).normal(size=(4, 8, 10)))
    original = datasets.select_feature_bands
    calls = []
    def spy(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(datasets, 'select_feature_bands', spy)
    caplog.set_level('DEBUG', logger=datasets.__name__)
    endpoint = f'/api/v1/datasets/{identifier}/preview?bands=auto'
    assert client.get(endpoint).status_code == 200
    assert client.get(endpoint).status_code == 200 and len(calls) == 1
    assert 'display_feature_cache_miss' in caplog.text and 'duration_ms=' in caplog.text
    monkeypatch.setattr(datasets, 'FEATURECOLOR_ALGO_VERSION', datasets.FEATURECOLOR_ALGO_VERSION+1)
    assert client.get(endpoint).status_code == 200 and len(calls) == 2
    saved = header.read_bytes()
    header.unlink()
    assert client.get(endpoint).json()['error'] == 'SOURCE_CHANGED'
    header.write_bytes(saved)
    assert client.get(endpoint).status_code == 200 and len(calls) == 3


def test_real_pe_feature_determinism_dispersion_corr_and_candidate_shape(tmp_path, monkeypatch):
    from spectrumagent.api.registry import DatasetRegistry
    from spectrumagent.display import falsecolor
    header = Path((Path(__file__).resolve().parents[2]/'milestone04/evidence/calibration/cubes_11.txt').read_text('utf-8').splitlines()[0])
    if not header.is_file():
        pytest.skip('real pe cube from cubes_11.txt is unavailable')
    registry = DatasetRegistry(tmp_path/'real.sqlite')
    record = registry.import_path(str(header)).datasets[0]
    ds, _ = registry.readable(record.id, raw=False)
    shapes = []
    original = falsecolor.np.corrcoef
    def tracked(x):
        shapes.append(x.shape)
        return original(x)
    monkeypatch.setattr(falsecolor.np, 'corrcoef', tracked)
    results = [select_feature_bands(ds, ds.shape, ds.wavelengths) for _ in range(3)]
    assert results[0] == results[1] == results[2]
    r, g, b, fallback = results[0]
    assert not fallback and b < g < r
    assert ds.wavelengths[r]-ds.wavelengths[b] >= .15*(ds.wavelengths[-1]-ds.wavelengths[0])
    stride = max(1, math.ceil(ds.shape[0]/128))
    sample = ds.read_subimage(list(range(0, ds.shape[0], stride)), list(range(0, ds.shape[1], stride)), list(range(ds.shape[2])))
    rho = sample.std(axis=(0, 1))/(np.diff(sample, axis=1).std(axis=(0, 1))/np.sqrt(2)+1e-12)
    candidates = np.flatnonzero(rho >= np.median(rho))
    assert all(shape == (len(candidates), sample.shape[0]*sample.shape[1]) for shape in shapes)
    corr = np.abs(original(sample[:, :, [r, g, b]].reshape(-1, 3).T))
    assert corr[np.triu_indices(3, 1)].max() < .75
