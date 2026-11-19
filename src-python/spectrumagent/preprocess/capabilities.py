"""Explicit publication policy; registering an operator does not expose it to AI."""
import os

UI_OPERATORS = ('snv', 'sg_smooth', 'sg_derivative', 'standardize',
                'crop', 'resample', 'pca', 'mnf', 'ica', 'continuum')
_LEGACY_AI_OPERATORS = ('snv', 'sg_smooth', 'sg_derivative', 'standardize')
# 开发期放开：AI 与界面共享全部算子目录；SPECTRUMAGENT_OPEN_ACCESS=0 可恢复原白名单。
AI_OPERATORS = UI_OPERATORS if os.environ.get('SPECTRUMAGENT_OPEN_ACCESS', '1') != '0' else _LEGACY_AI_OPERATORS


def capabilities(registry):
    result = []
    for name in UI_OPERATORS:
        entry = registry.resolve(name, 1)
        constraints, conditions = [], []
        if name.startswith('sg_'):
            constraints = ['window 为正奇数', 'polyorder 为非负整数且严格小于 window',
                           'mode 默认为 interp']
            if name == 'sg_derivative':
                constraints.append('order 为 1 或 2')
            conditions = ['interp 模式的 window 不得超过该步骤输入的有效 bands']
        elif name in {'crop', 'resample'}:
            conditions = ['需要当前有效波长轴；轴来源由界面核验，不能猜测']
        elif name in {'pca', 'mnf', 'ica'}:
            conditions = ['n_components 不得超过输入维数及有效拟合样本容量']
        result.append({'op': name, 'version': 1, 'ai_enabled': name in AI_OPERATORS,
                       'params_schema': entry.params_schema, 'parameter_constraints': constraints,
                       'data_conditions': conditions})
    return result
