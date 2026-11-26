"""Conversation tools that operate directly on current workspace data."""
from typing import Annotated
from pydantic import Field
from spectrumagent.data import DataError
from spectrumagent.preprocess.current import CurrentWorkspace
from . import ToolInput, CubeArguments, check_run_error


class CurrentPage(ToolInput):
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 32


class ProcessCurrent(ToolInput):
    cube_ids: Annotated[list[str], Field(min_length=1, max_length=32)]
    recipe_id: str


class EditCurrentRecipe(ToolInput):
    recipe_id: str


class TrainCurrent(ToolInput):
    cube_ids: Annotated[list[str], Field(min_length=2)]
    cv_folds: Annotated[int, Field(ge=2)] = 5
    seed: int = 17
    confidence_threshold: Annotated[float, Field(ge=0, lt=1)] = 0
    n_components: Annotated[int, Field(ge=1, le=20)] | None = None


def register_current(registry, sessions, runner):
    # Remove executable historical tools too: old pinned conversations cannot
    # resurrect a version, freeze a set, or execute a stale confirmation.
    obsolete = {'annotations.draft_confirm','training_mat.export','preprocess.run','preprocess.compare',
                'preprocess.run_default','preprocess.run_batch','preprocess.recipe_version_add',
                'preprocess.draft_confirm','preprocess.draft_execute','modeling.preflight','modeling.classify',
                'workspace.classify', 'labels.tree_preview', 'labels.tree_apply'}
    for name in list(registry._tools):
        if name in obsolete or name.startswith(('versions.', 'training_sets.')):
            del registry._tools[name]
    # Descriptions of retained editing tools describe the current-state contract.
    for name, description in {
        'preprocess.recipes':'列出当前配方定义；内部关联标识不是历史版本选择',
        'preprocess.recipe_create':'新建独立配方；修改已有配方使用共享草稿保存当前定义',
        'preprocess.draft_get':'读取或新建共享配方编辑草稿，revision仅用于防止并发覆盖',
        'preprocess.draft_save':'保存当前配方定义；给recipe_id覆盖该配方，不给时新建配方，不产生历史版本',
    }.items():
        if name in registry._tools:
            from dataclasses import replace
            registry._tools[name] = replace(registry._tools[name], description=description)
    if sessions is None or runner is None:
        return
    workspace = CurrentWorkspace(sessions, runner)

    def state(args):
        value = workspace.state()
        end = args.offset + args.limit
        out = {'sample_count':len(value['members']), 'recipe_count':len(value['recipes']), 'offset':args.offset,
               'truncated':end < max(len(value['members']), len(value['recipes'])), 'next_offset':end}
        for i,row in enumerate(value['members'][args.offset:end],1):
            for key in ('cube_id','status','run_id'):
                out[f'sample_{i}_{key}'] = row[key] or ''
        for i,row in enumerate(value['recipes'][args.offset:end],1):
            out.update({f'recipe_{i}_id':row['id'],f'recipe_{i}_name':row['name']})
        return out

    def save(args):
        row = sessions.save(args.cube_id)
        return {'cube_id':args.cube_id,'annotation_id':row['id'],'status':'saved', 'export_ok':row['export']['ok']}

    def edit_recipe(args):
        from .recipe_drafts import _owner, summary
        recipe = runner.recipes.get(args.recipe_id)
        draft = runner.drafts.create(_owner(),recipe['versions'][-1]['id'],new_plan=True)
        result = summary(draft)
        result.pop('source_recipe_version_id',None)
        return {**result,'recipe_id':recipe['id'],'recipe_name':recipe['name']}

    def process(args):
        from dataclasses import replace
        from spectrumagent.preprocess import submissions
        if len(set(args.cube_ids)) != len(args.cube_ids):
            raise DataError('INVALID_REQUEST','样品不能重复')
        out = {'count':len(args.cube_ids),'succeeded':0,'failed':0,'truncated':False}
        submission = submissions.context()
        for i,cube in enumerate(args.cube_ids,1):
            try:
                with submissions.execution_context(replace(submission,action_ref=f'{submission.action_ref}.{i}')):
                    row = workspace.process(cube,args.recipe_id)
                check_run_error(row)
                out.update({f'item_{i}_cube_id':cube,f'item_{i}_run_id':row['id'],f'item_{i}_status':'succeeded'})
                out['succeeded'] += 1
            except DataError as error:
                out.update({f'item_{i}_cube_id':cube,f'item_{i}_status':'failed',f'item_{i}_error':error.code})
                out['failed'] += 1
        out['status'] = 'succeeded' if not out['failed'] else 'partial' if out['succeeded'] else 'failed'
        return out

    def preflight(args):
        indexed = {row['cube_id']:row for row in workspace.state()['members']}
        if len(set(args.cube_ids)) != len(args.cube_ids) or any(indexed.get(cube,{}).get('status') != 'ready' for cube in args.cube_ids):
            raise DataError('NEED_PREPROCESS','选中的样品须先完成当前标注和预处理')
        rows = [indexed[cube] for cube in args.cube_ids]
        body = dict(cube_ids=args.cube_ids,annotation_version_ids=[row['annotation_id'] for row in rows],
                    preprocess_run_ids=[row['run_id'] for row in rows],task='classification',target='label',
                    cv_strategy='group_kfold',cv_folds=args.cv_folds,seed=args.seed,split_strategy='none',evaluation_protocol='nested_group_cv')
        result = registry.modeling.training.preflight(**body)
        return registry.modeling.training_summary(result['run_id'],result)

    registry.register('workspace.current',CurrentPage,'分页查询当前样品处理状态和可用配方；不需要版本或冻结训练集，truncated时按next_offset继续',state)
    registry.register('workspace.save_annotation',CubeArguments,'保存当前标注并聚合，替换原保存结果',save)
    registry.register('workspace.recipe_edit',EditCurrentRecipe,'按配方ID读取当前定义到共享编辑草稿；随后draft_update编辑、draft_save以同一recipe_id保存',edit_recipe)
    registry.register('workspace.preprocess',ProcessCurrent,'用指定配方处理选中的样品，自动保存当前标注；每次最多32项',process)
    registry.register('workspace.preflight',TrainCurrent,'仅应用户要求，对旧配方处理结果执行独立诊断；分类训练请使用统一实验方案',preflight)
