const EMOJI_PATTERN = /[\u{1F600}-\u{1FAFF}\u{2600}-\u{27BF}]/gu;
const EMOJI_JOINER_PATTERN = /[\u{FE0E}\u{FE0F}\u{200D}]/gu;

export const ASR_TERM_CORRECTIONS = Object.freeze({
  '途国科技': '途鸽科技',
  '途哥科技': '途鸽科技',
  '福利业': '傅利叶',
  '人系机器人': '人形机器人',
  '人性机器人': '人形机器人',
  '机成': '机器人',
});

export function cleanTranscriptText(value) {
  let text = String(value || '')
    .replace(EMOJI_PATTERN, '')
    .replace(EMOJI_JOINER_PATTERN, '');

  for (const [source, target] of Object.entries(ASR_TERM_CORRECTIONS)) {
    text = text.replaceAll(source, target);
  }

  return text
    .replace(/(^|[。！？!?]\s*)(?:O\.|Yeah[。.!]?)(?=\s|$|[\u3400-\u9FFF])/gi, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/([。！？])\s+(?=[\u3400-\u9FFF])/g, '$1')
    .trim();
}

export function formatMeetingDuration(value) {
  const total = Math.max(0, Math.round(Number(value || 0)));
  if (!total) return '-';
  return `${Math.floor(total / 60)}分${total % 60}秒`;
}

export function formatMeetingDate(value, includeTime = true) {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  const datePart = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, '0'),
    String(date.getDate()).padStart(2, '0'),
  ].join('-');
  if (!includeTime) return datePart;
  return `${datePart} ${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
}

function formatTranscriptTime(value) {
  const total = Math.max(0, Math.floor(Number(value || 0)));
  return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
}

export function formatTranscriptRange(start, end) {
  return `${formatTranscriptTime(start)} - ${formatTranscriptTime(end)}`;
}

export function resolveMeetingSpeaker(segment, index) {
  const explicitLabel = String(segment?.speaker_label || segment?.speaker || '').trim();
  const speakerId = String(segment?.speaker_id || '').trim();
  const rawLabel = explicitLabel || speakerId;

  if (rawLabel) {
    const machineMatch = rawLabel.match(/^speaker[_\s-]?(\d+)$/i);
    if (machineMatch) {
      const speakerIndex = Number(machineMatch[1]);
      return {
        label: `说话人${String.fromCharCode(65 + (speakerIndex % 26))}`,
        tone: speakerIndex % 2 === 0 ? 'primary' : 'secondary',
      };
    }
    return { label: rawLabel, tone: index % 2 === 0 ? 'primary' : 'secondary' };
  }

  const text = cleanTranscriptText(segment?.transcript_text || segment?.text || '');
  if (/(我们这边是|我们主要做|我先介绍|我们公司|我们这边公司)/.test(text)) {
    return { label: '我方', tone: 'primary' };
  }
  if (/(你们能(?:否)?提供|你们这边|我想了解|请问|能不能提供)/.test(text)) {
    return { label: '客户方', tone: 'secondary' };
  }
  return {
    label: index % 2 === 0 ? '说话人A' : '说话人B',
    tone: index % 2 === 0 ? 'primary' : 'secondary',
  };
}

export function splitHighlightedText(value, query) {
  const text = String(value || '');
  const keyword = String(query || '').trim();
  if (!keyword) return [{ text, match: false }];

  const chunks = [];
  const normalizedText = text.toLocaleLowerCase();
  const normalizedKeyword = keyword.toLocaleLowerCase();
  let cursor = 0;

  while (cursor < text.length) {
    const matchIndex = normalizedText.indexOf(normalizedKeyword, cursor);
    if (matchIndex < 0) {
      chunks.push({ text: text.slice(cursor), match: false });
      break;
    }
    if (matchIndex > cursor) {
      chunks.push({ text: text.slice(cursor, matchIndex), match: false });
    }
    chunks.push({ text: text.slice(matchIndex, matchIndex + keyword.length), match: true });
    cursor = matchIndex + keyword.length;
  }

  return chunks.length > 0 ? chunks : [{ text, match: false }];
}
