"""Training-only fitted transformations with a serializable parameter definition."""
import numpy as np
from scipy.signal import savgol_filter
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from spectrumagent.data import DataError


class SpectralPipeline:
    def __init__(self, steps):
        self.steps = steps
        self.fitted = None

    @staticmethod
    def _step(X, step, fitted=None):
        if step.op == "savgol":
            X = savgol_filter(X, step.window, step.polyorder, deriv=step.derivative,
                              delta=step.delta_nm, mode=step.mode, axis=1)
        elif step.op == "l2":
            norm = np.linalg.norm(X, axis=1, keepdims=True)
            X = X / np.where(norm > step.epsilon, norm, 1.)
        elif step.op == "snv":
            std = X.std(axis=1, ddof=step.ddof, keepdims=True)
            if np.any(std <= 1e-12):
                raise DataError("EXPERIMENT_DEGENERATE", "SNV包含零方差光谱")
            X = (X-X.mean(axis=1, keepdims=True))/std
        else:
            if fitted is None:
                fitted = (PCA(n_components=step.n_components, svd_solver="full") if step.op == "pca"
                          else StandardScaler(with_std=step.op == "standard_scale"))
                fitted.fit(X)
            X = fitted.transform(X)
        if not np.isfinite(X).all():
            raise DataError("EXPERIMENT_DEGENERATE", "预处理产生非有限数值", op=step.op)
        return X, fitted

    def fit_transform(self, X):
        X = np.asarray(X, dtype=np.float64)
        self.fitted = []
        for step in self.steps:
            X, fitted = self._step(X, step)
            self.fitted.append(fitted)
        return X

    def transform(self, X):
        if self.fitted is None or len(self.fitted) != len(self.steps):
            raise DataError("EXPERIMENT_MODEL_INVALID", "预处理尚未拟合")
        X = np.asarray(X, dtype=np.float64)
        for step, fitted in zip(self.steps, self.fitted):
            if step.op in {'center','standard_scale','pca'} and fitted is None:
                raise DataError('EXPERIMENT_MODEL_INVALID', '归档预处理缺少训练时拟合参数，拒绝在推理数据上重新拟合')
            X, _ = self._step(X, step, fitted)
        return X
