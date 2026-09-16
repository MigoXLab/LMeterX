export const parseJsonlObjects = (value: string): Record<string, unknown>[] => {
  const lines = value.split(/\r?\n/).filter(line => line.trim());
  if (lines.length === 0) {
    throw new Error('JSONL data must contain at least one record');
  }

  return lines.map((line, index) => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      throw new Error(`Invalid JSONL at line ${index + 1}`);
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error(`JSONL line ${index + 1} must be an object`);
    }
    return parsed as Record<string, unknown>;
  });
};
