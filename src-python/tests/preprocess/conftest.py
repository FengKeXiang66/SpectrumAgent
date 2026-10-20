import numpy as np
import pytest

from spectrumagent.preprocess import builtin_registry


@pytest.fixture
def registry():
    return builtin_registry()


@pytest.fixture
def reference():
    # A non-polynomial fixture: full rank for ref + constant + t + t².
    t = np.linspace(0., 1., 21)
    return np.sin(7*t) + .3*np.cos(11*t) + 2


def run(registry, name, x, params=None, **kwargs):
    return registry.run(x, {"steps": [{"op": name, "version": 1, "params": params or {}}]}, **kwargs)
