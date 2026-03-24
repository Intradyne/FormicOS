/**
 * FormicOS WebSocket client — thin transport layer.
 * Connects to the surface WS endpoint, sends commands, dispatches messages.
 */
import type { WSCommand, WSCommandAction, WSMessage } from '../types.js';

export type ConnectionState = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface WSClientOptions {
  url?: string;
  reconnectMs?: number;
  maxRetries?: number;
}

type Listener = (msg: WSMessage) => void;
type StateListener = (state: ConnectionState) => void;

export class WSClient {
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private stateListeners = new Set<StateListener>();
  private _state: ConnectionState = 'disconnected';
  private retries = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly url: string;
  private readonly reconnectMs: number;
  private readonly maxRetries: number;

  constructor(opts: WSClientOptions = {}) {
    const loc = globalThis.location;
    const proto = loc?.protocol === 'https:' ? 'wss:' : 'ws:';
    this.url = opts.url ?? `${proto}//${loc?.host ?? 'localhost:8080'}/ws`;
    this.reconnectMs = opts.reconnectMs ?? 3000;
    this.maxRetries = opts.maxRetries ?? 10;
  }

  get state(): ConnectionState { return this._state; }

  private setState(s: ConnectionState) {
    this._state = s;
    this.stateListeners.forEach(fn => fn(s));
  }

  connect(): void {
    if (this.ws) return;
    this.setState('connecting');
    const ws = new WebSocket(this.url);

    ws.onopen = () => {
      this.retries = 0;
      this.setState('connected');
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as WSMessage;
        this.listeners.forEach(fn => fn(msg));
      } catch { /* ignore malformed frames */ }
    };

    ws.onclose = () => {
      this.ws = null;
      this.setState('disconnected');
      this.scheduleReconnect();
    };

    ws.onerror = () => {
      this.ws = null;
      this.setState('error');
      this.scheduleReconnect();
    };

    this.ws = ws;
  }

  disconnect(): void {
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null; }
    this.retries = this.maxRetries; // prevent auto-reconnect
    this.ws?.close();
    this.ws = null;
    this.setState('disconnected');
  }

  send(action: WSCommandAction, workspaceId: string, payload: Record<string, unknown> = {}): void {
    const cmd: WSCommand = { action, workspaceId, payload };
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(cmd));
    }
  }

  onMessage(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => { this.listeners.delete(fn); };
  }

  onStateChange(fn: StateListener): () => void {
    this.stateListeners.add(fn);
    return () => { this.stateListeners.delete(fn); };
  }

  private scheduleReconnect(): void {
    if (this.retries >= this.maxRetries) return;
    this.retries++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect();
    }, this.reconnectMs * Math.min(this.retries, 5));
  }
}
