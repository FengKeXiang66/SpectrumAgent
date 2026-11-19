"""One submission contract for typed mode choices and structured UI actions."""
from spectrumagent.data import DataError
from .sessions import digest


def submit_flow(service, tasks, sid, request_id, cube_ids, mode, state, grant):
    if tasks is None:
        raise DataError('TOOL_NOT_IMPLEMENTED', '分割服务不可用')
    fingerprint = digest({'cube_ids': cube_ids, 'mode': mode})
    old = state.get('annotation_flow_request')
    if old and old['request_id'] == request_id:
        if old['fingerprint'] != fingerprint:
            raise DataError('IDEMPOTENCY_CONFLICT', '模式请求 ID 已被占用')
        return old['response']
    ids = cube_ids if mode == 'all' else cube_ids[:1]
    accepted = tasks.submit(sid, request_id, ids, grant)
    response = {**accepted, 'mode': mode, 'flow_id': grant['authorization_id'], 'member_count': len(cube_ids)}
    service.flow_requests[(sid, request_id)] = response
    state['annotation_flow_request'] = {'request_id': request_id, 'fingerprint': fingerprint,
        'authorization_id': grant['authorization_id'], 'mode': mode, 'response': response}
    state.pop('pending_clarify', None)
    service.store.save_context(sid, state)
    return response


def flow_reply(response):
    return {
        'content': ('已选择提前生成全部，超像素任务已受理。' if response['mode'] == 'all'
                    else '已选择逐张生成，首张超像素准备任务已受理。'),
        'step_count': 0, 'task_result': 'working', 'annotation_task_id': response['task_id'],
        'annotation_flow_id': response['flow_id'], 'annotation_mode': response['mode'],
        'annotation_member_count': response['member_count'],
    }
