/**
 * Provider-agnostic local LLM client. Scrivano is not tied to any one runtime:
 * it speaks Ollama's native API and the OpenAI-compatible API served by
 * LM Studio, Jan, llamafile, vLLM, LocalAI, and others — and auto-detects
 * whichever is running.
 */

export type ProviderKind = 'ollama' | 'openai-compatible';

export interface ProviderInfo {
  reachable: boolean;
  kind: ProviderKind;
  url: string;
  label: string;
  models: string[];
  error?: string;
}

export const CANDIDATE_ENDPOINTS: { url: string; kind: ProviderKind; label: string }[] = [
  { url: 'http://localhost:11434', kind: 'ollama', label: 'Ollama' },
  { url: 'http://localhost:1234/v1', kind: 'openai-compatible', label: 'LM Studio' },
  { url: 'http://localhost:1337/v1', kind: 'openai-compatible', label: 'Jan' },
  { url: 'http://localhost:8080/v1', kind: 'openai-compatible', label: 'llamafile' },
];

export function normalizeBaseUrl(url: string): string {
  return url.trim().replace(/\/+$/, '');
}

/** Heuristic: URLs ending in /v1 are OpenAI-compatible; Ollama's default port too. */
export function guessKind(url: string): ProviderKind {
  const u = normalizeBaseUrl(url);
  if (u.endsWith('/v1')) return 'openai-compatible';
  if (u.includes(':11434')) return 'ollama';
  return 'openai-compatible';
}

export function parseOllamaModels(data: unknown): string[] {
  const d = data as { models?: { name?: unknown }[] };
  if (!Array.isArray(d?.models)) return [];
  return d.models.map((m) => (typeof m.name === 'string' ? m.name : '')).filter((n) => n.length > 0);
}

export function parseOpenAiModels(data: unknown): string[] {
  const d = data as { data?: { id?: unknown }[] };
  if (!Array.isArray(d?.data)) return [];
  return d.data.map((m) => (typeof m.id === 'string' ? m.id : '')).filter((n) => n.length > 0);
}

async function probe(url: string, kind: ProviderKind, label: string): Promise<ProviderInfo | null> {
  const base = normalizeBaseUrl(url);
  const endpoint = kind === 'ollama' ? `${base}/api/tags` : `${base}/models`;
  try {
    const res = await fetch(endpoint, { signal: AbortSignal.timeout(2500) });
    if (!res.ok) return null;
    const data = await res.json();
    const models = kind === 'ollama' ? parseOllamaModels(data) : parseOpenAiModels(data);
    return { reachable: true, kind, url: base, label, models };
  } catch {
    return null;
  }
}

const OFFLINE_ERROR =
  'No local AI server found. Start Ollama, LM Studio, Jan, or any OpenAI-compatible server — or set its URL in Settings. If you opened Scrivano from a website (not localhost), the server must allow this origin (see README).';

/**
 * Find a local AI server. If customUrl is set, only that URL is probed (as both API
 * styles); otherwise the common local runtimes are probed in order.
 */
export async function detectProvider(customUrl: string): Promise<ProviderInfo> {
  const custom = normalizeBaseUrl(customUrl);
  if (custom.length > 0) {
    const guessed = guessKind(custom);
    const other: ProviderKind = guessed === 'ollama' ? 'openai-compatible' : 'ollama';
    const first = await probe(custom, guessed, 'Custom');
    if (first) return first;
    const second = await probe(custom, other, 'Custom');
    if (second) return second;
    return { reachable: false, kind: guessed, url: custom, label: 'Custom', models: [], error: OFFLINE_ERROR };
  }

  const probes = await Promise.all(CANDIDATE_ENDPOINTS.map((c) => probe(c.url, c.kind, c.label)));
  const found = probes.find((p) => p !== null);
  if (found) return found;
  return { reachable: false, kind: 'ollama', url: '', label: 'Local AI', models: [], error: OFFLINE_ERROR };
}

/** Non-streaming text generation against whichever provider was detected. */
export async function generate(provider: ProviderInfo, model: string, prompt: string): Promise<string> {
  if (provider.kind === 'ollama') {
    const res = await fetch(`${provider.url}/api/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, prompt, stream: false, options: { temperature: 0.2 } }),
    });
    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`${provider.label} error (HTTP ${res.status}): ${body.slice(0, 200)}`);
    }
    const data = (await res.json()) as { response?: string };
    return data.response ?? '';
  }

  const res = await fetch(`${provider.url}/chat/completions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages: [{ role: 'user', content: prompt }], temperature: 0.2, stream: false }),
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`${provider.label} error (HTTP ${res.status}): ${body.slice(0, 200)}`);
  }
  const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
  return data.choices?.[0]?.message?.content ?? '';
}
