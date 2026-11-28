"""Per-session tool views; no shared registry/handler is mutated."""
import json
import re

from backend.database import connect_database
from spectrumagent.data import DataError
from .state import _failure
from . import context as memory
from .open_access import OPEN_ACCESS


# Explicit, closed catalogue. Never authorize by a prefix.
POLICIES = {
    'workspace.current':'global', 'workspace.recipe_edit':'public', 'workspace.save_annotation':'cube', 'workspace.preprocess':'global',
    'workspace.classify':'global', 'workspace.preflight':'global',
    'datasets.list':'discovery', 'datasets.describe':'cube', 'datasets.resolve':'discovery',
    'annotations.draft_get':'cube', 'annotations.draft_add_region':'cube',
    'annotations.status_batch':'nested',
    'annotations.draft_select_candidates':'cube', 'annotations.draft_confirm':'cube',
    'preprocess.run':'cube', 'preprocess.compare':'cube', 'training_mat.export':'cube',
    'settings.llm_get':'public', 'annotations.context':'cube', 'annotations.prepare':'cube',
    'annotations.prepare_batch':'batch', 'annotations.ensure_labels':'cube',
    'annotations.propose':'cube', 'annotations.apply_candidate':'cube',
    'annotations.reject_candidate':'cube', 'annotations.set_background':'cube',
    'annotations.mark_region':'cube', 'annotations.edit_region':'cube', 'annotations.undo':'cube',
    'preprocess.recipes':'public', 'preprocess.recipe_ensure':'public',
    'preprocess.run_default':'cube', 'preprocess.run_get':'run', 'preprocess.run_batch':'nested',
    'versions.list':'bound_version', 'versions.preview':'global', 'versions.confirm':'global',
    'modeling.preflight':'modeling_write', 'modeling.classify':'modeling_write',
    'modeling.training_task':'modeling_read',
    'modeling.runs':'modeling_read', 'modeling.run':'modeling_read',
    'modeling.registry':'modeling_read', 'modeling.coefficients':'modeling_read',
    'modeling.inference':'modeling_read',
    'modeling.metrics':'modeling_read',
    'modeling.classification_result':'modeling_read',
    'modeling.classification_infer':'modeling_write',
    'modeling.classification_task':'modeling_write',
    # Everything-operable layer. Import and deletion are cross-dataset, so they
    # stay in global sessions; recipe composition and settings are not dataset-bound.
    'sources.list':'public', 'sources.scan':'public', 'datasets.import':'global',
    'datasets.delete_preview':'global', 'datasets.delete':'global',
    'preprocess.recipe_create':'public', 'preprocess.recipe_version_add':'public',
    'preprocess.run_export':'run',
    'modeling.register':'modeling_write', 'modeling.set_stage':'modeling_write',
    'modeling.infer':'modeling_write',
    'training_sets.candidates':'global', 'training_sets.preview':'global',
    'training_sets.confirm':'global', 'training_sets.list':'global', 'training_sets.members':'global',
    'settings.llm_set':'public', 'projects.paths_get':'public',
    'preprocess.draft_get':'public','preprocess.draft_update':'public','preprocess.draft_save':'public',
    'preprocess.draft_confirm':'nested','preprocess.draft_execute':'nested',
    'preprocess.recipe_delete':'public','preprocess.recipe_restore':'public',
}
POLICIES.update({
    'experiments.sample_evaluation_get':'global', 'experiments.sample_evaluation_update':'global',
    'modeling.regression_plan_get':'global', 'modeling.regression_plan_update':'global',
    'modeling.regression_plan_review':'global', 'modeling.regression_plan_execute':'global',
    'experiments.draft_get':'global', 'experiments.draft_update':'global', 'experiments.input_inspect':'global',
    'experiments.history_list':'global', 'experiments.history_select':'global', 'experiments.history_compare':'global',
    'experiments.inference_get':'global','experiments.inference_inspect':'global','experiments.inference_update':'global',
    'preprocess.runs':'global', 'preprocess.operators':'public','projects.paths_set':'public',
    'preprocess.recipe_select':'public','modeling.targets':'public','modeling.target_set':'cube',
    'modeling.targets_import':'global','modeling.regress':'global','labels.create':'public',
    'labels.update':'public','labels.continuous_create':'public','ui.show':'public',
    'annotations.configure':'cube','annotations.task':'public',
    'labels.delete':'public','labels.merge':'public','labels.tree_preview':'public','labels.tree_apply':'public','labels.samples':'public',
    'annotations.review':'cube',
})


