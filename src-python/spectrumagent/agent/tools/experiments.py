"""Typed conversational patches; spectra and local paths stay in the service."""
from typing import Annotated, Literal, Union

from pydantic import Field, FiniteFloat, model_validator

from . import ToolInput, NoArguments, Reference
from ..tool_context import owner_session
from spectrumagent.experiments.schema import L2, Center, Standard, SNV, Metric


class ArchiveDraft(ToolInput):
    kind: Literal['npz']
    source_refs: list[Reference] | None = None
    spectra_key: str | None = None
    labels_key: str | None = None
    wavelengths_key: str | None = None
    groups_key: str | None = None
    input_stage: Literal['spectra', 'neighborhood_mean'] | None = None
    neighborhood: int | None = None
    evaluation_unit: Literal['spectrum', 'center_pixel'] | None = None


class ImageReference(ToolInput):
    header_ref: Reference
    roi_ref: Reference
    sample_id: Reference
    batch: Reference | None = None
    data_ref: Reference | None = None
    centers_ref: Reference | None = None


class QualityDraft(ToolInput):
    min_mean: FiniteFloat | None = None
    min_std: FiniteFloat | None = None
    max_zero_fraction: FiniteFloat | None = None
    saturation: FiniteFloat | None = None


class ImageDraft(ToolInput):
    kind: Literal['roi_images']
    members: list[ImageReference] | None = None
    neighborhood: int | None = None
    sampling_stride: Annotated[int, Field(ge=1)] | None = None
    max_per_class: Annotated[int, Field(ge=1)] | None = None
    sampling_seed: Annotated[int, Field(ge=0, le=2**32-1)] | None = None
    wavelength_unit: Literal['nm', 'um'] | None = None
    mapping_window_nm: FiniteFloat | None = None
    nearest_tolerance_nm: FiniteFloat | None = None
    quality: QualityDraft | None = None
    evaluation_unit: Literal['center_pixel'] | None = None


class SGDraft(ToolInput):
    op: Literal['savgol']
    window: int | None = None
    polyorder: int | None = None
    derivative: int | None = None
    delta_nm: FiniteFloat | None = None
    mode: Literal['interp', 'mirror', 'constant', 'nearest', 'wrap'] | None = None


class ModelDraft(ToolInput):
    n_components: int | None = None
    scale: bool | None = None
    max_iter: int | None = None
    tol: FiniteFloat | None = None


class PCADraft(ToolInput):
    op: Literal['pca']
    n_components: int | None = None


class ClassName(ToolInput):
    label: int
    name: Reference


class ArchiveAxis(ToolInput):
    kind: Literal['archive']
    role: Literal['train', 'test']


class CropAxis(ToolInput):
    kind: Literal['crop']
    start_nm: FiniteFloat
    stop_nm: FiniteFloat

    @model_validator(mode='after')
    def increasing(self):
        if self.start_nm >= self.stop_nm:
            raise ValueError('裁剪终点须大于起点')
        return self


class UnappliedRequest(ToolInput):
    topic: Literal['wavelength_crop', 'wavelength_grid', 'savgol', 'preprocessing', 'sampling', 'split', 'metrics', 'other']
    requested: Annotated[str, Field(min_length=1, max_length=300, description='用户请求摘要，省略本地路径')]
    reason: Annotated[str, Field(min_length=1, max_length=300)]

    @model_validator(mode='after')
    def path_free_feedback(self):
        from spectrumagent.experiments.conversation import PATHS
        if any(PATHS.search(value) or '\\\\' in value for value in (self.requested, self.reason)):
            raise ValueError('未生效项的摘要与原因须省略本机路径')
        return self


class GridAxis(ToolInput):
    kind: Literal['grid']
    start_nm: FiniteFloat
    stop_nm: FiniteFloat
    step_nm: Annotated[FiniteFloat, Field(gt=0)]


