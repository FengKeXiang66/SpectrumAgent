"""Sample PLS with fold-fitted recipes and a replayable training snapshot."""
import hashlib
import platform
from pathlib import Path

import numpy as np

from spectrumagent.preprocess.fitted import fit, transform
from . import ModelingError

PROTOCOL = 'sample_pls_foldwise_v1'
LEGACY_PROTOCOL = 'sample_pls_full_fit_legacy'


def select(data, train, inner, *, n_components, max_components):
    from sklearn.cross_decomposition import PLSRegression

    X, y, ids = data['X_raw'], data['y'], data['groups']
    pipeline, axis = data['meta']['cubes'][0]['pipeline'], data['wavelengths']
    folds, states, maximum = [], [], X.shape[1]
    for fold in inner:
        a, b = train[fold['train_idx']], train[fold['test_idx']]
        state = fit(X[a], pipeline, wavelengths=axis, sample_ids=ids[a].tolist())
        A, B = transform(state, pipeline, X[a]), transform(state, pipeline, X[b])
        maximum = min(maximum, len(a)-1, A.shape[1], int(np.linalg.matrix_rank(A-A.mean(axis=0))))
        folds.append((A, B, y[a], y[b]))
        states.append({'fold_index': fold['fold_index'], 'train_cube_ids': ids[a].tolist(),
                       'validation_cube_ids': ids[b].tolist(), 'preprocessing': state})
    if max_components is not None:
        maximum = min(maximum, max_components)
    if maximum < 1 or n_components is not None and not 1 <= n_components <= maximum:
        raise ModelingError('INVALID_LV', 'LV 超出至少一折的训练样品数、特征数或训练特征秩', maximum=maximum)
    curve = []
    for lv in range(1, maximum+1):
        errors, fold_rmse = [], []
        for A, B, y_a, y_b in folds:
            estimator = PLSRegression(n_components=lv).fit(A, y_a)
            residual = finite(estimator.predict(B).reshape(-1)-y_b)
            errors.extend((residual**2).tolist())
            fold_rmse.append(float(np.sqrt(np.mean(residual**2))))
        curve.append({'n_components': lv, 'lv': lv, 'rmsecv': float(np.sqrt(np.mean(errors))),
                      'sd': float(np.std(fold_rmse, ddof=1)) if len(inner) > 1 else 0.})
    best = min(curve, key=lambda row: (row['rmsecv'], row['n_components']))
    elbow = next(row['n_components'] for row in curve if row['rmsecv'] <= best['rmsecv']+best['sd'])
    selected = n_components if n_components is not None else best['n_components']
    sweep = {'curve': curve, 'best_lv': best['n_components'], 'elbow_lv': elbow, 'selected_lv': selected,
             'by_cv_min': best['n_components'], 'by_elbow': elbow, 'manual_override': n_components is not None,
             'training_protocol': PROTOCOL,
             'definition': 'training-fold fitted preprocessing; pooled held-out RMSECV; elbow <= best RMSECV + one SD'}
    return sweep, states


