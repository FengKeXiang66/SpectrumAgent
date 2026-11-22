"""Shared runtime recipe drafts, optimistic revisions and fixed execution consent."""
from contextvars import ContextVar
from dataclasses import dataclass
import json
import sqlite3
import re
from uuid import uuid4

from backend.database import connect_database
from spectrumagent.data import DataError
from spectrumagent.data.validation import safe_error
from .registry import effective_pipeline
from .recipes import pipeline_identity, RECIPE_HASH_ALGORITHM
from . import submissions


DDL = (
    'CREATE TABLE IF NOT EXISTS recipe_runtime_state ('
    'recipe_id TEXT PRIMARY KEY REFERENCES preprocess_recipe(id),deleted INTEGER NOT NULL CHECK(deleted IN (0,1)),updated_at TEXT NOT NULL)',
    'CREATE TABLE IF NOT EXISTS recipe_draft ('
    'draft_id TEXT PRIMARY KEY NOT NULL,owner_session_id TEXT NOT NULL,revision INTEGER NOT NULL CHECK(revision>0),'
    'source_recipe_version_id TEXT REFERENCES preprocess_recipe_version(id),pipeline TEXT NOT NULL,'
    "validation_result TEXT NOT NULL,updated_at TEXT NOT NULL,metadata TEXT NOT NULL DEFAULT '{}')",
    'CREATE TABLE IF NOT EXISTS recipe_current_draft ('
    'owner_session_id TEXT PRIMARY KEY NOT NULL,draft_id TEXT NOT NULL REFERENCES recipe_draft(draft_id))',
    'CREATE TABLE IF NOT EXISTS recipe_execution_confirmation ('
    'confirmation_id TEXT PRIMARY KEY NOT NULL,owner_session_id TEXT NOT NULL,draft_id TEXT NOT NULL REFERENCES recipe_draft(draft_id),'
    'revision INTEGER NOT NULL,recipe_version_id TEXT NOT NULL REFERENCES preprocess_recipe_version(id),'
    'pipeline_sha256 TEXT NOT NULL,inputs_json TEXT NOT NULL,input_fingerprints TEXT NOT NULL,authorization_source TEXT NOT NULL,'
    "status TEXT NOT NULL CHECK(status IN ('valid','accepted','invalid')),accepted_submission_ref TEXT,created_at TEXT NOT NULL)",
)


def migrate(db):
    for statement in DDL:
        db.execute(statement)


def assert_available(db, *, recipe_id=None, version_id=None):
    if version_id is not None:
        row = db.execute('SELECT recipe_id FROM preprocess_recipe_version WHERE id=?', (str(version_id),)).fetchone()
        if row is None:
            error=DataError('RECIPE_VERSION_NOT_FOUND', '配方版本不存在');error.status_code=404;raise error
        recipe_id = row[0]
    if not db.execute('SELECT 1 FROM preprocess_recipe WHERE id=?', (str(recipe_id),)).fetchone():
        error=DataError('RECIPE_NOT_FOUND', '配方不存在');error.status_code=404;raise error
    if db.execute('SELECT 1 FROM recipe_runtime_state WHERE recipe_id=? AND deleted=1', (str(recipe_id),)).fetchone():
        error=DataError('RECIPE_DELETED', '配方已在本次应用运行中删除；历史可读，新提交须先明确恢复');error.status_code=409;raise error


def assert_runs_available(db, run_ids):
    for identifier in run_ids:
        row = db.execute('SELECT recipe_version_id FROM preprocess_run WHERE id=?', (identifier,)).fetchone()
        if row:
            assert_available(db, version_id=row[0])


def validate_draft(pipeline, registry):
    try:
        effective_pipeline(pipeline, registry)
        return {'valid':True, 'fields':[], 'recipe_pipeline_sha256':pipeline_identity(pipeline,registry)[1]}
    except DataError as error:
        summary = safe_error(error)
        return {'valid':False, 'error':error.code, 'fields':[
            {'field':summary[f'field_{i}_location'], 'message':summary[f'field_{i}_message']}
            for i in range(1,9) if f'field_{i}_location' in summary]}


