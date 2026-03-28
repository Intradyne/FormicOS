/**
 * Wave 69 Track 5: AG-UI compatible event shape mapping.
 *
 * Thin mapping layer that converts FormicOS WebSocket events into AG-UI
 * standard event shapes. Export mapping functions, not a transport layer.
 * Intended for future AG-UI client integration.
 */

/** AG-UI standard event types. */
export type AguiEventType =
  | 'STEP_STARTED'
  | 'STEP_FINISHED'
  | 'TOOL_CALL_END'
  | 'STATE_DELTA';

export interface AguiEvent {
  type: AguiEventType;
  stepId?: string;
  status?: 'success' | 'error' | 'running';
  toolName?: string;
  toolResult?: string;
  delta?: Record<string, unknown>;
  timestamp?: string;
}

/**
 * Map a FormicOS ColonySpawned event to AG-UI STEP_STARTED.
 */
export function mapColonySpawned(e: Record<string, unknown>): AguiEvent {
  const colonyId = (e.colony_id ?? e.colonyId ?? '') as string;
  return {
    type: 'STEP_STARTED',
    stepId: colonyId,
    status: 'running',
    timestamp: (e.timestamp ?? '') as string,
  };
}

/**
 * Map a FormicOS ColonyCompleted/ColonyFailed event to AG-UI STEP_FINISHED.
 */
export function mapColonyFinished(e: Record<string, unknown>): AguiEvent {
  const colonyId = (e.colony_id ?? e.colonyId ?? '') as string;
  const eventType = (e.type ?? '') as string;
  return {
    type: 'STEP_FINISHED',
    stepId: colonyId,
    status: eventType === 'ColonyCompleted' ? 'success' : 'error',
    timestamp: (e.timestamp ?? '') as string,
  };
}

/**
 * Map a thread state change to AG-UI STATE_DELTA.
 */
export function mapStateDelta(delta: Record<string, unknown>): AguiEvent {
  return {
    type: 'STATE_DELTA',
    delta,
  };
}
