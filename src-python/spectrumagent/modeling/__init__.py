"""TASK-08 modeling foundation; preflight only, no fitted models."""
from spectrumagent.data import DataError


class ModelingError(DataError):
    status_code = 400


__all__ = ["ModelingError"]
