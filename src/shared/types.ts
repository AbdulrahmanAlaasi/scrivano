export interface TranscriptSegment {
  start: number; // seconds
  end: number; // seconds
  text: string;
}

export interface ActionItem {
  text: string;
  owner: string | null;
  due: string | null;
  done: boolean;
}

export interface AiNotes {
  summary: string;
  keyPoints: string[];
  actionItems: ActionItem[];
  decisions: string[];
  model: string;
  generatedAt: string;
}

export type MeetingSource = 'microphone' | 'tab-audio' | 'upload' | 'pasted';

export interface Meeting {
  id: string;
  title: string;
  createdAt: string; // ISO
  durationSec: number;
  source: MeetingSource;
  segments: TranscriptSegment[];
  notes: AiNotes | null;
}

export interface Settings {
  /** Custom local AI server URL. Empty string = auto-detect Ollama / LM Studio / Jan / llamafile. */
  llmUrl: string;
  llmModel: string;
  whisperModel: string;
}

export const DEFAULT_SETTINGS: Settings = {
  llmUrl: '',
  llmModel: '',
  whisperModel: 'onnx-community/whisper-base',
};

/** Migrate settings stored by earlier versions that were Ollama-specific. */
export function migrateSettings(raw: Partial<Settings> & { ollamaUrl?: string; ollamaModel?: string }): Settings {
  const llmUrl =
    raw.llmUrl ??
    // The old default pointed explicitly at Ollama; treat it as "auto-detect" now.
    (raw.ollamaUrl && raw.ollamaUrl !== 'http://localhost:11434' ? raw.ollamaUrl : '');
  return {
    llmUrl,
    llmModel: raw.llmModel ?? raw.ollamaModel ?? '',
    whisperModel: raw.whisperModel ?? DEFAULT_SETTINGS.whisperModel,
  };
}
