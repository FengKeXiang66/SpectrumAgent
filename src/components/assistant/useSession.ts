import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { agent, type MessageBody, type RuntimeInfo, type WorkspaceContext } from './api.ts';
import { initialChat, reduceChat, requestError, validateWorkspaceEvent, type WorkspaceEventData } from './sse.ts';
import { changedCubes, datasetChoices, proposedCandidates } from './presentation.ts';
import type { DatasetRecord } from '../datasets/types.ts';

export default function useSession({ enabled, generation, workspace = {}, records = [], displayName,
  onWorkspaceChange, onWorkspaceNavigate, onPreviewCandidate, onDataChanged }: {
  enabled: boolean; generation: number; workspace?: WorkspaceContext; records?: DatasetRecord[]; displayName?: string;
  onWorkspaceChange?(workspace: WorkspaceContext): void;
  onWorkspaceNavigate?(selection: WorkspaceEventData): void;
  onPreviewCandidate?(cubeId: string, candidateRef: string): void;
  onDataChanged?(cubeIds: string[]): void;
}) {
  const [state, dispatch] = useReducer(reduceChat, initialChat);
  const [content, setContent] = useState('');
  const [runtime, setRuntime] = useState<RuntimeInfo | null>(null);
  const sessionId = useRef<string | null>(null);
  // One guard covers both views, including clicks before disabled buttons commit.
  const inFlight = useRef(false);
  const epoch = useRef(0);
  const startNew = useCallback(() => {
    epoch.current++;
    sessionId.current = null; dispatch({ type: 'reset' }); setContent('');
    inFlight.current = false;
  }, []);
  // Replaces AssistantBar's former generation key without tying state to a screen.
  useEffect(() => {
    startNew(); setRuntime(null);
    if (!enabled) return;
    let cancelled = false;
    void agent.getRuntime().then(value => { if (!cancelled) setRuntime(value); }).catch(() => undefined);
    return () => { cancelled = true; epoch.current++; };
  }, [enabled, generation, startNew]);
  const choices = datasetChoices(state.entries, records);
  const selected = records.find(record => record.id === workspace.cube_id);
  const selectedChoice = choices.find(choice => choice.id === workspace.cube_id);
  const request = async (body: MessageBody) => {
    if (!enabled || inFlight.current) return;
    if ('content' in body && !body.content.trim()) return;
    if ('check_id' in body && (!state.pending || !('check_id' in state.pending) || state.pending.check_id !== body.check_id)) return;
    if ('plan_id' in body && (!state.pending || !('plan_id' in state.pending) || state.pending.plan_id !== body.plan_id)) return;
    const requestWorkspace = 'content' in body ? body.workspace ?? workspace : workspace;
    const requestEpoch = epoch.current;
    inFlight.current = true;
    if ('content' in body) dispatch({ type: 'send', content: body.content });
    else if ('check_id' in body) dispatch({ type: 'decision', decision: body.decision });
    else dispatch({ type: 'plan', ...body });
    try {
      if (sessionId.current === null) {
        const created = await agent.createSession();
        if (epoch.current !== requestEpoch) return;
        sessionId.current = created.id;
      }
      const result = await agent.sendMessage(sessionId.current, 'content' in body
        ? { content: body.content, ...(requestWorkspace.cube_id ? { workspace: requestWorkspace } : {}) } : body);
      if (epoch.current !== requestEpoch) return;
      for (const event of result.events) if (event.event === 'workspace') validateWorkspaceEvent(event.data);
      dispatch({ type: 'events', events: result.events });
      for (const event of result.events) if (event.event === 'workspace') {
        onWorkspaceChange?.({ cube_id: event.data.cube_id, ...(event.data.gesture_ref ? { gesture_ref: event.data.gesture_ref } : {}) });
        onWorkspaceNavigate?.(event.data);
      }
      for (const preview of proposedCandidates(result.events)) onPreviewCandidate?.(preview.cube_id, preview.candidate_ref);
      const changed = changedCubes(result.events, requestWorkspace);
      if (changed.length) onDataChanged?.(changed);
      if ('content' in body) setContent('');
    } catch (error) {
      if (epoch.current === requestEpoch) dispatch({ type: 'failed', detail: requestError(error) });
    } finally { if (epoch.current === requestEpoch) inFlight.current = false; }
  };
  return { state, dispatch, content, setContent, runtime, request, choices, selected, selectedChoice, startNew,
    enabled, workspace, records, displayName, onWorkspaceChange };
}

export type AssistantSession = ReturnType<typeof useSession>;