class ScopedToolRegistry:
    @property
    def data_intake(self):
        return getattr(self.base, 'data_intake', None)

    @property
    def experiment_dialogue(self):
        return getattr(self.base, 'experiment_dialogue', None)

    def __init__(self, base, service, session_id, *, engine=None, annotations=None, batch=None, request_id=None, tasks=None):
        self.base, self.service, self.session_id = base, service, session_id
        self.engine, self.annotations, self.batch = engine, annotations, batch
        self.request_id = request_id
        self.tasks = tasks
        self.user_content = None
        self.catalogue_version = getattr(base, 'catalogue_version', 1)
        self.hidden_names = base.hidden_names
        self.binding = service.scope(session_id)
        self.work = self.binding['scope_kind'] == 'dataset_version'
        self.call_identity = None
        self.call_round = None

    def begin_call(self, round_, call):
        self.call_identity = round_['id'] + ':' + call['id']
        self.call_round = round_

    def authorizes_recipe_plan(self,content,calls):
        from .authorization import unquoted
        text = unquoted(content or '')
        allowed = {'preprocess.draft_get','preprocess.draft_update','preprocess.draft_save',
                   'preprocess.draft_confirm','preprocess.draft_execute','preprocess.recipes'}
        return bool(calls and all(c['name'] in allowed for c in calls)
                    and re.search(r'保存|另存',text) and re.search(r'执行|运行|预处理',text)
                    and not re.search(r'(?:不要|不用|暂不|先不|禁止)\s*(?:保存|执行|运行)|是否|如何|怎么|[?？]',text))

    def explicit_repeat_limit(self,name):
        if name not in {'preprocess.run','preprocess.run_default','preprocess.draft_execute'}:
            return 1
        from .authorization import unquoted
        text = unquoted(self.user_content or (self.call_round or {}).get('user_message',''))
        return 2 if re.search(r'(?:运行|执行|预处理)\s*(?:两|2)\s*(?:次|遍)',text) else 1

    def capture_intent(self, content, workspace, state):
        self.user_content = content
        from .authorization import AnnotationAuthorization
        recipe_only=(state.get('recipe_editing') or '配方' in content) and not re.search(r'标注|分割|超像素|扩散',content)
        if not recipe_only:
            AnnotationAuthorization(self.service).capture(self.session_id, content, workspace, self.request_id, state)
        from .preprocess_authorization import capture
        capture(self.service.database,self.session_id,content,state,self.request_id)

    def annotation_choice_target(self, state):
        from .authorization import AnnotationAuthorization,unquoted,QUERY,QUESTION,operations
        text=unquoted(self.user_content or '')
        if (state.get('recipe_editing') or '配方' in text) and not re.search(r'标注|分割|超像素|扩散',text):
            return None
        if re.search(QUERY+'|'+QUESTION,text) or (not operations(text) and re.search(r'预处理|配方|建模|训练|模型|推理',text)):
            return None
        target = AnnotationAuthorization(self.service).pending_target(self.session_id, state)
        return target['cube_ids'].copy() if target and target.get('awaiting_mode') else None

    def start_annotation_mode(self, mode, state):
        if getattr(self, 'control', None) is not None:
            self.control.begin('tool')
        from .annotation_flow import submit_flow, flow_reply
        grant = self.service.authorization_records[state['operation_authorization']['authorization_id']]
        accepted = submit_flow(self.service, self.tasks, self.session_id, self.request_id,
                               grant['cube_ids'], mode, state, grant)
        return flow_reply(accepted)

    def select_annotation_targets(self, cube_ids, state):
        """Bind an intake-owned batch for the user's next mode choice."""
        from .authorization import AnnotationAuthorization
        AnnotationAuthorization(self.service).capture(self.session_id, '人工标注', None,
            self.request_id, state, selected_cube_ids=tuple(cube_ids))
        state.pop('pending_clarify', None)

    def authorize_annotation(self, name, args):
        if OPEN_ACCESS:
            from .authorization import unquoted
            action = ('保存' if name in {'annotations.draft_confirm','preprocess.draft_save'}
                      else '生成|分割|准备|超像素' if name in {'annotations.prepare','annotations.prepare_batch','annotations.configure'}
                      else '接受|应用|确认' if name=='annotations.apply_candidate'
                      else '预处理|执行|运行' if name in {'preprocess.run','preprocess.run_default','preprocess.run_batch','preprocess.draft_execute'}
                      else '扩散' if name=='annotations.propose' else None)
            text=unquoted(self.user_content or (self.call_round or {}).get('user_message',''))
            if action and re.search(r'(?:不要|不用|暂不|先不|先别|禁止|别)\s*(?:再|先|自动|进行|做|执行)?\s*(?:'+action+r')',text):
                raise DataError('OPERATION_NOT_AUTHORIZED','已遵循本轮停止或否定指令，未执行该操作')
        if OPEN_ACCESS and name.startswith('annotations.'):
            if name in {'annotations.prepare','annotations.prepare_batch','annotations.propose','annotations.draft_confirm'}:
                from .authorization import source_baseline
                from uuid import uuid4
                state=self.service.store.context(self.session_id)
                old=self.service.authorization_records.get((state.get('operation_authorization') or {}).get('authorization_id'))
                if args.get('retry_of'):
                    parent=(self.tasks.receipts if self.tasks else {}).get(args['retry_of'])
                    if parent:return parent['grant']
                ids=args.get('cube_ids') or ([args['cube_id']] if args.get('cube_id') else [])
                if not ids and args.get('dataset_version_id'):
                    ids=[m['cube_id'] for m in self.service.versions.get_frozen(args['dataset_version_id'])['members']]
                if not ids:raise DataError('TASK_TARGET_REQUIRED','操作需要真实的数据范围')
                if old and set(ids)<=set(old['cube_ids']) and old.get('status') not in {'invalid','revoked'}:
                    old['operations']=sorted(set(old['operations'])|{'prepare','save','diffuse'})
                    return old
                record=dict(authorization_id=str(uuid4()),session_id=self.session_id,boot_id=self.service.boot_id,
                    cube_ids=list(ids),operations=['prepare','save','diffuse'],
                    baselines={cube:source_baseline(self.service.registry,cube) for cube in ids},
                    expected_content_hashes={},verified_targets={},status='pending_verification',
                    profile='annotation-default-v1',source_request_id=self.request_id)
                self.service.authorization_records[record['authorization_id']]=record
                return record
            return None
        if OPEN_ACCESS and not name.startswith('annotations.'):
            return None
        if name in {'preprocess.recipe_create','preprocess.recipe_version_add','preprocess.draft_save',
                    'preprocess.draft_confirm','preprocess.draft_execute','preprocess.recipe_delete','preprocess.recipe_restore'}:
            from .authorization import unquoted
            text = unquoted(self.user_content or (self.call_round or {}).get('user_message',''))
            verb = (r'删除|移除' if name=='preprocess.recipe_delete' else r'恢复|还原' if name=='preprocess.recipe_restore'
                    else r'执行|运行|预处理|保存并执行' if name in {'preprocess.draft_confirm','preprocess.draft_execute'}
                    else r'保存|另存|创建配方|新建配方')
            if not re.search(verb,text) or re.search(r'(?:不要|不用|暂不|先不|禁止)\s*(?:保存|执行|运行|预处理|删除|恢复|创建|新建)|是否|如何|怎么|[?？]',text):
                raise DataError('OPERATION_NOT_AUTHORIZED','本轮未明确要求该配方提交；讨论和草稿修改不会自动保存或执行')
        if name in {'annotations.prepare','annotations.prepare_batch','annotations.propose','annotations.draft_confirm'}:
            from .authorization import operations, unquoted, NEGATION, QUERY, QUESTION
            text = self.user_content if self.user_content is not None else (self.call_round or {}).get('user_message')
            if text is not None and not operations(text):
                clean = unquoted(text)
                continuation = re.search(r'继续|接着|按上述|按之前|默认|(?:这(?:里|个)?是|标为|属于)', clean)
                if (not continuation or re.search(NEGATION+'|'+QUERY+'|'+QUESTION, clean)):
                    raise DataError('OPERATION_NOT_AUTHORIZED', '本轮没有要求执行或继续该操作，未使用历史授权写入')
        if name == 'annotations.ensure_labels':
            text = self.user_content or (self.call_round or {}).get('user_message', '')
            context = self.service.store.context(self.session_id)
            codes = args.get('class_codes') or []
            with connect_database(self.service.database) as db:
                projects = db.execute('SELECT id,name FROM project').fetchall()
                from spectrumagent.projects import session_project
                target_project = args.get('project_id') or session_project(self.service.database, self.session_id)
                if args.get('cube_id'):
                    row = db.execute('SELECT project_id FROM dataset_registry WHERE id=?', (args['cube_id'],)).fetchone()
                    target_project = row[0] if row else None
                if target_project is None and len(projects) == 1:
                    target_project = projects[0][0]
                existing_codes = {row[0] for row in db.execute('SELECT code FROM label WHERE project_id=? AND deleted_at IS NULL', (target_project,))}
            if target_project and len(projects) > 1 and not any(pid == target_project and (pid in text or pname in text) for pid, pname in projects):
                if target_project != context.get('label_project_id') and target_project != session_project(self.service.database, self.session_id):
                    raise DataError('OPERATION_NOT_AUTHORIZED', '请明确要修改标签的项目')
            wanted = set(codes) | ({'BG'} if args.get('include_background', False) else set())
            if (codes and target_project == context.get('label_project_id') and not args.get('class_names')
                    and not args.get('aliases') and set(codes).issubset(context.get('class_codes', []))
                    and wanted.issubset(existing_codes)):
                return None  # Re-reading already declared labels cannot mint a new category.
            from .authorization import unquoted
            if re.search(r'查询|查看|列出|如何|怎么|是否|能否|不要|不用|暂不|先不|禁止|取消|[？?]', unquoted(text)):
                raise DataError('OPERATION_NOT_AUTHORIZED', '查询或否定指令不授权创建标签')
            if not re.search(r'新建|创建|建立|添加|登记|标签|类别|标注', text) or re.search(r'不要.*(?:标签|类别)', text):
                raise DataError('OPERATION_NOT_AUTHORIZED', '请明确要登记的项目标签')
            names = args.get('class_names') or []
            if args.get('include_background', False) and not re.search(r'背景|\bBG\b', text, re.IGNORECASE):
                raise DataError('OPERATION_NOT_AUTHORIZED', '背景标签需要用户明确声明')
            if any(value not in text for value in names + codes):
                raise DataError('OPERATION_NOT_AUTHORIZED', '标签不在用户明确声明的类别中')
            for alias in args.get('aliases', []):
                if (alias['alias'] not in text or alias['class_code'] not in text
                        or not re.search(r'别名|对应|映射', text)):
                    raise DataError('OPERATION_NOT_AUTHORIZED', '别名需要用户明确指定对应关系')
        from .authorization import AnnotationAuthorization
        return AnnotationAuthorization(self.service).require(
            self.session_id, self.service.store.context(self.session_id), name, args,
            self.tasks if self.tasks and args.get('retry_of') in self.tasks.receipts else self.batch)

    def save_authorized(self, cube_id):
        self.authorize_annotation('annotations.draft_confirm', {'cube_id': cube_id})
        return True

    def modeling_provenance(self):
        from .tools.modeling import ModelingProvenance
        if self.call_round is None:
            return None
        turn = self.call_round.get('turn_id') or self.call_round['id']
        rounds = self.service.store.turn_rounds(self.session_id, turn)
        root = next((r for r in rounds if r['id'] == turn), None)
        if root is None:
            return None
        steps = tuple(s for r in rounds for s in self.service.store.steps(self.session_id, r['id']))
        return ModelingProvenance(root['user_message'], turn, self.request_id, steps,
                                  self.binding['dataset_version_ref'] if self.work else None,
                                  tuple(self.service.store.steps(self.session_id)))

    def authorizes_modeling_plan(self, content, calls):
        """A plan is scheduling, not consent: verify the exact batch selection first."""
        from .tools.modeling import (ModelingProvenance, ModelingBindingArguments,
                                     NeedVersion, resolve_modeling_selection, resolve_modeling_binding)
        from .workflow import READ_TOOLS
        writes = [c for c in calls if c['name'] not in READ_TOOLS]
        names = [c['name'] for c in writes]
        if names == ['modeling.preflight', 'modeling.classify']:
            if writes[0]['arguments'] != writes[1]['arguments']:
                return False
            prior = self.modeling_provenance()
            proof = ModelingProvenance(content, prior.turn_id if prior else '', self.request_id,
                prior.steps if prior and prior.user_message == content else (),
                self.binding['dataset_version_ref'] if self.work else None,
                tuple(self.service.store.steps(self.session_id)))
            try:
                resolve_modeling_binding(arguments=ModelingBindingArguments.model_validate(writes[1]['arguments']),
                    versions=self.base.modeling.versions, database=self.service.database,
                    registry=self.base.modeling.datasets, engine=self.engine, provenance=proof)
            except (DataError, NeedVersion, ValueError):
                return False
            return True
        if names == ['preprocess.run_batch', 'modeling.preflight', 'modeling.classify']:
            if writes[1]['arguments'] != writes[2]['arguments']:
                return False
            writes = [writes[0], writes[2]]
        if [c['name'] for c in writes] != ['preprocess.run_batch', 'modeling.classify']:
            return False
        batch, training = (c['arguments'] for c in writes)
        if training.get('preprocess_source') != 'current_turn':
            return False
        if not re.search(r'(?:本次|本轮)(?:整批)?预处理(?:产生的|生成的)?(?:整套)?(?:结果|运行|run)', content, re.I):
            return False
        prior = self.modeling_provenance()
        proof = ModelingProvenance(content, prior.turn_id if prior else '', self.request_id,
            prior.steps if prior and prior.user_message == content else (),
            self.binding['dataset_version_ref'] if self.work else None,
            tuple(self.service.store.steps(self.session_id)))
        try:
            _, _, items = resolve_modeling_selection(arguments=ModelingBindingArguments.model_validate(training),
                versions=self.base.modeling.versions, database=self.service.database,
                engine=self.engine, provenance=proof)
        except (DataError, NeedVersion, ValueError):
            return False
        expected = {cube: {'cube_id': cube, 'annotation_version_id': item.annotation_version_id,
                          'recipe_version_id': training['recipe_version_id']} for cube, item in items.items()}
        actual = batch.get('items', [])
        # Pydantic emits optional null fields. They do not change an explicitly
        # authorized member triple; populated alternatives still require their
        # own binding and cannot inherit this exact-plan authorization.
        if batch.get('retry_of_submission') is not None:
            return False
        actual = [{k: v for k, v in item.items() if v is not None} for item in actual]
        return len(actual) == len(expected) and len({i.get('cube_id') for i in actual}) == len(actual) and all(
            expected.get(item.get('cube_id')) == item for item in actual)

    def allowed(self, name):
        return not self.work or name in POLICIES and POLICIES[name] != 'global'

    def resolve(self, name):
        if not self.allowed(name):
            raise _failure('SESSION_SCOPE_MISMATCH','当前工作会话不提供该操作，请进入全局会话',409)
        return self.base.resolve(name)

    def snapshot(self):
        return [t for t in self.base.snapshot() if self.allowed(t['function']['name'])]

    def validate(self, name, arguments):
        self.resolve(name)
        return self.base.validate(name, arguments)

    def member(self, cube):
        with connect_database(self.service.database) as db:
            row = db.execute('SELECT content_hash FROM agent_session_member WHERE session_id=? AND cube_id=?',(self.session_id,cube)).fetchone()
        if not row:
            raise _failure('SESSION_SCOPE_MISMATCH','目标不属于绑定版本，请进入全局或对应工作会话',409)
        return row[0]

    def _reference_cube(self, table, ref):
        with connect_database(self.service.database) as db:
            row = db.execute(f'SELECT cube_id FROM {table} WHERE id=?',(ref,)).fetchone()
        if row is None:
            raise _failure('SESSION_REFERENCE_INVALID','引用已失效，请重新明确对象',409)
        return row[0]

    def _check(self, name, args, *, scientific=False, live_references=True):
        self.resolve(name)
        from .step_plan import validate_tool
        validate_tool(self.service.database, self.session_id, name)
        from spectrumagent.projects import bind, check_document, session_project
        with bind(session_project(self.service.database, self.session_id)), connect_database(self.service.database) as db:
            check_document(db, args)
            from spectrumagent.projects import require
            if args.get('run_id'):
                kind = 'training' if name in {'modeling.register','modeling.run'} else 'inference' if name == 'modeling.inference' else 'preprocess' if name.startswith('preprocess.') else None
                if kind:
                    require(db, kind, args['run_id'])
            if name == 'datasets.resolve' and re.fullmatch(r'[0-9a-f-]{36}', args.get('query','')):
                require(db, 'cube', args['query'])
        if self.work and name=='annotations.status_batch':
            for cube in args.get('cube_ids',[]):self.member(cube)
        from .tools.modeling import MODELING_TOOLS, WRITE_TOOLS
        if name in MODELING_TOOLS:
            cubes = self.base.modeling.reference_members(name, args, owner=self.session_id)
            if self.work:
                for cube in cubes:
                    self.member(cube)
                if name in WRITE_TOOLS and args.get('dataset_version_id') not in (None, self.binding['dataset_version_ref']):
                    raise _failure('SESSION_SCOPE_MISMATCH', '训练版本与会话绑定不一致', 409)
                for item in args.get('items', []):
                    for key, table in [('annotation_version_id', 'annotation_version'), ('preprocess_run_id', 'preprocess_run')]:
                        if item.get(key):
                            actual = self._reference_cube(table, item[key])
                            self.member(actual)
                            if actual != item['cube_id']:
                                raise _failure('SESSION_SCOPE_MISMATCH', '建模成员引用不一致', 409)
            if scientific and (name in WRITE_TOOLS or name == 'modeling.classification_infer'
                               or name == 'modeling.classification_task' and args.get('action') == 'retry'):
                for cube in cubes:
                    if not self.service.availability(cube)['available']:
                        raise _failure('SESSION_MEMBER_UNAVAILABLE', '成员当前不可用', 409)
                    if self.work and (self.engine is None or self.engine.source_identity(cube)[0] != self.member(cube)):
                        raise _failure('SESSION_SOURCE_MISMATCH', '当前源内容与会话绑定不一致', 409)
            return
        if name=='annotations.prepare_batch' and args.get('retry_of'):
            receipt=(self.tasks.receipts.get(args['retry_of']) if self.tasks else None) or (self.batch.receipts.get(args['retry_of']) if self.batch else None)
            if not receipt or receipt.get('owner_session_id')!=self.session_id or receipt.get('owner_boot_id')!=self.service.boot_id:
                raise _failure('SESSION_SCOPE_MISMATCH','不能使用其他会话或已失效的批次回执',409)
        if not self.work:
            if live_references and (args.get('candidate_ref') or args.get('gesture_ref') or args.get('region_id') or isinstance(args.get('geometry'),dict) or (args.get('params') or {}).get('gesture_ref')):
                self._live_reference(args)
            return
        cubes = set()
        def visit(value):
            if isinstance(value, dict):
                direct = value.get('cube_id') or value.get('dataset_id')
                if direct:
                    self.member(direct);cubes.add(direct)
                for key, table in [('run_id','preprocess_run'),('annotation_version_id','annotation_version')]:
                    if value.get(key):
                        actual = self._reference_cube(table,value[key]);self.member(actual);cubes.add(actual)
                        if direct and direct!=actual:
                            raise _failure('SESSION_SCOPE_MISMATCH','引用与目标样品不一致',409)
                if name=='training_mat.export' and value.get('version_id'):
                    actual=self._reference_cube('annotation_version',value['version_id']);self.member(actual);cubes.add(actual)
                    if direct and actual!=direct:
                        raise _failure('SESSION_SCOPE_MISMATCH','标注版本与样品不一致',409)
                for nested in value.values():visit(nested)
            elif isinstance(value,list):
                for nested in value:visit(nested)
        visit(args)
        if name=='annotations.prepare_batch':
            if args.get('dataset_version_id')!=self.binding['dataset_version_ref']:
                raise _failure('SESSION_SCOPE_MISMATCH','批量版本与会话绑定不一致',409)
            if args.get('retry_of'):
                receipt=self.batch.receipts.get(args['retry_of']) if self.batch else None
                if not receipt or receipt.get('owner_session_id')!=self.session_id:
                    raise _failure('SESSION_SCOPE_MISMATCH','不能使用其他会话或已失效的批次回执',409)
        if live_references and (args.get('candidate_ref') or args.get('gesture_ref') or args.get('region_id') or isinstance(args.get('geometry'),dict) or (args.get('params') or {}).get('gesture_ref')):
            self._live_reference(args)
        if scientific and name not in {'datasets.describe','datasets.resolve','datasets.list','annotations.context','annotations.draft_get','preprocess.run_get','annotations.prepare_batch'}:
            for cube in cubes:
                if not self.service.availability(cube)['available']:
                    raise _failure('SESSION_MEMBER_UNAVAILABLE','成员当前不可用',409)
                if self.engine is None or self.engine.source_identity(cube)[0]!=self.member(cube):
                    raise _failure('SESSION_SOURCE_MISMATCH','当前源内容与绑定版本不一致',409)

    def _live_reference(self, args):
        cube=args.get('cube_id')
        if not cube or self.annotations is None:
            raise _failure('SESSION_REFERENCE_INVALID','当前引用不可核验',409)
        state=self.annotations._states.get(cube)
        context=self.service.store.context(self.session_id)
        if state is None:
            raise _failure('SESSION_REFERENCE_INVALID','工作态已失效，请重新准备',409)
        gesture=args.get('gesture_ref') or (args.get('geometry') or {}).get('gesture_ref') or (args.get('params') or {}).get('gesture_ref')
        if gesture and (gesture not in state.gestures or context.get('gesture_ref')!=gesture):
            raise _failure('SESSION_SCOPE_MISMATCH','手势不属于本会话的当前样品',409)
        candidate=args.get('candidate_ref')
        if candidate:
            preview=getattr(self.annotations,'_orchestration_previews',{}).get(candidate)
            actual=next((c for c in state.candidates if c.get('candidate_ref')==candidate),None)
            if not (preview and preview.get('cube_id')==cube or actual) or context.get('candidate_ref')!=candidate or not self.owns_candidate(candidate):
                raise _failure('SESSION_SCOPE_MISMATCH','候选不属于本会话的当前授权',409)
        region=args.get('region_id')
        if region and not any(r.get('region_id')==region for r in json.loads(state.document_json).get('regions',[])):
            raise _failure('SESSION_REFERENCE_INVALID','区域不属于当前样品',409)

    def owns_candidate(self, reference):
        with connect_database(self.service.database) as db:
            return bool(db.execute("SELECT 1 FROM agent_step WHERE session_id=? AND tool='annotations.propose' AND status='ok' AND json_extract(result_summary,'$.candidate_ref')=? LIMIT 1",(self.session_id,reference)).fetchone())

    def effective_arguments(self, name, args, *, live_references=True):
        result=dict(args)
        if name=='preprocess.run_batch' and result.get('items'):
            result['items']=[dict(item) for item in result['items']]
            with connect_database(self.service.database) as db:
                for item in result['items']:
                    if item.get('cube_id') and item.get('annotation_version_no') is not None and not item.get('annotation_version_id'):
                        row=db.execute('SELECT id FROM annotation_version WHERE cube_id=? AND version_no=?',
                                       (item['cube_id'],item['annotation_version_no'])).fetchone()
                        if row:item['annotation_version_id']=row[0]
        for key in ('cube_id','dataset_id'):
            if result.get(key) and self.catalogue_version==2 and self.service.registry is not None:
                self.service.registry.get(result[key])
        if name=='annotations.propose' and not result.get('gesture_ref'):
            context=self.service.store.context(self.session_id)
            if context.get('selected_cube_id')==result.get('cube_id'):
                result['gesture_ref']=context.get('gesture_ref')
        if self.work and name=='annotations.prepare_batch' and result.get('dataset_version_id') is None:
            result['dataset_version_id']=self.binding['dataset_version_ref']
        self._check(name,result,live_references=live_references)
        return result

    def preflight_group(self, calls):
        state=self.service.store.context(self.session_id)
        # 2026-11-13 ruling: a global session is global. The visible workspace
        # is only the UI's current canvas target, never a boundary on which
        # dataset a tool may address. Scope, live references and per-cube
        # consent are still checked for the whole group before any handler runs.
        for call in calls:
            refused=(call['name']=='annotations.apply_candidate' and call['arguments'].get('candidate_ref')
                     and call['arguments']['candidate_ref']==state.get('rejected_candidate_ref'))
            args=self.effective_arguments(call['name'],call['arguments'],live_references=not refused)
            self._check(call['name'],args,scientific=not refused,live_references=not refused)
            self.authorize_annotation(call['name'], args)

    def hydrate(self, state):
        state=dict(state)
        from spectrumagent import projects
        with connect_database(self.service.database) as db:
            old_catalog = state.get('dataset_catalog') or []
            if any(not projects.owned(db, 'cube', row['id']) for row in old_catalog):
                state.pop('dataset_catalog', None)
                state.pop('catalogs', None)
                state['scope_notice'] = '数据归属已变化，旧编号与确认需重新核对'
            if state.get('selected_cube_id') and not projects.owned(db, 'cube', state['selected_cube_id']):
                for key in ('selected_cube_id','task_target','operation_authorization','gesture_ref','candidate_ref','recipe_version_id'):
                    state.pop(key, None)
        if self.tasks:
            # Refresh accepted background work at each user turn. A stale
            # "accepted" receipt is not the current completion state.
            state['background_tasks'] = self.tasks.context(self.session_id)
        record = self.service.authorization_records.get((state.get('operation_authorization') or {}).get('authorization_id'))
        if record and state.get('task_target'):
            state['task_target'] = {**state['task_target'], 'identity_status': record['status']}
            if record['verified_targets']:
                state['task_target']['task_target_id'] = next(reversed(record['verified_targets']))
        state['session_scope']={'kind':self.binding['scope_kind'],
                                'dataset_version_id':self.binding['dataset_version_ref'],
                                'member_count':self.binding['member_count']}
        if not self.work:
            counts = self.service._counts(self.session_id, False)
            from spectrumagent.projects import session_project
            state['session_scope'].update(kind='global', scope='project', project_id=session_project(self.service.database, self.session_id), total=counts['total_members'],
                member_count=counts['total_members'],
                available_members=counts['available_members'], availability_status=counts['availability_status'])
            if self.service.registry is not None:
                from .tools.workflows import dataset_catalog
                state['current_datasets']=dataset_catalog(self.service.registry)
            return state
        # Scope is read from its table every time, never from context keys.
        rows=self.service.members(self.session_id,limit=20)['members']
        summary=self._catalog(rows)
        summary.update(dataset_count=self.binding['member_count'],count=self.binding['member_count'],truncated=len(rows)<self.binding['member_count'])
        state=memory.observe(state,'datasets.list',{},summary)
        selected=state.get('selected_cube_id')
        if selected:
            self.member(selected)
        return state

    def check_workspace(self, workspace):
        if workspace and workspace.get('cube_id'):
            if self.service.registry:
                self.service.registry.get(workspace['cube_id'])
                self.service.remember_canvas(self.session_id, workspace['cube_id'])
            if self.work:self.member(workspace['cube_id'])
            if workspace.get('gesture_ref'):
                state=self.annotations._states.get(workspace['cube_id']) if self.annotations else None
                if not state or workspace['gesture_ref'] not in state.gestures:
                    raise _failure('SESSION_REFERENCE_INVALID','画布手势已失效，请重新点选',409)

    def check_preprocess_discovery(self,name,args):
        """Discovery rows do not mint consent to their latest version references."""
        if name not in {'preprocess.run','preprocess.run_default','preprocess.run_batch','preprocess.compare',
                        'preprocess.draft_confirm','preprocess.draft_execute'}:
            return
        from .authorization import unquoted,QUESTION,NEGATION
        text=unquoted(self.user_content or (self.call_round or {}).get('user_message',''))
        from .preprocess_authorization import selected_inputs
        state=self.service.store.context(self.session_id)
        confirmed=selected_inputs(state,self.user_content or (self.call_round or {}).get('user_message',''))
        members=args.get('inputs') or args.get('items') or [args]
        if confirmed and name in {'preprocess.run','preprocess.run_default','preprocess.run_batch'}:
            references=[]
            for member in members:
                refs={key:member.get(key) for key in ('cube_id','annotation_version_id','recipe_version_id')}
                references.append(refs)
                if all(refs.values()) and refs not in confirmed:
                    raise DataError('PREPROCESS_REFERENCES_REQUIRED','提交范围或版本与本轮明确确认的方案不一致')
            if all(all(ref.values()) for ref in references):
                if (name!='preprocess.run_batch' and len(confirmed)!=1 or name=='preprocess.run_batch' and
                        (len(references)!=len(confirmed) or len({ref['cube_id'] for ref in references})!=len(confirmed))):
                    raise DataError('PREPROCESS_REFERENCES_REQUIRED','请用一次批量提交完整的已确认范围，不能缩为部分成员或重复成员')
            if all(ref in confirmed for ref in references):
                return
        if OPEN_ACCESS:
            return
        current_results=(re.search(r'(?:使用|采用|按|用).*(?:本轮|本次|这次|刚才|最新).*(?:结果|版本|标注|配方|查询|候选)',text)
                         and re.search(r'预处理|运行|执行|比较|对比',text)
                         and not re.search(QUESTION+'|'+NEGATION,text))
        if current_results:
            return
        with connect_database(self.service.database) as db:
            rows=db.execute("SELECT result_summary FROM agent_step WHERE session_id=? AND status='ok' "
                            "AND tool IN ('training_sets.candidates','annotations.context','annotations.status_batch','preprocess.recipes') "
                            'ORDER BY rowid DESC LIMIT 128',(self.session_id,)).fetchall()
            discovered=set()
            named_recipes=set()
            catalogue_seen=False
            for item in state.get('catalogs',{}).get('recipe',{}).get('items',[]):
                reference=item.get('ref')
                if reference and re.search(r'(?<![A-Za-z0-9])'+re.escape(reference)+r'(?![A-Za-z0-9])',text,re.I):
                    named_recipes.add(item['id'])
            for row in rows:
                result=json.loads(row[0])
                discovered.update(value for key,value in result.items() if isinstance(value,str) and
                    (key=='latest_annotation_version_id' or re.fullmatch(r'(?:item_\d+_(?:latest_)?annotation_version_id|recipe_\d+_version_id)',key)))
                if 'recipe_count' in result and not catalogue_seen and re.search(r'默认(?:配方|方案|预处理)',text):
                    for key,value in result.items():
                        if re.fullmatch(r'recipe_\d+_is_default',key) and value is True:
                            named_recipes.add(result[key.removesuffix('_is_default')+'_version_id'])
                    catalogue_seen=True
            def check(value,key):
                if not value or value not in discovered or value in text:
                    return
                if key=='recipe_version_id' and (value==state.get('recipe_version_id') or value in named_recipes):
                    return  # A user-selected catalogue reference remains explicit.
                if key=='annotation_version_id' and db.execute("SELECT 1 FROM agent_step WHERE session_id=? "
                    "AND tool='annotations.draft_confirm' AND status='ok' AND json_extract(result_summary,'$.version_id')=? LIMIT 1",
                    (self.session_id,value)).fetchone():
                    return  # A real, authorized save is distinct from a latest-item query.
                raise DataError('PREPROCESS_REFERENCES_REQUIRED','候选发现不代表确认，请明确使用的版本或授权本轮查询结果')
            members=args.get('inputs') or args.get('items') or [args]
            for member in members:
                for key in ('annotation_version_id','recipe_version_id'):
                    check(member.get(key),key)
                for value in member.get('recipe_version_ids',[]):
                    check(value,'recipe_version_id')

    @staticmethod
    def _catalog(rows):
        result={'dataset_count':len(rows),'count':len(rows),'truncated':False}
        for i,m in enumerate(rows,1):
            result.update({f'dataset_{i}_id':m['cube_id'],f'dataset_{i}_ref':m['ref'],f'dataset_{i}_name':m['display_name'],f'dataset_{i}_available':m['available']})
        return result

    def invoke(self, name, arguments):
        from spectrumagent.projects import bind, session_project
        with bind(session_project(self.service.database, self.session_id)):
            return self._invoke_project(name, arguments)

    def _invoke_project(self, name, arguments):
        if getattr(self, 'control', None) is not None:
            self.control.begin('tool')
        raw=self.validate(name,arguments).model_dump(mode='json', exclude_unset=name.startswith('experiments.') or name == 'modeling.regression_plan_update')
        args=self.effective_arguments(name,raw)
        self._check(name,args,scientific=True)
        grant = self.authorize_annotation(name, args)
        self.check_preprocess_discovery(name,args)
        annotation_target = None
        if name == 'annotations.task':
            if self.tasks is None:
                raise DataError('TOOL_NOT_IMPLEMENTED','后台任务服务未就绪')
            action=args['action']
            if action in {'get','cancel'}:
                row=(self.tasks.cancel if action=='cancel' else self.tasks.view)(self.session_id,args['task_id'])
                return {k:row.get(k) for k in ('task_id','task_status','phase','total','cancel_requested')} | {
                    'count_'+k:v for k,v in row['counts'].items()}
            parent=self.tasks.view(self.session_id,args['task_id'])
            grant=self.tasks.receipts[args['task_id']]['grant']
            return self.tasks.retry(self.session_id,args['task_id'],self.request_id or self.call_identity,
                                    grant,'failed' if action=='retry_failed' else 'remaining')
        if name == 'annotations.draft_confirm' or name == 'annotations.propose' and args.get('gesture_ref'):
            from .authorization import AnnotationAuthorization
            annotation_target = AnnotationAuthorization(self.service).verify_target(grant, self.engine, args['cube_id'])
        if self.tasks and name == 'annotations.prepare':
            grant = self.authorize_annotation(name, args)
            def prepare_one():
                from .authorization import AnnotationAuthorization
                cube = args['cube_id']
                if 'prepare' not in grant['operations']:
                    raise DataError('OPERATION_NOT_AUTHORIZED', '分割授权已撤销')
                target = AnnotationAuthorization(self.service).verify_target(grant, self.engine, cube)
                result = self.base.invoke(name,args)
                return {**result,'task_target_id':target}
            return self.tasks.run_sync(prepare_one)
        if self.tasks and name == 'annotations.prepare_batch':
            grant = self.authorize_annotation(name, args)
            if args.get('retry_of') in self.tasks.receipts:
                return self.tasks.retry(self.session_id, args['retry_of'], self.request_id or self.call_round['id'], grant)
            ids = args.get('cube_ids')
            if args.get('retry_of') and not ids:
                parent = self.batch.receipts.get(args['retry_of']) if self.batch else None
                if parent:
                    ids = [item['cube_id'] for item in parent['items'] if item['status'] != 'ready']
                    if not ids:
                        raise DataError('NOTHING_TO_RETRY', '父批次没有未就绪成员')
                    grant['expected_content_hashes'].update({m['cube_id']:m['content_hash'] for m in parent['members'] if m['cube_id'] in ids})
            if not ids and args.get('dataset_version_id'):
                ids = [m['cube_id'] for m in self.service.versions.get_frozen(args['dataset_version_id'])['members']]
            # Stable ordinal within this user turn, independent of provider call ID.
            slot = sum(1 for s in self.service.store.steps(self.session_id)
                       if self.call_round and s['round_id'] in {r['id'] for r in self.service.store.turn_rounds(self.session_id, self.call_round.get('turn_id') or self.call_round['id'])})
            return self.tasks.submit(self.session_id, self.request_id or self.call_round['id'], ids, grant, slot=slot, retry_of=args.get('retry_of'))
        from .tools.modeling import MODELING_TOOLS
        if name in MODELING_TOOLS:
            allowed = {r['cube_id'] for r in self.service._members(self.session_id)} if self.work else None
            from .tool_context import owner_session
            from spectrumagent.preprocess import submissions
            token = owner_session.set(self.session_id)
            try:
                turn = (self.call_round.get('turn_id') or self.call_round['id']) if self.call_round else None
                if turn:
                    slot, found = 0, False
                    for round_ in self.service.store.turn_rounds(self.session_id, turn):
                        for planned in json.loads(round_['calls_json']):
                            if round_['id'] == self.call_round['id'] and self.call_identity == round_['id'] + ':' + planned['id']:
                                found = True; break
                            slot += 1
                        if found: break
                    reference, source = submissions.conversation_submission(self.service.database, self.session_id, turn, self.request_id or turn)
                    submission = submissions.Submission(reference, str(slot), self.session_id, source)
                else:
                    submission = submissions.explicit_submission(owner=self.session_id)
                with submissions.execution_context(submission):
                    result = self.base.modeling.invoke(name, self.validate(name, args),
                        provenance=self.modeling_provenance(), allowed_cubes=allowed)
            finally:
                owner_session.reset(token)
            # Modeling owns its reference domain; never interpret a training ID
            # as preprocess_run, or update canvas/selection from a model result.
            return result
        if name=='annotations.propose' and not args.get('gesture_ref'):
            return {'cube_id':args['cube_id'],'status':'need_seed','class_code':args['class_code'],
                    'detail':'本会话没有有效种子，请在画布重新指认；共享草稿不继承其他会话手势。'}
        if self.work and name=='datasets.list':
            rows=self.service.members(self.session_id,limit=20)['members']
            return {**self._catalog(rows),'dataset_count':self.binding['member_count'],'count':self.binding['member_count'],'truncated':len(rows)<self.binding['member_count']}
        if self.work and name=='datasets.resolve':
            q=args['query'].strip().casefold()
            ordinal=re.fullmatch(r'(?:d|第)?(\d+)(?:个|项|个数据集)?',q)
            words={'第一项':1,'第一个':1,'第一个数据集':1,'第二项':2,'第二个':2,'第二个数据集':2,
                   '第三项':3,'第三个':3,'第三个数据集':3,'第一':1,'第二':2,'第三':3}
            ordinal_number=int(ordinal[1]) if ordinal else words.get(q,-1)
            with connect_database(self.service.database) as db:
                found=db.execute("SELECT m.ordinal,m.cube_id,json_extract(r.payload,'$.name') FROM agent_session_member m LEFT JOIN dataset_registry r ON r.id=m.cube_id WHERE m.session_id=? AND (m.ordinal=? OR m.cube_id=? OR substr(m.cube_id,1,?)=? OR lower(json_extract(r.payload,'$.name'))=?) ORDER BY m.ordinal LIMIT 51",(self.session_id,ordinal_number,q,len(q),q,q)).fetchall()
            from spectrumagent.api.registry import safe_name
            rows=[{'cube_id':cube,'ref':'D'+str(i),'display_name':safe_name(name) if name else '缺失样品','available':self.service.availability(cube)['available']} for i,cube,name in found]
            exact=[m for m in rows if q in {m['cube_id'].casefold(),m['display_name'].casefold()}]
            matches=exact or [m for m in rows if m['ref']=='D'+str(ordinal_number)]
            if not matches:matches=[m for m in rows if m['cube_id'].startswith(q) or m['display_name'].casefold().startswith(q)]
            if len(matches)==1:
                m=matches[0]
                return {'status':'resolved','cube_id':m['cube_id'],'display_name':m['display_name'],'dataset_ref':m['ref'],'available':m['available']}
            return {'status':'ambiguous' if matches else 'not_found','match_count':len(matches)}
        if self.work and name=='versions.list':
            return {'version_count':1,'truncated':False,'version_1_id':self.binding['dataset_version_ref'],'version_1_cube_count':self.binding['member_count'],'version_1_content_hash':self.binding['version_content_hash'],'version_1_is_frozen':1}
        from .tool_context import owner_session
        token = owner_session.set(self.session_id)
        try:
            from spectrumagent.preprocess import submissions
            if self.call_round is None or name not in {'workspace.preprocess','workspace.classify','preprocess.recipe_create','preprocess.recipe_version_add',
                    'preprocess.recipe_ensure','preprocess.run','preprocess.run_default','preprocess.run_batch','preprocess.compare',
                    'preprocess.draft_save','preprocess.draft_execute'}:
                submission = submissions.explicit_submission(owner=self.session_id, source='conversation_explicit')
            else:
                turn = self.call_round.get('turn_id') or self.call_round['id']
                rounds = self.service.store.turn_rounds(self.session_id, turn)
                # Stable position in the server-persisted plan; provider call IDs
                # are used only to locate that position, never as commit identity.
                slot = 0
                found = False
                for round_ in rounds:
                    for planned in json.loads(round_['calls_json']):
                        if round_['id'] == self.call_round['id'] and self.call_identity == round_['id'] + ':' + planned['id']:
                            found = True
                            break
                        slot += 1
                    if found:
                        break
                reference, source = submissions.conversation_submission(self.service.database, self.session_id, turn,
                                                                        self.request_id or turn)
                submission = submissions.Submission(reference, str(slot), self.session_id, source)
            with submissions.execution_context(submission):
                result=self.base.invoke(name,args)
                if (name in {'preprocess.run','preprocess.run_default','preprocess.run_batch','preprocess.draft_execute'}
                        and (result.get('run_id') or 'succeeded' in result)):
                    result={**result,'submission_ref':submission.submission_ref}
        finally:
            owner_session.reset(token)
        if name=='annotations.context':
            context=self.service.store.context(self.session_id)
            # A shared draft read cannot grant another session's canvas consent.
            if result.get('last_gesture_ref')!=context.get('gesture_ref'):
                result={k:v for k,v in result.items() if not k.startswith('last_gesture_')}
            if result.get('latest_candidate_ref') and not self.owns_candidate(result['latest_candidate_ref']):
                result={k:v for k,v in result.items() if not k.startswith('latest_candidate_')}
        if self.work:
            expected=args.get('cube_id') or args.get('dataset_id')
            if expected and result.get('cube_id',result.get('dataset_id',expected))!=expected or any(
                    args.get(k) and result.get(k) and args[k]!=result[k] for k in ('run_id','annotation_version_id','recipe_version_id','dataset_version_id')):
                raise _failure('SESSION_RESULT_SCOPE_MISMATCH','工具已返回但结果与有效输入不一致；未更新样品，未宣称回滚',409)
            for key,value in result.items():
                if value and (key in {'cube_id','dataset_id','open_cube_id'} or re.fullmatch(r'(?:item|run)_\d+_cube_id',key)):
                    try:self.member(value)
                    except Exception:
                        raise _failure('SESSION_RESULT_SCOPE_MISMATCH','工具已返回但结果目标越界；未更新当前样品，既有副作用未宣称回滚',409) from None
                table=('preprocess_run' if key=='run_id' or re.fullmatch(r'(?:item|run)_\d+_run_id',key) else
                       'annotation_version' if key=='annotation_version_id' or re.fullmatch(r'(?:item|run)_\d+_annotation_version_id',key)
                       or key=='version_id' and name=='annotations.draft_confirm' else None)
                if value and table:
                    try:
                        actual=self._reference_cube(table,value);self.member(actual)
                        if expected and actual!=expected:raise ValueError()
                    except Exception:
                        raise _failure('SESSION_RESULT_SCOPE_MISMATCH','工具已返回但产出引用归属不一致；未更新上下文，未宣称回滚',409) from None
        if name=='annotations.prepare_batch':
            if result.get('batch_ref') and self.batch:
                self.batch.receipts[result['batch_ref']]['owner_session_id']=self.session_id
                self.batch.receipts[result['batch_ref']]['owner_boot_id']=self.service.boot_id
            if self.work and not raw.get('dataset_version_id'):
                result={**result,'binding_source':'session_scope','original_dataset_version_id':None,'effective_dataset_version_id':args['dataset_version_id']}
        return {**result, 'task_target_id': annotation_target} if annotation_target else result