def differences(old, new):
    left, right = old.get('steps',[]), new.get('steps',[])
    result = []
    for index in range(max(len(left),len(right))):
        if index >= len(left) or index >= len(right):
            result.append({'field':f'steps.{index}', 'change':'added' if index >= len(left) else 'removed'})
        elif left[index] != right[index]:
            for key in ('op','version','params'):
                if left[index].get(key) != right[index].get(key):
                    result.append({'field':f'steps.{index}.{key}', 'change':'changed'})
    return result[:30]


def _draft(db, identifier, owner):
    db.row_factory = sqlite3.Row
    row = db.execute('SELECT * FROM recipe_draft WHERE draft_id=? AND owner_session_id=?', (identifier,owner)).fetchone()
    if row is None:
        raise DataError('DRAFT_NOT_FOUND', '配方草稿不存在或不属于当前会话')
    result = dict(row)
    for key in ('pipeline','validation_result','metadata'):
        result[key] = json.loads(result[key])
    return result


def _revision(draft, expected, proposed=None):
    if type(expected) is not int or expected < 1:
        raise DataError('INVALID_REQUEST','expected_revision 须为正整数')
    if draft['revision'] != expected:
        raise DataError('RECIPE_DRAFT_REVISION_CONFLICT', '草稿已更新，请读取最新修订后合并',
                        latest_revision=draft['revision'], differences=differences(proposed or {'steps':[]},draft['pipeline']))


def _owner(db, owner):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='agent_session'").fetchone() or not db.execute(
            'SELECT 1 FROM agent_session WHERE id=?',(owner,)).fetchone():
        raise DataError('DRAFT_OWNER_REQUIRED', '草稿须绑定本次应用运行中的聊天会话')


@dataclass(frozen=True)
class ConfirmationContext:
    confirmation_id: str
    owner_session_id: str
    inputs_json: str


current_confirmation = ContextVar('recipe_confirmation', default=None)


def assert_confirmation(db, submission, member, fingerprint=None):
    context = current_confirmation.get()
    if context is None:
        return  # Legacy explicit version submissions retain their authorization boundary.
    row = db.execute('SELECT draft_id,revision,recipe_version_id,pipeline_sha256,inputs_json,status,accepted_submission_ref,input_fingerprints '
                     'FROM recipe_execution_confirmation WHERE confirmation_id=? AND owner_session_id=?',
                     (context.confirmation_id,context.owner_session_id)).fetchone()
    accepted = row is not None and row[6] == submission.submission_ref and submissions.admitted(submission,member)
    if row is None or (row[5] == 'invalid' and not accepted) or row[4] != context.inputs_json or (row[6] and row[6] != submission.submission_ref):
        raise DataError('RECIPE_CONFIRMATION_STALE', '执行确认已失效，请基于当前定义和输入范围重新提交')
    if not accepted:
        draft = _draft(db,row[0],context.owner_session_id)
        if draft['revision'] != row[1] or pipeline_identity(draft['pipeline'])[1] != row[3]:
            raise DataError('RECIPE_CONFIRMATION_STALE', '草稿定义已改变，旧确认不能执行新内容')
    expected = {**member, 'recipe_version_id':row[2]}
    if member['recipe_version_id'] != row[2] or expected not in json.loads(row[4]):
        raise DataError('RECIPE_CONFIRMATION_STALE', '输入范围与确认不一致')
    if fingerprint is not None and json.loads(row[7]).get(member['cube_id']) != fingerprint:
        raise DataError('SOURCE_CHANGED','输入内容已改变，旧执行确认不再适用')
    db.execute("UPDATE recipe_execution_confirmation SET status='accepted',accepted_submission_ref=? WHERE confirmation_id=?",
               (submission.submission_ref,context.confirmation_id))