PreprocessingStep = Annotated[Union[SGDraft, L2, Center, Standard, SNV, PCADraft], Field(discriminator='op')]


class PreprocessingEdit(ToolInput):
    action: Literal['update', 'insert', 'remove']
    index: Annotated[int, Field(ge=1, description='从 1 开始的步骤序号；插入放在该位置')]
    step: PreprocessingStep | None = Field(default=None, description='修改同一算子时合并参数；换成另一算子时替换该步')

    @model_validator(mode='after')
    def step_required(self):
        if (self.step is None) != (self.action == 'remove'):
            raise ValueError('修改或插入须提供步骤，删除只需要序号')
        return self


class DraftUpdate(ToolInput):
    expected_revision: Annotated[int, Field(ge=0)]
    reset: bool = False
    name: str | None = None
    train: Annotated[Union[ArchiveDraft, ImageDraft], Field(discriminator='kind')] | None = None
    test: Annotated[Union[ArchiveDraft, ImageDraft], Field(discriminator='kind')] | None = None
    classes: list[ClassName] | None = None
    preprocessing: list[PreprocessingStep] | None = None
    preprocessing_edit: PreprocessingEdit | None = None
    model: ModelDraft | None = None
    axis: Annotated[Union[ArchiveAxis, GridAxis, CropAxis], Field(discriminator='kind')] | None = None
    unapplied_requests: list[UnappliedRequest] | None = None
    additional_metrics: list[Metric] | None = None
    test_usage: Literal['independent_test', 'development_regression'] | None = None

    @model_validator(mode='after')
    def one_preprocessing_operation(self):
        if self.preprocessing_edit is not None and (self.reset or 'preprocessing' in self.model_fields_set):
            raise ValueError('局部修改不能与重置或替换预处理清单同时使用')
        return self


class InspectInput(ToolInput):
    source_ref: Reference


class HistoryPage(ToolInput):
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=20)] = 10


class SelectExperiment(ToolInput):
    experiment_id: Reference


class CompareExperiments(ToolInput):
    first_id: Reference
    second_id: Reference


def register_experiments(registry, dialogue):
    registry.experiment_dialogue = dialogue
    from .inference import register_inference
    register_inference(registry,dialogue.inference)
    registry.register('experiments.history_list', HistoryPage,
                      '分页列出跨应用重启保留的显式训练测试实验；仅返回编号、状态与指标摘要，无路径和谱值',
                      lambda args: dialogue.history_list(args.offset, args.limit))
    registry.register('experiments.history_select', SelectExperiment,
                      '根据已列出的真实实验编号，在本会话选中历史实验并展示原始保存结果；不启动训练或推理',
                      lambda args: dialogue.select(owner_session.get(), args.experiment_id))
    registry.register('experiments.history_compare', CompareExperiments,
                      '并列核对两个成功实验的指标和输入、划分、评价单位一致性；口径不同不可直接判断优劣，不自动选参',
                      lambda args: dialogue.compare(args.first_id, args.second_id))
    registry.register('experiments.draft_get', NoArguments,
                      '读取本会话的训练测试实验草稿、修订号、方案与待补字段',
                      lambda args: dialogue.view(owner_session.get()))
    registry.register('experiments.input_inspect', InspectInput,
                      '检查用户提供的输入源引用；只返回文件类型、NPZ字段及维度，不返回谱值、路径或材质猜测',
                      lambda args: dialogue.inspect(owner_session.get(), args.source_ref))
    registry.register('experiments.draft_update', DraftUpdate,
                      '增量保存用户明确给出的实验信息，不启动计算。局部改预处理用 preprocessing_edit（从 1 开始）；'
                      'preprocessing 和 classes 整组替换，仅用于明确提供整组时。'
                      'SG缺参允许留空以便追问。改变步骤时保留已确认参数，reset仅用于用户要求新实验。',
                      lambda args: dialogue.update(owner_session.get(), args))
