"""Conversation adapters over the same services used by the desktop UI.

Display replies contain references and display parameters only. Artifacts are
read by desktop components, never serialized into model context.
"""
from typing import Annotated, Literal
import json

from pydantic import Field
from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.preprocess import submissions
from ..tool_context import owner_session
from . import ToolInput, Reference, NoArguments, _run_summary


class Page(ToolInput):
    offset: Annotated[int, Field(ge=0)] = 0
    limit: Annotated[int, Field(ge=1, le=100)] = 32


class RunPage(Page):
    submission_reference: Reference | None = None
    cube_id: Reference | None = None
    run_ids: Annotated[list[Reference], Field(max_length=256)] | None = None


class ProjectPaths(ToolInput):
    project_id: Reference
    source_path: str
    output_root: str


class RecipeSelect(ToolInput):
    project_id: Reference
    recipe_id: Reference
    selected: bool = True


class TargetQuery(ToolInput):
    project_id: Reference | None = None


class TargetPut(ToolInput):
    cube_id: Reference
    schema_id: Reference
    value: float


class TargetImport(ToolInput):
    project_id: Reference
    csv_text: Annotated[str, Field(max_length=2*1024*1024)]
    overwrite: bool = False


class Regression(ToolInput):
    preprocess_run_ids: Annotated[list[Reference], Field(min_length=4, max_length=256)]
    target_schema_id: Reference
    split_strategy: Literal['ks'] = 'ks'
    test_ratio: Annotated[float, Field(gt=0, lt=1)] = 1/3
    cv_strategy: Literal['kfold', 'loo'] = 'kfold'
    cv_folds: Annotated[int, Field(ge=2)] = 5
    seed: int = 17
    n_components: Annotated[int, Field(ge=1)] | None = None
    max_components: Annotated[int, Field(ge=1)] | None = None


class LabelCreate(ToolInput):
    project_id: Reference
    name: Annotated[str, Field(min_length=1, max_length=80)]
    color_hex: Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')] = '#2563eb'


class LabelEdit(ToolInput):
    label_id: Reference
    name: str | None = None
    color_hex: Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')] | None = None
    shortcut_key: Annotated[int, Field(ge=0, le=9)] | None = None
    tree_path: str | None = None


class LabelRef(ToolInput):
    label_id: Reference


class LabelMerge(ToolInput):
    source_id: Reference
    target_id: Reference


class TreeScope(ToolInput):
    project_id: Reference
    root: Annotated[str,Field(min_length=1)]
    depth: Annotated[int,Field(ge=1,le=10)] = 1


class TreeCandidate(ToolInput):
    directory: Annotated[str,Field(min_length=1)]
    code: Annotated[str,Field(pattern=r'^[A-Z0-9_]{1,16}$')]
    name: Annotated[str,Field(min_length=1)]
    color_hex: Annotated[str,Field(pattern=r'^#[0-9a-fA-F]{6}$')]
    sample_count: Annotated[int,Field(ge=0)]
    reuse: bool
    needs_naming: bool
    confirmed: bool = False


class TreeApply(TreeScope):
    candidates: Annotated[list[TreeCandidate],Field(min_length=1,max_length=1000)]


class SampleLabels(ToolInput):
    project_id: Reference
    cube_ids: Annotated[list[Reference],Field(max_length=1000)] | None = None
    label_id: Reference | None = None


class SchemaCreate(ToolInput):
    project_id: Reference
    name: str
    tree_path: str
    unit: str | None = None


class Segmentation(ToolInput):
    cube_id: Reference
    n_segments: Annotated[int, Field(gt=0)] = 200
    compactness: Annotated[float, Field(gt=0)] = .5
    pca_components: Literal[3, 5] = 5
    force: bool = False


class TaskAction(ToolInput):
    task_id: Reference
    action: Literal['get', 'cancel', 'retry_failed', 'continue_remaining'] = 'get'


class Review(ToolInput):
    cube_id: Reference
    erase_superpixel: Annotated[int,Field(ge=0)] | None = None