def final_fit(data, train, test, selected, run_id):
    from sklearn.cross_decomposition import PLSRegression
    import scipy
    import sklearn

    X, y, ids = data['X_raw'], data['y'], data['groups']
    members = data['meta']['cubes']
    pipeline = members[0]['pipeline']
    state = fit(X[train], pipeline, wavelengths=data['wavelengths'], sample_ids=ids[train].tolist())
    A, B = transform(state, pipeline, X[train]), transform(state, pipeline, X[test])
    if selected > min(len(train)-1, A.shape[1], np.linalg.matrix_rank(A-A.mean(axis=0))):
        raise ModelingError('INVALID_LV', '最终训练特征秩不足以支持所选 LV')
    estimator = PLSRegression(n_components=selected).fit(A, y[train])
    model = {'kind': 'PLSRegression', 'selected_lv': selected, 'coef': estimator.coef_.tolist(),
             'intercept': estimator.intercept_.tolist(), 'x_mean': estimator._x_mean.tolist(),
             'parameters': estimator.get_params()}
    calibration, prediction = predict(A, model), predict(B, model)
    for features, actual in ((A, calibration), (B, prediction)):
        if not np.allclose(actual, estimator.predict(features).ravel(), rtol=1e-10, atol=1e-12):
            raise ModelingError('CALIBRATION_MISMATCH', '冻结的 PLS 参数不能重放训练结果')
    residual = calibration-y[train]
    mean, sd = float(residual.mean()), float(residual.std(ddof=1)) if len(train) > 1 else None
    preprocess_root = Path(__file__).resolve().parents[1] / 'preprocess'
    code_files = [preprocess_root/'fitted.py', *sorted((preprocess_root/'operators').glob('*.py'))]
    state.update(training_protocol=PROTOCOL, origin='training_snapshot', training_run_id=run_id,
        input_stage='raw_sample_mean', model=model, wavelengths=data['wavelengths'].tolist(),
        probe=X[train[0]].tolist(), feature_min=A.min(axis=0).tolist(), feature_max=A.max(axis=0).tolist(),
        source_hashes=[{'cube_id': m['cube_id'], **m['source_hashes']} for m in members],
        recipe_version_ids=sorted({m['recipe_version_id'] for m in members}),
        environment={'python': platform.python_version(), 'numpy': np.__version__,
                     'scipy': scipy.__version__, 'sklearn': sklearn.__version__},
        code_sha256={p.relative_to(preprocess_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in code_files},
        residual_interval={'mean': mean, 'sd': sd, 'low': None if sd is None else mean-sd,
                           'high': None if sd is None else mean+sd, 'ddof': 1, 'scope': 'global_calibration_residual'},
        limitation='训练时冻结的样品均值谱预处理及 PLS 状态；像素级预测为域外外推。',
        provenance={'fit_scope': 'sample_mean', 'fit_sample_count': len(train), 'fitted_on': 'training',
                    'train_cube_ids': ids[train].tolist(),
                    'source_preprocess_run_ids': [data['preprocess_run_ids'][i] for i in train],
                    'source_input_fingerprints': [members[i]['input_fingerprint'] for i in train],
                    'report_fit_scope': 'labeled_pixels', 'distinct_fit_populations': True,
                    'non_interchangeable_reason': '模型状态在训练样品均值谱拟合，不使用逐像素报告的拟合状态。'})
    return model, state, calibration, prediction


def check_provenance(state):
    """Fail closed for a new snapshot; legacy provenance has a separate reader."""
    try:
        p = state['provenance']
        ids = state['fit_sample_ids']
        if (state['origin'] != 'training_snapshot' or state['training_protocol'] != PROTOCOL
                or state['input_stage'] != 'raw_sample_mean' or not isinstance(ids, list) or not ids
                or any(not isinstance(v, str) or not v for v in ids)
                or len(set(ids)) != len(ids) or p['train_cube_ids'] != ids
                or p['fitted_on'] != 'training' or p['fit_scope'] != 'sample_mean'
                or type(p['fit_sample_count']) is not int or p['fit_sample_count'] != len(ids) or p['report_fit_scope'] != 'labeled_pixels'
                or p['distinct_fit_populations'] is not True or not p['non_interchangeable_reason']
                or not isinstance(state['training_run_id'], str) or not state['training_run_id']):
            raise ValueError()
        for key in ('source_preprocess_run_ids', 'source_input_fingerprints'):
            if len(p[key]) != len(ids) or any(not isinstance(v, str) or not v for v in p[key]):
                raise ValueError()
    except (KeyError, TypeError, ValueError) as error:
        raise ModelingError('CALIBRATION_PROVENANCE_UNAVAILABLE', '训练状态的拟合来源不完整或不一致') from error


def verify_snapshot(state, replay, predictions, model, *, run_id, train_ids, test_ids):
    check_provenance(state)
    try:
        ids = replay['cube_ids']
        raw = np.asarray(replay['X_raw'], dtype=float)
        truth = np.asarray(replay['y'], dtype=float)
        members = replay['members']
        if (state['training_run_id'] != run_id or state['model'] != model
                or state['fit_sample_ids'] != train_ids or set(train_ids) & set(test_ids)
                or not train_ids or not test_ids or len(set(train_ids)) != len(train_ids)
                or len(set(test_ids)) != len(test_ids)
                or len(ids) != len(set(ids)) or set(ids) != set(train_ids) | set(test_ids)
                or raw.shape != (len(ids), state['input_n_features']) or truth.shape != (len(ids),)
                or not np.isfinite(truth).all() or len(members) != len(ids)
                or [m['cube_id'] for m in members] != ids or len(replay['preprocess_run_ids']) != len(ids)
                or len(predictions) != len(ids) or [r['cube_id'] for r in predictions] != ids):
            raise ValueError()
        positions = [ids.index(cube) for cube in train_ids]
        provenance = state['provenance']
        if (provenance['source_preprocess_run_ids'] != [replay['preprocess_run_ids'][i] for i in positions]
                or provenance['source_input_fingerprints'] != [members[i]['input_fingerprint'] for i in positions]
                or any(m['pipeline'] != state['pipeline'] for m in members)
                or state['recipe_version_ids'] != sorted({m['recipe_version_id'] for m in members})):
            raise ValueError()
        features = transform(state, state['pipeline'], replay['X_raw'])
        if features.shape != (len(ids), state['output_n_features']):
            raise ValueError()
        values = predict(features, model)
        expected = np.asarray([row['y_pred'] for row in predictions])
        if not np.array_equal(values, expected):
            raise ValueError()
        for row, truth in zip(predictions, replay['y']):
            role = 'calibration' if row['cube_id'] in train_ids else 'prediction'
            if row['y_true'] != truth or row['set'] != role or row['residual'] != row['y_pred']-truth:
                raise ValueError()
    except (KeyError, TypeError, ValueError) as error:
        raise ModelingError('CALIBRATION_MISMATCH', '训练快照不能重放已保存的逐样品预测') from error


def finite(value):
    if not np.isfinite(value).all():
        raise ModelingError('NON_FINITE_SPECTRA', '回归输入或预测含非有限数值')
    return value


def predict(x, model):
    """PLS 1.9.1 formula, flattened and independent of IO block dimensions."""
    try:
        x = finite(np.asarray(x, dtype=np.float64))
        coef, mean, intercept = (np.asarray(model[key], dtype=np.float64)
                                 for key in ("coef", "x_mean", "intercept"))
        if (x.ndim != 2 or coef.shape != (1, x.shape[1])
                or mean.shape != (x.shape[1],) or intercept.shape != (1,)):
            raise ModelingError("FEATURE_COUNT_MISMATCH", "像素特征数与模型不一致")
        finite(coef); finite(mean); finite(intercept)
        return finite(np.asarray([((row - mean) @ coef.T + intercept).ravel()[0] for row in x])).ravel()
    except (KeyError, TypeError, ValueError) as error:
        raise ModelingError("INVALID_MODEL_ARTIFACT", "模型系数产物无效") from error

