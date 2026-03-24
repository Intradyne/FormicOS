import type { TreeNode, Colony } from './types.js';

/** Recursively find a node by id in the tree. */
export function findNode(nodes: TreeNode[], id: string): TreeNode | null {
  for (const n of nodes) {
    if (n.id === id) return n;
    if (n.children) {
      const found = findNode(n.children, id);
      if (found) return found;
    }
  }
  return null;
}

/** Flatten all colony nodes from the tree. */
export function allColonies(nodes: TreeNode[]): Colony[] {
  let out: Colony[] = [];
  for (const n of nodes) {
    if (n.type === 'colony') out.push(n as Colony);
    if (n.children) out = out.concat(allColonies(n.children));
  }
  return out;
}

/** Return the path from root to the node with the given id. */
export function breadcrumbs(nodes: TreeNode[], id: string, path: TreeNode[] = []): TreeNode[] | null {
  for (const n of nodes) {
    const cur = [...path, n];
    if (n.id === id) return cur;
    if (n.children) {
      const found = breadcrumbs(n.children, id, cur);
      if (found) return found;
    }
  }
  return null;
}

/** Format an ISO timestamp as a relative time string. */
export function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return 'just now';
  const sec = Math.floor(ms / 1000);
  if (sec < 60) return 'just now';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hours = Math.floor(min / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

/** Format a cost value with honest near-zero display. */
export function formatCost(value: number): string {
  if (value === 0) return '$0.00';
  if (value > 0 && value < 0.01) return '<$0.01';
  return `$${value.toFixed(2)}`;
}

/** Return the display name for a colony, falling back to its id. */
export function colonyName(colony: { displayName?: string; id: string }): string {
  return colony.displayName || colony.id;
}

/** Determine the provider from a model address string. */
export function providerOf(model: string | null | undefined): string {
  if (!model) return 'local';
  const prefixes = [
    'anthropic/', 'gemini/', 'openai/', 'deepseek/',
    'minimax/', 'ollama-cloud/', 'ollama/', 'mistral/', 'groq/',
  ];
  for (const p of prefixes) {
    if (model.startsWith(p)) return p.slice(0, -1);
  }
  return 'llama-cpp';
}

/** Format a VRAM MiB value as a human-readable string (GiB when >= 1024 MiB). */
export function formatVram(mib: number): string {
  if (mib >= 1024) return `${(mib / 1024).toFixed(1)} GiB`;
  return `${mib.toLocaleString()} MiB`;
}

/** Return the CSS variable name for a model's provider color. */
export function providerColor(model: string | null | undefined): string {
  const p = providerOf(model);
  const map: Record<string, string> = {
    anthropic: 'var(--provider-anthropic)',
    gemini: 'var(--provider-gemini)',
    openai: 'var(--v-success)',
    deepseek: 'var(--v-blue)',
    minimax: 'var(--v-purple)',
    mistral: 'var(--v-warn)',
    groq: 'var(--v-accent)',
    'llama-cpp': 'var(--provider-local)',
    ollama: 'var(--provider-local)',
    'ollama-cloud': 'var(--provider-local)',
    local: 'var(--v-fg-dim)',
  };
  return map[p] ?? 'var(--v-fg-dim)';
}
