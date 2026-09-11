const LOG_TIMESTAMP_PATTERN =
  /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:[.,](\d{1,6}))?(?:Z|[+-]\d{2}:?\d{2})?$/;

const STRUCTURED_LOG_LINE_PATTERN =
  /^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?(?:Z|[+-]\d{2}:?\d{2})?)\s*\|\s*(INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\s*\|\s*(.*)$/i;

const LOCUST_LOG_LINE_PATTERN =
  /^\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:[.,]\d{1,6})?\]\s+(?:.+?)\/(?:INFO|ERROR|WARN|WARNING|DEBUG|CRITICAL|FATAL)\/(?:[^:]+):\s*(.*)$/i;

const ESCAPE_CHAR = String.fromCharCode(27);

const padMilliseconds = (fraction = '') => fraction.padEnd(3, '0').slice(0, 3);
const padMicroseconds = (fraction = '') => fraction.padEnd(6, '0').slice(0, 6);

const formatDate = (date: Date): string => {
  const pad = (value: number, width = 2) => String(value).padStart(width, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(
    date.getMilliseconds(),
    3
  )}`;
};

const stripAnsiColorCodes = (value: string): string => {
  let stripped = '';
  let index = 0;

  while (index < value.length) {
    if (value[index] === ESCAPE_CHAR && value[index + 1] === '[') {
      let sequenceIndex = index + 2;

      while (
        sequenceIndex < value.length &&
        (value[sequenceIndex] === ';' ||
          (value[sequenceIndex] >= '0' && value[sequenceIndex] <= '9'))
      ) {
        sequenceIndex += 1;
      }

      if (value[sequenceIndex] === 'm') {
        index = sequenceIndex + 1;
      } else {
        stripped += value[index];
        index += 1;
      }
    } else {
      stripped += value[index];
      index += 1;
    }
  }

  return stripped;
};

export const normalizeLogTimestamp = (value: unknown): string => {
  if (typeof value === 'string') {
    const trimmed = value.trim();
    const match = trimmed.match(LOG_TIMESTAMP_PATTERN);
    if (match) {
      const [, date, time, fraction] = match;
      return `${date} ${time}.${padMilliseconds(fraction)}`;
    }
  }

  const date =
    typeof value === 'number'
      ? new Date(value * 1000)
      : typeof value === 'string'
        ? new Date(value)
        : null;

  return date && Number.isFinite(date.getTime()) ? formatDate(date) : '';
};

const normalizeLogSortTimestamp = (value: unknown): string => {
  if (typeof value === 'string') {
    const match = value.trim().match(LOG_TIMESTAMP_PATTERN);
    if (match) {
      const [, date, time, fraction] = match;
      return `${date} ${time}.${padMicroseconds(fraction)}`;
    }
  }

  const displayedTimestamp = normalizeLogTimestamp(value);
  return displayedTimestamp ? `${displayedTimestamp}000` : '';
};

export const stripNestedLogPrefix = (value: string): string => {
  let message = stripAnsiColorCodes(value).trimStart();

  for (let index = 0; index < 3; index += 1) {
    const structuredMessage = message.match(STRUCTURED_LOG_LINE_PATTERN);
    if (structuredMessage) {
      message = structuredMessage[3].trimStart();
    } else {
      const locustMessage = message.match(LOCUST_LOG_LINE_PATTERN);
      if (locustMessage) {
        message = locustMessage[1].trimStart();
      } else {
        break;
      }
    }
  }

  return message;
};

export const buildSlsLogLine = (
  entry: any,
  decodeMessage: (value: string) => string
) => {
  const rawMessage = entry.message || entry.raw?.message || '';
  const message = stripNestedLogPrefix(decodeMessage(String(rawMessage)));
  const timestamp = normalizeLogSortTimestamp(
    entry.raw?.time || entry.timestamp || Date.now() / 1000
  );
  const level = String(entry.level || entry.raw?.level || 'INFO').toUpperCase();
  const prefix = `${timestamp} | ${level.padEnd(8)} | `;

  // A Locust table is one logical logging record containing multiple lines.
  // Prefix every physical line so later polling can split, merge and sort the
  // rendered content without treating continuation rows as timestamp zero.
  return message
    .split(/\r?\n/)
    .map(line => (line ? `${prefix}${line}` : ''))
    .join('\n');
};
