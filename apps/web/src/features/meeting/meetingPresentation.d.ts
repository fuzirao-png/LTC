export interface MeetingSpeakerInput {
  speaker?: unknown;
  speaker_id?: unknown;
  speaker_label?: unknown;
  transcript_text?: unknown;
  text?: unknown;
}

export interface MeetingSpeakerPresentation {
  label: string;
  tone: 'primary' | 'secondary';
}

export interface HighlightChunk {
  text: string;
  match: boolean;
}

export const ASR_TERM_CORRECTIONS: Readonly<Record<string, string>>;
export function cleanTranscriptText(value: unknown): string;
export function formatMeetingDuration(value: unknown): string;
export function formatMeetingDate(value: unknown, includeTime?: boolean): string;
export function formatTranscriptRange(start: unknown, end: unknown): string;
export function resolveMeetingSpeaker(segment: MeetingSpeakerInput, index: number): MeetingSpeakerPresentation;
export function splitHighlightedText(value: unknown, query: unknown): HighlightChunk[];