class RecipeDrafts:
    def __init__(self, store, runner=None):
        self.store, self.database = store, store.database
        self.runner = runner

    def get(self, owner, draft_id=None):
        with connect_database(self.database) as db:
            if draft_id is None:
                row = db.execute('SELECT draft_id FROM recipe_current_draft WHERE owner_session_id=?',(owner,)).fetchone()
                if row is None:
                    return None
                draft_id = row[0]
            return _draft(db,draft_id,owner)

    def create(self, owner, source_recipe_version_id=None, *, new_plan=False):
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            _owner(db,owner)
            current = db.execute('SELECT draft_id FROM recipe_current_draft WHERE owner_session_id=?',(owner,)).fetchone()
            if current and not new_plan:
                draft = _draft(db,current[0],owner)
                if source_recipe_version_id is None or draft['source_recipe_version_id'] == source_recipe_version_id:
                    return draft
            pipeline = {'steps':[]}
            if source_recipe_version_id is not None:
                assert_available(db,version_id=source_recipe_version_id)
                pipeline = json.loads(db.execute('SELECT pipeline FROM preprocess_recipe_version WHERE id=?',
                                                (source_recipe_version_id,)).fetchone()[0])
            identifier = str(uuid4())
            db.execute('INSERT INTO recipe_draft (draft_id,owner_session_id,revision,source_recipe_version_id,pipeline,validation_result,updated_at) VALUES (?,?,1,?,?,?,?)',
                       (identifier,owner,source_recipe_version_id,submissions.encode(pipeline),
                        submissions.encode(validate_draft(pipeline,self.store.registry)),submissions.now()))
            db.execute('INSERT INTO recipe_current_draft VALUES (?,?) ON CONFLICT(owner_session_id) DO UPDATE SET draft_id=excluded.draft_id',
                       (owner,identifier))
            return _draft(db,identifier,owner)

    def update(self, owner, draft_id, expected_revision, pipeline=None, metadata=None):
        if metadata is not None:
            if (type(metadata) is not dict or set(metadata)-{'code','name','description','note'}
                    or any(type(v) is not str or len(v) > (2000 if k in {'description','note'} else 80 if k=='name' else 64) for k,v in metadata.items())
                    or metadata.get('code') and not re.fullmatch(r'[a-z0-9][a-z0-9-]*',metadata['code'])):
                raise DataError('INVALID_REQUEST', '草稿名称或编码格式不合法')
        if pipeline is None:
            pipeline = self.get(owner,draft_id)['pipeline']
        if not isinstance(pipeline,dict) or set(pipeline) != {'steps'} or type(pipeline['steps']) is not list or len(pipeline['steps']) > 30:
            raise DataError('INVALID_REQUEST', '草稿需要有界 steps 列表')
        if any(type(step) is not dict or set(step) != {'op','version','params'} or not isinstance(step['op'],str)
               or type(step['version']) is not int or step['version'] < 1 or type(step['params']) is not dict for step in pipeline['steps']):
            raise DataError('INVALID_REQUEST','草稿步骤须明确 op、version 和 params 对象')
        encoded = submissions.encode(pipeline)
        if len(encoded.encode()) > 65536:
            raise DataError('INVALID_REQUEST', '草稿超过大小限制')
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            draft = _draft(db,draft_id,owner)
            _revision(draft,expected_revision,pipeline)
            changes = differences(draft['pipeline'],pipeline)
            merged = {**draft['metadata'], **(metadata or {})}
            if merged.get('name') and not merged.get('code'):
                merged['code'] = 'recipe-' + draft_id.replace('-','')[:12]
            db.execute('UPDATE recipe_draft SET pipeline=?,validation_result=?,metadata=?,revision=revision+1,updated_at=? WHERE draft_id=?',
                       (encoded,submissions.encode(validate_draft(pipeline,self.store.registry)),submissions.encode(merged),submissions.now(),draft_id))
            db.execute("UPDATE recipe_execution_confirmation SET status='invalid' WHERE draft_id=?",(draft_id,))
            return {**_draft(db,draft_id,owner), 'differences':changes}

    def save(self, owner, draft_id, expected_revision, *, recipe_id=None, code=None, name=None, description=None, note=None):
        submission = submissions.current_submission.get() or submissions.explicit_submission(owner=owner,source='direct_save')
        if submission.owner_session_id != owner:
            raise DataError('OPERATION_OWNER_MISMATCH','提交上下文与草稿会话不一致')
        payload = dict(owner=owner,draft_id=draft_id,revision=expected_revision,recipe_id=recipe_id,code=code,name=name,description=description,note=note)
        with self.store.lock, connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            operation, fresh = submissions.begin(db,submission,'preprocess.draft_save',payload)
            if not fresh:
                return submissions.receipt(operation)
            draft = _draft(db,draft_id,owner)
            _revision(draft,expected_revision)
            code = code if code is not None else draft['metadata'].get('code')
            name = name if name is not None else draft['metadata'].get('name')
            description = description if description is not None else draft['metadata'].get('description')
            note = note if note is not None else draft['metadata'].get('note')
            encoded,digest = pipeline_identity(draft['pipeline'],self.store.registry)
            existing=None
            if recipe_id is None:
                if not code or not name or not code.strip() or not name.strip():
                    raise DataError('INVALID_REQUEST', '另存新配方需要明确 code 与 name')
                recipe_id,version_id = str(uuid4()),str(uuid4())
                self.store._create(db,recipe_id,version_id,submissions.now(),code,name,description,encoded,note,digest)
                version_no = 1
            else:
                assert_available(db,recipe_id=recipe_id)
                source=db.execute('SELECT id,version_no,pipeline FROM preprocess_recipe_version WHERE id=? AND recipe_id=?',
                                  (draft['source_recipe_version_id'],recipe_id)).fetchone()
                latest=db.execute('SELECT id,version_no,pipeline FROM preprocess_recipe_version WHERE recipe_id=? ORDER BY version_no DESC LIMIT 1',
                                  (recipe_id,)).fetchone()
                existing=next((row for row in (latest,) if row is not None and self.store._pipeline(row[2])[0]==encoded),None)
                if existing is not None:
                    version_id,version_no=existing[0],existing[1]
                else:
                    row = self.store._update_current(db,dict(id=str(uuid4()),recipe_id=recipe_id,pipeline=encoded,note=note,created_at=submissions.now()),digest)
                    version_id,version_no = row['id'],row['version_no']
            db.execute('UPDATE recipe_draft SET source_recipe_version_id=?,revision=revision+1,updated_at=? WHERE draft_id=?',
                       (version_id,submissions.now(),draft_id))
            db.execute("UPDATE recipe_execution_confirmation SET status='invalid' WHERE draft_id=?",(draft_id,))
            result = dict(draft_id=draft_id,revision=draft['revision']+1,recipe_id=recipe_id,recipe_version_id=version_id,
                          version_no=version_no,recipe_pipeline_sha256=digest,recipe_hash_alg=RECIPE_HASH_ALGORITHM)
            result['reused_existing_version']=existing is not None
            submissions.finish(db,operation['operation_id'],'succeeded',result)
            return result

    def confirm(self, owner, draft_id, expected_revision, recipe_version_id, inputs, authorization_source):
        if not inputs or len(inputs) > 32 or len({m['cube_id'] for m in inputs}) != len(inputs):
            raise DataError('INVALID_REQUEST', '确认须绑定非空且不重复的固定输入范围')
        with connect_database(self.database) as db:
            draft=_draft(db,draft_id,owner)
            _revision(draft,expected_revision)
            if draft['source_recipe_version_id'] != recipe_version_id:
                raise DataError('RECIPE_CONFIRMATION_STALE','请明确指定当前已保存的配方版本')
        fingerprints = {}
        if self.runner is None:
            raise DataError('TOOL_NOT_IMPLEMENTED','执行确认缺少输入核验服务')
        for item in inputs:
            prepared = self.runner._preflight(item['cube_id'],item['annotation_version_id'],recipe_version_id,32,'clip')
            fingerprints[item['cube_id']] = prepared[-1]
            del prepared
        with connect_database(self.database) as db:
            db.execute('BEGIN IMMEDIATE')
            draft = _draft(db,draft_id,owner)
            _revision(draft,expected_revision)
            assert_available(db,version_id=recipe_version_id)
            version = db.execute('SELECT pipeline FROM preprocess_recipe_version WHERE id=?',(recipe_version_id,)).fetchone()
            _,digest = pipeline_identity(draft['pipeline'],self.store.registry)
            if pipeline_identity(version[0],self.store.registry)[1] != digest or draft['source_recipe_version_id'] != recipe_version_id:
                raise DataError('RECIPE_CONFIRMATION_STALE', '请先保存当前有效定义，并明确指定该配方版本')
            for item in inputs:
                annotation = db.execute('SELECT cube_id FROM annotation_version WHERE id=?',(item['annotation_version_id'],)).fetchone()
                if item['recipe_version_id'] != recipe_version_id or annotation is None or annotation[0] != item['cube_id']:
                    raise DataError('RECIPE_CONFIRMATION_STALE', '确认范围内引用不一致')
            identifier = str(uuid4())
            db.execute('INSERT INTO recipe_execution_confirmation '
                       '(confirmation_id,owner_session_id,draft_id,revision,recipe_version_id,pipeline_sha256,inputs_json,input_fingerprints,authorization_source,status,created_at) '
                       "VALUES (?,?,?,?,?,?,?,?,?,'valid',?)", (identifier,owner,draft_id,expected_revision,recipe_version_id,digest,
                       submissions.encode(inputs),submissions.encode(fingerprints),authorization_source,submissions.now()))
            return {'confirmation_id':identifier,'draft_id':draft_id,'revision':expected_revision,'recipe_version_id':recipe_version_id}

    def execute(self, runner, owner, confirmation_id, inputs):
        return self._execute(runner, owner, confirmation_id, inputs)

    def retry(self, runner, owner, confirmation_id, inputs, retry_of_submission):
        return self._execute(runner, owner, confirmation_id, inputs, retry_of_submission=retry_of_submission)

    def _execute(self, runner, owner, confirmation_id, inputs, *, retry_of_submission=None):
        if not inputs:
            raise DataError('INVALID_REQUEST','执行范围不能为空')
        context = ConfirmationContext(confirmation_id,owner,submissions.encode(inputs))
        submission = submissions.current_submission.get() or submissions.explicit_submission(owner=owner,source='direct_execute')
        if submission.owner_session_id != owner:
            raise DataError('OPERATION_OWNER_MISMATCH','提交上下文与草稿会话不一致')
        kind = 'preprocess.draft_retry' if retry_of_submission else 'preprocess.draft_execute'
        payload = {'owner':owner,'confirmation_id':confirmation_id,'inputs':inputs}
        if retry_of_submission:
            payload['retry_of_submission'] = retry_of_submission
        with submissions.execution_context(submission):
            with connect_database(self.database) as db:
                db.execute('BEGIN IMMEDIATE')
                operation,fresh = submissions.begin(db,submission,kind,payload)
                if not fresh:
                    if operation['receipt_json']:
                        recorded=json.loads(operation['receipt_json'])
                        if recorded.get('rejected'):
                            raise DataError(recorded['error'],recorded['detail'])
                    return submissions.receipt(operation)
                batch_submission = submissions.child(submission,'batch')
                if retry_of_submission:
                    from .retry import bind
                    original_reference,batch_submission,_=bind(db,retry_of_submission,batch_submission,[item['cube_id'] for item in inputs])
                for item in inputs:
                    assert_available(db,version_id=item['recipe_version_id'])
                    assert_confirmation_in_context(db,submission,item,context)
            if not submissions.claim(self.database,operation['operation_id'],runner.executor_id):
                raise DataError('OPERATION_IN_PROGRESS','同一执行提交已受理，请核对原操作')
            token = current_confirmation.set(context)
            admission=submissions.current_admission.set(submissions.BatchAdmission(submission.submission_ref,
                frozenset(tuple(row[k] for k in ('cube_id','annotation_version_id','recipe_version_id')) for row in inputs)))
            try:
                with submissions.execution_context(batch_submission):
                    result = runner.run_batch(inputs)
                if retry_of_submission:
                    result={**result,'retry_of_submission':original_reference}
                with connect_database(self.database) as db:
                    db.execute('BEGIN IMMEDIATE')
                    submissions.finish(db,operation['operation_id'],'failed' if result['failed'] else 'succeeded',result)
                return result
            except Exception as error:
                try:
                    # A transactionally rejected retry has not admitted a batch.
                    # Record that known outcome, rather than inventing uncertainty.
                    with connect_database(self.database) as db:
                        admitted=db.execute('SELECT 1 FROM business_operation WHERE submission_ref=? AND action_ref=?',
                            (batch_submission.submission_ref,batch_submission.action_ref)).fetchone()
                        if retry_of_submission and not admitted and isinstance(error,DataError) and error.code=='PREPROCESS_RETRY_SCOPE_MISMATCH':
                            db.execute('BEGIN IMMEDIATE')
                            submissions.finish(db,operation['operation_id'],'failed',{'rejected':True,**safe_error(error)})
                        else:
                            submissions.uncertain(self.database,operation['operation_id'])
                except Exception:
                    pass
                raise
            finally:
                submissions.current_admission.reset(admission)
                current_confirmation.reset(token)


def assert_confirmation_in_context(db,submission,item,context):
    token = current_confirmation.set(context)
    try:
        assert_confirmation(db,submission,item)
    finally:
        current_confirmation.reset(token)