class Display(ToolInput):
    view: Literal['dataset', 'spectrum', 'preprocess', 'compare', 'classification', 'regression',
                  'coefficients', 'inference', 'exports', 'annotation_review', 'annotation_history', 'settings', 'diagnostics']
    cube_id: Reference | None = None
    run_id: Reference | None = None
    comparison_run_id: Reference | None = None
    model_id: Reference | None = None
    annotation_version_id: Reference | None = None
    band: Annotated[int, Field(ge=0)] | None = None
    red: Annotated[int, Field(ge=0)] | None = None
    green: Annotated[int, Field(ge=0)] | None = None
    blue: Annotated[int, Field(ge=0)] | None = None
    l0: Annotated[int, Field(ge=0)] | None = None
    l1: Annotated[int, Field(ge=0)] | None = None
    s0: Annotated[int, Field(ge=0)] | None = None
    s1: Annotated[int, Field(ge=0)] | None = None
    stretch: Literal['auto', 'manual'] = 'auto'
    black: Annotated[int, Field(ge=0, le=128)] = 0
    white: Annotated[int, Field(ge=128, le=255)] = 255
    gamma: Annotated[float, Field(ge=.2, le=5)] = 1
    zoom: Annotated[float, Field(gt=0, le=20)] = 1


def register_interactive(registry, *, datasets=None, runner=None, sessions=None, paths=None,
                         database=None, training=None, training_sets=None, diffusion=None):
    def flat_page(rows, args, keys):
        page = rows[args.offset:args.offset+args.limit]
        out = dict(total=len(rows), count=len(page), offset=args.offset,
                   truncated=args.offset+len(page)<len(rows))
        for i, row in enumerate(page, 1):
            out.update({f'item_{i}_{key}':row.get(key) for key in keys})
        return out

    def runs(args):
        reference = args.submission_reference
        owner = owner_session.get()
        records = None
        retry_source=None
        with connect_database(database) as db:
            db.row_factory = __import__('sqlite3').Row
            if args.run_ids is not None:
                if len(set(args.run_ids)) != len(args.run_ids):
                    raise DataError('INVALID_REQUEST', '运行引用不能重复')
                ids = args.run_ids
            elif args.cube_id:
                ids = [r[0] for r in db.execute('SELECT id FROM preprocess_run WHERE cube_id=? ORDER BY created_at,id', (args.cube_id,))]
            else:
                if reference is None:
                    row = db.execute("SELECT submission_ref FROM business_operation WHERE owner_session_id=? AND kind IN ('preprocess.run','preprocess.run_batch') ORDER BY created_at DESC,operation_id DESC LIMIT 1",(owner,)).fetchone()
                    reference = row[0] if row else None
                batches=db.execute("SELECT operation_id,receipt_json,action_ref FROM business_operation WHERE submission_ref=? AND owner_session_id=? AND kind='preprocess.run_batch' ORDER BY created_at,action_ref",(reference,owner)).fetchall()
                from spectrumagent.preprocess.retry import action_parent
                sources={action_parent(row['action_ref']) for row in batches}
                if len(sources)==1 and None not in sources:retry_source=next(iter(sources))
                ops = db.execute("SELECT operation_id,run_id FROM business_operation WHERE submission_ref=? AND owner_session_id=? AND kind='preprocess.run' ORDER BY created_at,action_ref",(reference,owner)).fetchall()
                if batches and all(row['receipt_json'] is not None for row in batches):
                    records=[{**item,'batch_operation_id':row['operation_id']} for row in batches
                             for item in json.loads(row['receipt_json'])['items']]
                    originals=[row for row in batches if action_parent(row['action_ref']) is None]
                    if len(originals)==1:
                        root=originals[0]
                        records=[{**item,'batch_operation_id':root['operation_id']} for item in json.loads(root['receipt_json'])['items']]
                        positions={item['cube_id']:i for i,item in enumerate(records)}
                        for row in batches:
                            parent=action_parent(row['action_ref'])
                            if parent!=reference:continue
                            for item in json.loads(row['receipt_json'])['items']:
                                if item['cube_id'] in positions:
                                    index=positions[item['cube_id']]
                                    if records[index]['status']!='succeeded':
                                        records[index]={**item,'batch_operation_id':row['operation_id'],'original_batch_operation_id':root['operation_id']}
                        for row in batches:
                            if action_parent(row['action_ref']) not in (None,reference):
                                records.extend({**item,'batch_operation_id':row['operation_id']} for item in json.loads(row['receipt_json'])['items'])
                else:
                    records=[dict(row) for row in ops]
                    if not records and batches:
                        records=[dict(run_id=None,status='unknown',operation_id=row['operation_id']) for row in batches]
                ids = [r.get('run_id') for r in records]
                if reference and not records:
                    raise DataError('OPERATION_NOT_FOUND', '该提交不属于当前会话或没有预处理操作')
            names=datasets.display_names() if datasets else {}
            out = dict(total=len(ids), count=0, offset=args.offset,
                       truncated=args.offset+args.limit<len(ids), submission_ref=reference,
                       unknown_count=0, view_kind='preprocess_batch')
            if retry_source:out['retry_of_submission']=retry_source
            for i, identifier in enumerate(ids[args.offset:args.offset+args.limit], 1):
                known=records[args.offset+i-1] if records is not None else {}
                if identifier is None and known.get('status')=='failed':
                    result={k:known.get(k) for k in ('run_id','status','cube_id','error_code')}
                else:
                    try:
                        if identifier is None:raise DataError('OPERATION_IN_PROGRESS','操作尚无可核对的运行引用')
                        result = _run_summary(runner.get(identifier))
                    except DataError:
                        result = {'run_id':identifier,'status':'unknown','cube_id':known.get('cube_id')}
                        out['unknown_count'] += 1
                if result.get('cube_id') in names:result['display_name']=names[result['cube_id']]
                if known.get('batch_operation_id'):result['batch_operation_id']=known['batch_operation_id']
                out.update({f'item_{i}_{k}':v for k,v in result.items()})
                operation = db.execute('SELECT operation_id FROM business_operation WHERE run_id=? AND owner_session_id=?',(identifier,owner)).fetchone()
                if operation:out[f'item_{i}_operation_id'] = operation[0]
                elif known.get('operation_id'):out[f'item_{i}_operation_id']=known['operation_id']
                out['count'] += 1
            return out

    def paths_set(args):
        from spectrumagent.api.project_paths import set_project_paths
        row = set_project_paths(paths,args.project_id,args.source_path,args.output_root)
        return {'project_id':args.project_id, 'source_configured':bool(row['source_path']),
                'output_configured':bool(row['output_root']), 'output_enabled':row['output_enabled']}

    def select(args):
        action = runner.recipes.select_project if args.selected else runner.recipes.deselect_project
        action(args.project_id,args.recipe_id)
        return dict(project_id=args.project_id,recipe_id=args.recipe_id,selected=args.selected)

    def target_store():
        from spectrumagent.modeling.dataset import SampleTargets
        return SampleTargets(database)

    def targets(args):
        rows = target_store().list(args.project_id)
        out = {'count':len(rows)}
        for i,row in enumerate(rows,1):
            out.update({f'item_{i}_{k}':row.get(k) for k in ('cube_id','schema_id','tree_path','value','source')})
        return out

    def put(args):
        row = target_store().put(args.cube_id,args.schema_id,args.value)
        return {k:row[k] for k in ('cube_id','schema_id','value','source')}

    def import_targets(args):
        row = target_store().import_csv(args.project_id,args.csv_text,overwrite=args.overwrite)
        out = {'imported':row['imported']}
        for k in ('unmatched','pending_confirmation','invalid','unknown_fields','out_of_range'):
            out[k+'_count'] = len(row[k])
        return out

    def regress(args):
        row = training.regress(**args.model_dump())
        return registry.modeling.training_summary(row['run_id'],row)

    def labels():
        from spectrumagent.annotation.labels import LabelStore
        return LabelStore(database)

    def label_create(args):
        from spectrumagent.annotation.labels import SimpleLabelRequest
        row = labels().add(SimpleLabelRequest(**args.model_dump()))
        return {k:row[k] for k in ('id','name','code','color_hex')}

    def label_edit(args):
        row = labels().update(args.label_id,**args.model_dump(exclude={'label_id'},exclude_unset=True))
        return {k:row[k] for k in ('id','name','code','color_hex')}

    def schema_create(args):
        from spectrumagent.annotation.labels import SchemaRequest, SchemaField
        row = labels().add(SchemaRequest(project_id=args.project_id,schema=SchemaField(
            name=args.name,tree_path=args.tree_path,field_type='continuous',unit=args.unit)))
        return {k:row[k] for k in ('id','name','tree_path','field_type')}

    def merge(args):
        row=labels().merge(args.source_id,args.target_id)
        return {'target_id':row['target']['id'],**{'references_'+k:v for k,v in row['references'].items()}}

    def tree_preview(args):
        rows=labels().import_tree(args.root,args.depth,project_id=args.project_id)
        out={'count':len(rows)}
        for i,row in enumerate(rows,1):out.update({f'item_{i}_{k}':v for k,v in row.items()})
        return out

    def tree_apply(args):
        return labels().apply_tree([c.model_dump() for c in args.candidates],project_id=args.project_id,root=args.root,depth=args.depth)

    def sample_labels(args):
        if args.label_id:
            if not args.cube_ids:raise DataError('INVALID_REQUEST','关联标签须指定样品范围')
            return sessions.assign_samples(args.project_id,args.cube_ids,args.label_id,'dialog')
        rows=sessions.sample_labels(args.project_id,args.cube_ids)
        out={'cube_count':len(rows),'count':0}
        for cube,items in rows.items():
            for item in items:
                out['count']+=1;i=out['count']
                out.update({f'item_{i}_cube_id':cube,**{f'item_{i}_{k}':item[k] for k in ('id','name','code','color_hex')}})
        return out

    def display(args):
        data = args.model_dump(exclude_none=True)
        if args.view in {'dataset','spectrum','annotation_review','annotation_history'}:
            if not args.cube_id:raise DataError('INVALID_REQUEST', '请明确要显示的数据')
            dataset,_ = datasets.get(args.cube_id)
            if any(data.get(k,0)>=dataset.shape[2] for k in ('band','red','green','blue')):
                raise DataError('INVALID_REQUEST', '显示波段超出数据范围')
        if args.view=='annotation_history':
            with connect_database(database) as db:
                rows=db.execute('SELECT id,version_no,labeled_pixels FROM annotation_version WHERE cube_id=? ORDER BY version_no',(args.cube_id,)).fetchall()
            if args.annotation_version_id and args.annotation_version_id not in {row[0] for row in rows}:
                raise DataError('VERSION_NOT_FOUND','该数据没有这个标注版本')
            data['version_count']=len(rows)
            for i,row in enumerate(rows,1):
                data.update({f'item_{i}_{k}':v for k,v in zip(('version_id','version_no','labeled_pixels'),row)})
        if args.view in {'preprocess','compare','exports'}:
            if not args.run_id:raise DataError('INVALID_REQUEST','请明确预处理运行引用')
            runner.get(args.run_id)
            if args.comparison_run_id:runner.get(args.comparison_run_id)
        if args.view in {'classification','regression'}:
            if not args.run_id:raise DataError('INVALID_REQUEST','请明确训练运行引用')
            registry.modeling.training.get(args.run_id)
        if args.view=='coefficients':
            if not args.model_id:raise DataError('INVALID_REQUEST','请明确模型引用')
            registry.modeling.models.coefficients(args.model_id)
        if args.view=='inference':
            if not args.run_id:raise DataError('INVALID_REQUEST','请明确推理引用')
            registry.modeling.inferences.get(args.run_id)
        if args.white-args.black<16:raise DataError('INVALID_REQUEST','高光与阴影至少相差16')
        data['view_kind'] = data.pop('view')
        return data

    def review(args):
        import numpy as np
        from contextlib import nullcontext
        lease=sessions.resources.lease(args.cube_id,required=True) if sessions.resources else nullcontext()
        with lease,sessions._lock:
            state=sessions._state(args.cube_id)
            if args.erase_superpixel is not None:
                if state.segments is None:raise DataError('SUPERPIXELS_REQUIRED','请先准备分割')
                mask=state.segments==args.erase_superpixel
                if not np.any(mask):raise DataError('INVALID_REQUEST','该超像素不存在')
                sessions.edit(args.cube_id,mask,action='erase',geometry={'superpixels':[args.erase_superpixel]})
            quality=sessions.validate(args.cube_id)
            out={'cube_id':args.cube_id,'view_kind':'annotation_review','suspicious_count':len(quality['suspicious'])}
            for i,item in enumerate(quality['suspicious'][:100],1):
                out.update({f'item_{i}_{k}':item[k] for k in ('superpixel_id','label_index','pixel_count','cos')})
            return out

    entries = [
        ('preprocess.runs',RunPage,'查询固定提交的整批预处理结果并分页；未给提交时只读本会话最近一次实际提交；也可明确 run_ids 或 cube_id，unknown 不算失败，不重跑',runs,runner is not None),
        ('preprocess.operators',NoArguments,'读取全部已开放算子的版本、必填参数、默认值和校验条件，不执行',lambda a:operator_summary(runner),runner is not None),
        ('projects.paths_set',ProjectPaths,'登记数据源和输出根，复用设置界面路径验证及写守卫；返回配置状态',paths_set,paths is not None),
        ('preprocess.recipe_select',RecipeSelect,'项目选用或取消选用明确配方',select,runner is not None),
        ('modeling.targets',TargetQuery,'查询样品连续量目标及字段引用',targets,database is not None),
        ('modeling.target_set',TargetPut,'保存明确样品连续量测量值，复用界面验证',put,database is not None),
        ('modeling.targets_import',TargetImport,'用服务端CSV解析器导入连续量；返回错误和覆盖确认数量，不猜测值',import_targets,database is not None),
        ('modeling.regress',Regression,'按真实成功预处理引用进行PLS回归，参数与人工界面一致',regress,training is not None),
        ('labels.create',LabelCreate,'按名称和颜色新建标签',label_create,database is not None),
        ('labels.update',LabelEdit,'修改已指认标签的名称、颜色或快捷键',label_edit,database is not None),
        ('labels.delete',LabelRef,'删除明确标签，复用引用检查，仍被标注或样品引用时拒绝删除',lambda a:labels().delete(a.label_id),database is not None),
        ('labels.merge',LabelMerge,'合并同项目标签，复用草稿引用校验和既有事务',merge,database is not None),
        ('labels.tree_preview',TreeScope,'预览目录标签导入候选和命名要求，不修改样品',tree_preview,database is not None),
        ('labels.tree_apply',TreeApply,'按真实预览候选导入目录标签与样品关联，目录和样品变化时拒绝',tree_apply,database is not None),
        ('labels.samples',SampleLabels,'查询样品标签；明确label_id和cube_ids时登记样品关联，不给像素赋类',sample_labels,sessions is not None),
        ('labels.continuous_create',SchemaCreate,'新建回归使用的连续量字段及单位',schema_create,database is not None),
        ('ui.show',Display,'在对话内显示本地真实图表或数据；不自动切屏，不把图像矩阵或光谱发给模型。支持灰度RGB、拉伸缩放、谱线、预处理、分类回归、系数、预测图、导出、复核及设置',display,runner is not None),
        ('annotations.configure',Segmentation,'按人工界面参数生成或重新生成超像素；只分割不赋类',lambda a:segmentation(sessions,diffusion,a),sessions is not None and diffusion is not None),
        ('annotations.task',TaskAction,'读取或取消后台分割任务，重试失败项、继续未执行项；保留已完成结果',lambda a: (_ for _ in ()).throw(DataError('DRAFT_OWNER_REQUIRED','需要当前对话任务上下文')),True),
        ('annotations.review',Review,'核对当前标注谱线，返回可疑超像素引用并在本地显示；只在用户明确要求剔除时提供erase_superpixel，不赋类',review,sessions is not None),
    ]
    for name,schema,description,handler,ready in entries:
        registry.register(name,schema,description,handler if ready else None)


