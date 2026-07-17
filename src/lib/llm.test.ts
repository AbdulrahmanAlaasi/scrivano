import { describe, expect, it } from 'vitest';
import { guessKind, normalizeBaseUrl, parseOllamaModels, parseOpenAiModels } from './llm';
import { migrateSettings } from '../shared/types';

describe('normalizeBaseUrl', () => {
  it('trims whitespace and trailing slashes', () => {
    expect(normalizeBaseUrl(' http://localhost:11434/ ')).toBe('http://localhost:11434');
    expect(normalizeBaseUrl('http://localhost:1234/v1//')).toBe('http://localhost:1234/v1');
  });
});

describe('guessKind', () => {
  it('treats /v1 URLs as OpenAI-compatible', () => {
    expect(guessKind('http://localhost:1234/v1')).toBe('openai-compatible');
  });

  it('treats port 11434 as Ollama', () => {
    expect(guessKind('http://localhost:11434')).toBe('ollama');
    expect(guessKind('http://192.168.1.5:11434/')).toBe('ollama');
  });

  it('defaults unknown URLs to OpenAI-compatible', () => {
    expect(guessKind('http://localhost:9999')).toBe('openai-compatible');
  });
});

describe('parseOllamaModels', () => {
  it('extracts model names from an /api/tags response', () => {
    expect(parseOllamaModels({ models: [{ name: 'llama3.2' }, { name: 'qwen2.5:7b' }] })).toEqual(['llama3.2', 'qwen2.5:7b']);
  });

  it('returns empty for malformed responses', () => {
    expect(parseOllamaModels({})).toEqual([]);
    expect(parseOllamaModels(null)).toEqual([]);
    expect(parseOllamaModels({ models: [{ notName: 1 }] })).toEqual([]);
  });
});

describe('parseOpenAiModels', () => {
  it('extracts model ids from a /v1/models response', () => {
    expect(parseOpenAiModels({ data: [{ id: 'mistral-7b-instruct' }, { id: 'phi-3' }] })).toEqual(['mistral-7b-instruct', 'phi-3']);
  });

  it('returns empty for malformed responses', () => {
    expect(parseOpenAiModels({})).toEqual([]);
    expect(parseOpenAiModels({ data: [{}] })).toEqual([]);
  });
});

describe('migrateSettings', () => {
  it('carries over a custom legacy Ollama URL', () => {
    const s = migrateSettings({ ollamaUrl: 'http://192.168.1.9:11434', ollamaModel: 'llama3.2' });
    expect(s.llmUrl).toBe('http://192.168.1.9:11434');
    expect(s.llmModel).toBe('llama3.2');
  });

  it('converts the old Ollama default URL into auto-detect', () => {
    const s = migrateSettings({ ollamaUrl: 'http://localhost:11434', ollamaModel: '' });
    expect(s.llmUrl).toBe('');
  });

  it('prefers new-style fields when both exist', () => {
    const s = migrateSettings({ llmUrl: 'http://localhost:1234/v1', llmModel: 'phi-3', ollamaUrl: 'x', ollamaModel: 'y' });
    expect(s.llmUrl).toBe('http://localhost:1234/v1');
    expect(s.llmModel).toBe('phi-3');
  });

  it('fills defaults for empty input', () => {
    const s = migrateSettings({});
    expect(s.llmUrl).toBe('');
    expect(s.whisperModel).toContain('whisper');
  });
});
