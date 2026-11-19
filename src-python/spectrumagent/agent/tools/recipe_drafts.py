"""Controlled recipe editing. Owner and authorization come from server context."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from spectrumagent.data import DataError
from spectrumagent.preprocess import submissions
from ..tool_context import owner_session
from ..open_access import OPEN_ACCESS
from . import Reference, ToolInput


class GetDraft(ToolInput):
    draft_id: Reference | None = None
    source_recipe_version_id: Reference | None = None
    new_plan: bool = False


class DraftStep(ToolInput):
    op: Literal['snv','sg_smooth','sg_derivative','standardize',
                'crop','resample','pca','mnf','ica','continuum']
    version: Annotated[int,Field(ge=1)]
    window: int | None = None
    polyorder: int | None = None
    order: int | None = None
    mode: Literal['interp','mirror','constant','nearest','wrap'] | None = None
    zero_std: Literal['zeros','nan','error'] | None = None
    method: Literal['standard','minmax','area','vector',
                    'linear','spline','convex_hull'] | None = None
    n_components: int | None = None
    random_state: int | None = None
    source: list[float] | None = None
    target: list[float] | None = None
    range: list[float] | None = None


class StepUpdate(ToolInput):
    step_no: Annotated[int,Field(ge=1,le=30)]
    window: int | None = None
    polyorder: int | None = None
    order: int | None = None
    mode: Literal['interp','mirror','constant','nearest','wrap'] | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_dump(exclude={'step_no'},exclude_none=True):
            raise ValueError('请给出至少一个要修改的步骤参数')
        return self


class UpdateDraft(ToolInput):
    draft_id: Reference
    expected_revision: Annotated[int,Field(gt=0)]
    steps: Annotated[list[DraftStep],Field(max_length=30)] | None = None
    step_updates: Annotated[list[StepUpdate],Field(min_length=1,max_length=30)] | None = None
    code: Annotated[str,Field(max_length=64,pattern=r'^[a-z0-9][a-z0-9-]*$')] | None = None
    name: Annotated[str,Field(min_length=1,max_length=80)] | None = None
    description: Annotated[str,Field(max_length=2000)] | None = None
    note: Annotated[str,Field(max_length=2000)] | None = None
    axis_cube_id: Reference | None = None

    @model_validator(mode='after')
    def one_step_action(self):
        if self.steps is not None and self.step_updates is not None:
            raise ValueError('steps整表替换与step_updates局部修改不能混用')
        if self.step_updates and len({s.step_no for s in self.step_updates})!=len(self.step_updates):
            raise ValueError('同一步骤的参数请合并到一次修改')
        return self


class SaveDraft(ToolInput):
    draft_id: Reference
    expected_revision: Annotated[int,Field(gt=0)]
    recipe_id: Reference | None = None
    code: Annotated[str,Field(max_length=64,pattern=r'^[a-z0-9][a-z0-9-]*$')] | None = None
    name: Annotated[str,Field(min_length=1,max_length=80)] | None = None
    description: Annotated[str,Field(max_length=2000)] | None = None
    note: Annotated[str,Field(max_length=2000)] | None = None


class Member(ToolInput):
    cube_id: Reference
    annotation_version_id: Reference
    recipe_version_id: Reference


class ConfirmDraft(ToolInput):
    draft_id: Reference
    expected_revision: Annotated[int,Field(gt=0)]
    recipe_version_id: Reference
    inputs: Annotated[list[Member],Field(min_length=1,max_length=32)]


class ExecuteDraft(ToolInput):
    confirmation_id: Reference
    inputs: Annotated[list[Member],Field(min_length=1,max_length=32)]


class RecipeRef(ToolInput):
    recipe_id: Reference


def _owner():
    owner = owner_session.get()
    if owner is None:
        raise DataError('DRAFT_OWNER_REQUIRED','草稿工具需要本轮服务端会话上下文')
    return owner


def summary(draft):
    result = {k:draft[k] for k in ('draft_id','revision','source_recipe_version_id','updated_at')}
    result['validation_valid'] = draft['validation_result']['valid']
    result['step_count'] = len(draft['pipeline']['steps'])
    result.update({f'metadata_{key}':value for key,value in draft.get('metadata',{}).items()})
    legacy = {'snv','sg_smooth','sg_derivative','standardize'}
    for index,step in enumerate(draft['pipeline']['steps'][:256],1):
        allowed = step['op'] in (legacy | {'crop','resample','pca','mnf','ica','continuum'} if OPEN_ACCESS else legacy)
        result[f'step_{index}_op'] = step['op'] if allowed else 'unsupported'
        result[f'step_{index}_version'] = step['version']
        if allowed:
            for key,value in step['params'].items():
                numeric=key in {'window','polyorder','order','n_components','random_state'} and type(value) is int
                enum=key in {'mode','zero_std','method'} and value in {
                    'mode':('interp','mirror','constant','nearest','wrap'),
                    'zero_std':('zeros','nan','error'),
                    'method':('standard','minmax','area','vector','linear','spline','convex_hull')}[key]
                if numeric or enum:
                    result[f'step_{index}_{key}'] = value
                elif allowed and key in {'source','target','range'} and isinstance(value,list):
                    result[f'step_{index}_{key}_count']=len(value)
                    for j,item in enumerate(value[:512],1):
                        result[f'step_{index}_{key}_{j}']=item
    for index,field in enumerate(draft['validation_result'].get('fields',[])[:256],1):
        result[f'validation_{index}_field'] = field['field']
        result[f'validation_{index}_message'] = field['message']
    for index,change in enumerate(draft.get('differences',[])[:256],1):
        result[f'difference_{index}'] = change['field'] + ':' + change['change']
    return result


def register_draft_operations(registry,runner):
    def get(args):
        row = runner.drafts.get(_owner(),args.draft_id) if args.draft_id else runner.drafts.create(
            _owner(),args.source_recipe_version_id,new_plan=args.new_plan)
        return summary(row)

    def update(args):
        pipeline = None if args.steps is None else {'steps':[
            {'op':s.op,'version':s.version,'params':s.model_dump(exclude={'op','version'},exclude_none=True)} for s in args.steps]}
        if args.step_updates:
            pipeline=runner.drafts.get(_owner(),args.draft_id)['pipeline']
            for patch in args.step_updates:
                if patch.step_no>len(pipeline['steps']):
                    raise DataError('INVALID_REQUEST','指定步骤不存在，请读取当前草稿后再修改')
                pipeline['steps'][patch.step_no-1]['params'].update(patch.model_dump(exclude={'step_no'},exclude_none=True))
        if pipeline is not None and args.axis_cube_id:
            dataset,_=runner.registry.get(args.axis_cube_id)
            axis=list(dataset.wavelengths) if dataset.wavelengths is not None else None
            for step in pipeline['steps']:
                params=step['params']
                if step['op'] in {'crop','resample'} and 'source' not in params:
                    if not axis:raise DataError('INVALID_REQUEST','该步骤没有有效波长轴，不能补入source')
                    params['source']=axis.copy()
                if step['op']=='crop' and axis and 'range' in params:
                    bounds=params['range']
                    if len(bounds)==2:axis=[v for v in axis if bounds[0]<=v<=bounds[1]]
                elif step['op']=='resample':axis=params.get('target')
                elif step['op'] in {'pca','mnf','ica'}:axis=None
        metadata = args.model_dump(include={'code','name','description','note'},exclude_none=True)
        return summary(runner.drafts.update(_owner(),args.draft_id,args.expected_revision,pipeline,metadata))

    def save(args):
        result = runner.drafts.save(_owner(),**args.model_dump())
        return {key:value for key,value in result.items() if key != 'recipe_hash_alg'}

    def confirm(args):
        data = args.model_dump()
        return runner.drafts.confirm(_owner(),**data,authorization_source=submissions.context().authorization_source)

    def execute(args):
        result = runner.drafts.execute(runner,_owner(),args.confirmation_id,[m.model_dump() for m in args.inputs])
        if result.get('diagnostics'):
            diagnostic=result['diagnostics'][0]
            raise DataError(diagnostic['error'],diagnostic['detail'],fields=diagnostic['fields'],
                            run_id=diagnostic['run_id'],completed_count=result['succeeded'])
        from . import check_run_error
        for item in result['items']:
            if item['run_id']:
                check_run_error(runner.get(item['run_id']),completed_count=result['succeeded'])
        out = {'succeeded':result['succeeded'],'failed':result['failed'],'truncated':False}
        for i,row in enumerate(result['items'],1):
            out.update({f'item_{i}_{key}':value for key,value in row.items()})
        return out

    def deleted(args,value):
        row = runner.recipes.set_deleted(args.recipe_id,value)
        return {'recipe_id':row['id'],'deleted':row['deleted'],'status':'deleted' if value else 'restored'}

    entries = [
        ('preprocess.draft_get',GetDraft,'读取会话共享配方草稿；新方案可 new_plan=true；不保存正式版本',get),
        ('preprocess.draft_update',UpdateDraft,'以expected_revision更新共享草稿。steps为完整替换，不能遗漏已确认参数；补改SG参数优先step_updates，例如step_no=2、window=9、polyorder=3，保留其他步骤。description只是说明，不会修改实际参数。冲突先读最新修订',update),
        ('preprocess.draft_save',SaveDraft,'用户明确保存时把有效草稿另存新配方或追加指定配方版本；不执行',save),
        ('preprocess.draft_confirm',ConfirmDraft,'用户明确执行时绑定已保存版本、当前草稿修订及全部固定输入；引用不得来自未经确认的候选最新项',confirm),
        ('preprocess.draft_execute',ExecuteDraft,'按本轮执行确认和相同完整输入运行；定义或范围改变必须重新绑定',execute),
        ('preprocess.recipe_delete',RecipeRef,'用户明确删除配方时软删除；本次运行内隐藏普通入口，历史仍可读',lambda a:deleted(a,True)),
        ('preprocess.recipe_restore',RecipeRef,'用户明确恢复指定已删除配方；不自动复活模板',lambda a:deleted(a,False)),
    ]
    for name,arguments,description,handler in entries:
        registry.register(name,arguments,description,handler if runner is not None else None)
