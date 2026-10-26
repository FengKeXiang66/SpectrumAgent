"""TASK-08 classification preflight and sample-level PLS regression."""
from spectrumagent.data import DataError


class ModelingError(DataError):
    status_code = 400


from .metrics import REGRESSION_METRICS

__all__ = ["ModelingError", "REGRESSION_METRICS"]
