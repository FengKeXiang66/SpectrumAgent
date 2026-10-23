import { invoke } from '@tauri-apps/api/core';
import type { AgentEvent } from './sse.ts';

export type MessageBody = { content: string } | { check_id: string; decision: 'approve' | 'reject' };
export type AgentRequest = { op: 'create_session' } | { op: 'get_steps'; id: string } | { op: 'send_message'; id: string; body: MessageBody };
export type Session = { id: string; title: string; skill_version_id: string; created_at: string };
export type Steps = { session_id: string; steps: { seq: number; tool: string; status: string; arguments_json: string;
  result_digest: string | null; result_summary: string; latency_ms: number; created_at: string }[] };
export type EventBatch = { events: AgentEvent[] };
export type InvokeAgent = <T>(command: string, args: { request: AgentRequest }) => Promise<T>;

export const requests = {
  createSession: (): AgentRequest => ({ op: 'create_session' }),
  sendMessage: (id: string, body: MessageBody): AgentRequest => ({ op: 'send_message', id,
    body: 'content' in body ? { content: body.content } : { check_id: body.check_id, decision: body.decision } }),
  getSteps: (id: string): AgentRequest => ({ op: 'get_steps', id }),
};

export function agentClient(send: InvokeAgent = invoke) {
  const forward = <T>(request: AgentRequest) => send<T>('agent_forward', { request });
  return {
    createSession: () => forward<Session>(requests.createSession()),
    sendMessage: (id: string, body: MessageBody) => forward<EventBatch>(requests.sendMessage(id, body)),
    getSteps: (id: string) => forward<Steps>(requests.getSteps(id)),
  };
}
export const agent = agentClient();
