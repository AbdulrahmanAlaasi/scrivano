import { describe, expect, it } from 'vitest';

import {
  buildMeetingChatPrompt,
  msToClock,
  parseCitationMarkers,
  segmentsToPayload,
  type Excerpt,
} from './api';

const excerpts: Excerpt[] = [
  { segment_id: 'aaa', sequence: 0, speaker_label: 'Dana', start_ms: 0, end_ms: 4000, text: 'Budget is twenty thousand.' },
  { segment_id: 'bbb', sequence: 1, speaker_label: '', start_ms: 4000, end_ms: 9000, text: 'We ship in October.' },
];

describe('segmentsToPayload', () => {
  it('converts seconds to ms, renumbers, and drops empty segments', () => {
    const out = segmentsToPayload([
      { start: 0, end: 4.2, text: ' Hello there ' },
      { start: 4.2, end: 4.2, text: '   ' },
      { start: 4.2, end: 9.5, text: 'Second' },
    ]);
    expect(out).toHaveLength(2);
    expect(out[0]).toEqual({ sequence: 0, start_ms: 0, end_ms: 4200, text: 'Hello there' });
    expect(out[1].sequence).toBe(1);
    expect(out[1].start_ms).toBe(4200);
  });

  it('guarantees end_ms > start_ms even for zero-length segments', () => {
    const out = segmentsToPayload([{ start: 1, end: 1, text: 'x' }]);
    expect(out[0].end_ms).toBeGreaterThan(out[0].start_ms);
  });
});

describe('parseCitationMarkers', () => {
  it('maps [n] markers to excerpt citations, deduplicated', () => {
    const cites = parseCitationMarkers('Budget is 20k [1][1] and ships in October [2].', excerpts);
    expect(cites.map((c) => c.segment_id)).toEqual(['aaa', 'bbb']);
    expect(cites[0].quote).toContain('twenty thousand');
  });

  it('ignores out-of-range markers and returns empty for uncited answers', () => {
    expect(parseCitationMarkers('It is 20k [7].', excerpts)).toEqual([]);
    expect(parseCitationMarkers('It is 20k.', excerpts)).toEqual([]);
  });
});

describe('buildMeetingChatPrompt', () => {
  it('numbers excerpts with speaker and timestamps and demands NOT_FOUND honesty', () => {
    const prompt = buildMeetingChatPrompt('What is the budget?', excerpts);
    expect(prompt).toContain('[1] (Dana 00:00–00:04) Budget is twenty thousand.');
    expect(prompt).toContain('[2] (speaker 00:04–00:09)');
    expect(prompt).toContain('NOT_FOUND');
    expect(prompt).toContain('ONLY the transcript excerpts');
  });

  it('states plainly when no excerpts were found', () => {
    expect(buildMeetingChatPrompt('q', [])).toContain('no relevant excerpts');
  });
});

describe('msToClock', () => {
  it('formats mm:ss', () => {
    expect(msToClock(0)).toBe('00:00');
    expect(msToClock(65_000)).toBe('01:05');
    expect(msToClock(600_000)).toBe('10:00');
  });
});
