import { invoke } from '@tauri-apps/api/core';
import type { AgentEvent, PlanDecision } from './sse.ts';

export type WorkspaceContext = { cube_id?: string; gesture_ref?: string };
export type MessageBody = { content: string; workspace?: WorkspaceContext } | { check_id: string; decision: 'approve' | 'reject' } | ({ plan_id: string } & PlanDecision);
export type AgentRequest = { op: 'create_session' } | { op: 'get_steps'; id: string } | { op: 'get_runtime' } | { op: 'send_message'; id: string; body: MessageBody };
export type Session = { id: string; title: string; skill_version_id: string; created_at: string;
  skill_name: string; skill_version_no: number; runtime: RuntimeInfo };
export type RuntimeInfo = { skill_name: string | null; skill_version_id: string | null; skill_version_no: number | null;
  tool_catalogue_version: number; tool_count: number; sessions_by_skill: Record<string, number>;
  sessions_upgraded?: number };
export type Steps = { session_id: string; steps: { seq: number; tool: string; status: string; arguments_json: string;
  result_digest: string | null; result_summary: string; latency_ms: number; created_at: string }[] };
export type EventBatch = { events: AgentEvent[] };
export type InvokeAgent = <T>(command: string, args: { request: AgentRequest }) => Promise<T>;

export const requests = {
  createSession: (): AgentRequest => ({ op: 'create_session' }),
  sendMessage: (id: string, body: MessageBody): AgentRequest => ({ op: 'send_message', id,
    body: 'content' in body ? { content: body.content, ...(body.workspace ? { workspace: workspaceContext(body.workspace) } : {}) } : 'check_id' in body ? { check_id: body.check_id, decision: body.decision }
      : body.action === 'approve' ? { plan_id: body.plan_id, action: 'approve' }
        : body.action === 'reject' ? { plan_id: body.plan_id, action: 'reject', reason: body.reason }
          : { plan_id: body.plan_id, action: body.action, step_ref: body.step_ref, reason: body.reason } }),
  getSteps: (id: string): AgentRequest => ({ op: 'get_steps', id }),
  getRuntime: (): AgentRequest => ({ op: 'get_runtime' }),
};

// Names, paths, geometry and component state stay local. Only opaque references
// may accompany a normal message; confirmation continuations retain their IDs.
export function workspaceContext(value: WorkspaceContext): WorkspaceContext {
  return { ...(typeof value.cube_id === 'string' && value.cube_id ? { cube_id: value.cube_id } : {}),
    ...(typeof value.gesture_ref === 'string' && value.gesture_ref ? { gesture_ref: value.gesture_ref } : {}) };
}

export function agentClient(send: InvokeAgent = invoke) {
  const forward = <T>(request: AgentRequest) => send<T>('agent_forward', { request });
  return {
    createSession: () => forward<Session>(requests.createSession()),
    sendMessage: (id: string, body: MessageBody) => forward<EventBatch>(requests.sendMessage(id, body)),
    getSteps: (id: string) => forward<Steps>(requests.getSteps(id)),
    getRuntime: () => forward<RuntimeInfo>(requests.getRuntime()),
  };
}
export const agent = agentClient();
