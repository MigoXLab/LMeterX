import { describe, expect, it } from 'vitest';

import { parseJsonlObjects } from './jsonl';

describe('parseJsonlObjects', () => {
  it('parses non-empty JSON object lines', () => {
    expect(parseJsonlObjects('{"id":"1"}\n\n {"id":"2"}')).toEqual([
      { id: '1' },
      { id: '2' },
    ]);
  });

  it.each(['', '  \n', '[]', 'null', '"text"', '{bad json}'])(
    'rejects invalid JSONL object data: %j',
    value => {
      expect(() => parseJsonlObjects(value)).toThrow();
    }
  );
});
