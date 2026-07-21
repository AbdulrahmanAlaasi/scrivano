import type { TranscriptSegment } from '../shared/types';

export interface TranscribeProgress {
  phase: 'loading-model' | 'transcribing';
  /** 0..1 where known, otherwise -1 (indeterminate) */
  progress: number;
  detail: string;
}

type ProgressCallback = (p: TranscribeProgress) => void;

// Quantized (q8) weights are ~4x smaller, but on some machines onnxruntime-web fails to
// create a session for the quantized decoder ("TransposeDQWeightsForMatMulNBits missing
// required scale" / "Can't create a session"). So we try q8 first and automatically fall
// back to full-precision fp32, remembering which dtype worked for next time.
const DTYPE_LADDER = ['q8', 'fp32'] as const;
type Dtype = (typeof DTYPE_LADDER)[number];

const DTYPE_CACHE_KEY = 'scrivano:whisper-dtype';

function preferredDtypes(): Dtype[] {
  const cached = localStorage.getItem(DTYPE_CACHE_KEY) as Dtype | null;
  if (cached && (DTYPE_LADDER as readonly string[]).includes(cached)) {
    return [cached, ...DTYPE_LADDER.filter((d) => d !== cached)];
  }
  return [...DTYPE_LADDER];
}

// The transformers.js pipeline is heavy, so it is imported lazily on first use and
// cached for the session.
let cachedPipeline: unknown = null;
let cachedKey: string | null = null;

async function createPipeline(modelId: string, dtype: Dtype, onProgress: ProgressCallback): Promise<unknown> {
  const { pipeline } = await import('@huggingface/transformers');
  const seen = new Map<string, number>();
  return pipeline('automatic-speech-recognition', modelId, {
    dtype,
    progress_callback: (info: { status?: string; file?: string; progress?: number }) => {
      if (info.status === 'progress' && info.file && typeof info.progress === 'number') {
        seen.set(info.file, info.progress);
        const values = [...seen.values()];
        const avg = values.reduce((a, b) => a + b, 0) / values.length / 100;
        onProgress({
          phase: 'loading-model',
          progress: avg,
          detail: `Downloading speech model${dtype === 'fp32' ? ' (full precision)' : ''}, ${Math.round(avg * 100)}%`,
        });
      }
    },
  });
}

async function getPipeline(modelId: string, onProgress: ProgressCallback): Promise<unknown> {
  const key = modelId;
  if (cachedPipeline && cachedKey === key) return cachedPipeline;

  let lastError: unknown = null;
  for (const dtype of preferredDtypes()) {
    try {
      const p = await createPipeline(modelId, dtype, onProgress);
      // ONNX sessions can be created lazily on the first inference call, so a broken
      // quantized model may load "successfully" and only blow up when transcription
      // starts. Run a tiny warmup inference here to force session creation while we
      // are still inside the fallback ladder.
      onProgress({ phase: 'loading-model', progress: -1, detail: 'Verifying speech model…' });
      await (p as (audio: Float32Array, options: Record<string, unknown>) => Promise<unknown>)(
        new Float32Array(16000),
        {}
      );
      localStorage.setItem(DTYPE_CACHE_KEY, dtype);
      cachedPipeline = p;
      cachedKey = key;
      return p;
    } catch (err) {
      lastError = err;
      onProgress({
        phase: 'loading-model',
        progress: -1,
        detail: 'Optimized model failed on this device, retrying with full precision…',
      });
    }
  }
  throw lastError instanceof Error ? lastError : new Error('Could not load the speech model on this device.');
}

/** Decode any browser-supported audio (webm/ogg/mp3/wav/m4a) into 16kHz mono PCM. */
export async function decodeAudio(blob: Blob): Promise<Float32Array> {
  const arrayBuffer = await blob.arrayBuffer();
  const probeCtx = new AudioContext();
  const decoded = await probeCtx.decodeAudioData(arrayBuffer);
  await probeCtx.close();

  const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * 16000), 16000);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination);
  source.start();
  const resampled = await offline.startRendering();
  return resampled.getChannelData(0).slice();
}

interface ChunkOutput {
  text: string;
  chunks?: { timestamp: [number, number | null]; text: string }[];
}

export async function transcribe(
  blob: Blob,
  modelId: string,
  onProgress: ProgressCallback
): Promise<TranscriptSegment[]> {
  onProgress({ phase: 'loading-model', progress: -1, detail: 'Preparing speech model…' });
  let transcriber = (await getPipeline(modelId, onProgress)) as (
    audio: Float32Array,
    options: Record<string, unknown>
  ) => Promise<ChunkOutput>;

  onProgress({ phase: 'transcribing', progress: -1, detail: 'Decoding audio…' });
  const audio = await decodeAudio(blob);
  const totalSec = audio.length / 16000;

  // Whisper handles 30s windows natively; chunk longer audio ourselves so we can
  // report progress and keep memory bounded.
  const CHUNK_SEC = 28;
  const chunkSamples = CHUNK_SEC * 16000;
  const segments: TranscriptSegment[] = [];
  const isEnglishOnly = modelId.endsWith('.en');

  for (let offset = 0; offset < audio.length; offset += chunkSamples) {
    const chunk = audio.subarray(offset, Math.min(offset + chunkSamples, audio.length));
    const baseTime = offset / 16000;
    onProgress({
      phase: 'transcribing',
      progress: Math.min(offset / audio.length, 0.99),
      detail: `Transcribing… ${Math.round(baseTime)}s / ${Math.round(totalSec)}s`,
    });

    const options: Record<string, unknown> = {
      return_timestamps: true,
      chunk_length_s: 30,
    };
    if (!isEnglishOnly) {
      options.language = 'english';
      options.task = 'transcribe';
    }

    let result: ChunkOutput;
    try {
      result = await transcriber(chunk as Float32Array, options);
    } catch (err) {
      // Last line of defense: a session error escaped the load-time ladder (e.g. a
      // stale cached pipeline from before a dtype switch). Rebuild at full precision
      // once, then retry this chunk.
      if (localStorage.getItem(DTYPE_CACHE_KEY) !== 'fp32') {
        cachedPipeline = null;
        cachedKey = null;
        localStorage.setItem(DTYPE_CACHE_KEY, 'fp32');
        onProgress({
          phase: 'loading-model',
          progress: -1,
          detail: 'Optimized model failed on this device, retrying with full precision…',
        });
        transcriber = (await getPipeline(modelId, onProgress)) as typeof transcriber;
        result = await transcriber(chunk as Float32Array, options);
      } else {
        throw err;
      }
    }

    if (result.chunks && result.chunks.length > 0) {
      for (const c of result.chunks) {
        const [s, e] = c.timestamp;
        segments.push({ start: baseTime + (s ?? 0), end: baseTime + (e ?? s ?? 0), text: c.text });
      }
    } else if (result.text.trim().length > 0) {
      segments.push({ start: baseTime, end: baseTime + chunk.length / 16000, text: result.text });
    }
  }

  onProgress({ phase: 'transcribing', progress: 1, detail: 'Done' });
  return segments;
}