def operator_summary(runner):
    from spectrumagent.preprocess.capabilities import capabilities
    out = {}
    for i, row in enumerate(capabilities(runner.recipes.registry),1):
        out[f'operator_{i}_name'] = row['op']
        out[f'operator_{i}_version'] = row['version']
        out[f'operator_{i}_ai_enabled'] = row['ai_enabled']
        schema = row['params_schema']
        out[f'operator_{i}_required'] = '、'.join(schema.get('required',[]))
        for key,value in schema.get('properties',{}).items():
            out[f'operator_{i}_parameter_{key}']=value.get('type','')
            if value.get('enum'):out[f'operator_{i}_options_{key}']='、'.join(map(str,value['enum']))
            if 'default' in value and type(value['default']) in (str,int,float,bool):
                out[f'operator_{i}_default_{key}'] = value['default']
        out[f'operator_{i}_conditions'] = '；'.join(row['parameter_constraints']+row['data_conditions'])
    out['count'] = len(capabilities(runner.recipes.registry))
    return out


def segmentation(sessions,diffusion,args):
    from spectrumagent.annotation.engines.superpixels import Parameters
    engine=diffusion.superpixels
    def prepare():
        segmentation,action=engine.prepare_with_action(args.cube_id,sessions,
            Parameters(n_segments=args.n_segments,compactness=args.compactness,pca_components=args.pca_components),force=args.force)
        return dict(cube_id=args.cube_id,status='ready',action=action,superpixel_count=int(segmentation.report['superpixel_count']))
    tasks=getattr(engine,'preparation_tasks',None)
    return tasks.run_sync(prepare) if tasks else prepare()
