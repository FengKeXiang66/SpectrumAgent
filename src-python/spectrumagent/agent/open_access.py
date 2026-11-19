"""开发期总开关：先放开 AI 的全部操作能力，约束在项目收尾阶段统一加回。

默认 OPEN_ACCESS=True，编排层跳过权限门、成员上限、调用预算和引用话术要求。
设环境变量 SPECTRUMAGENT_OPEN_ACCESS=0 可即时恢复 A–D 基线的全部约束
（用于回归对照）；项目收尾时把默认值改为 '0' 即可，无需逐处改回代码。
"""
import os

OPEN_ACCESS = os.environ.get('SPECTRUMAGENT_OPEN_ACCESS', '1') != '0'

MAX_MEMBERS = 256 if OPEN_ACCESS else 5
MAX_TOOL_CALLS = 256 if OPEN_ACCESS else 8
MAX_WORKFLOW_BATCHES = 128 if OPEN_ACCESS else 16
MAX_WORKFLOW_STEPS = 512 if OPEN_ACCESS else 32
