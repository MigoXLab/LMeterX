import { describe, expect, it } from 'vitest';

import {
  headersForSubmission,
  INHERITED_SECRET_PLACEHOLDER,
  prepareHeadersForEditor,
} from './requestHeaders';

describe('request header copy helpers', () => {
  it('shows inherited values as placeholders', () => {
    const rows = prepareHeadersForEditor(
      [
        {
          key: 'Authorization',
          value: null,
          configured: true,
          sensitive: true,
        },
      ],
      ['Authorization']
    );

    expect(rows[0]).toMatchObject({
      key: 'Content-Type',
      value: 'application/json',
      fixed: true,
    });
    expect(rows[1].value).toBe(INHERITED_SECRET_PLACEHOLDER);
  });

  it('omits unchanged inherited values but submits explicit replacements', () => {
    expect(
      headersForSubmission(
        [
          { key: 'Content-Type', value: 'application/json', fixed: true },
          { key: 'Authorization', value: INHERITED_SECRET_PLACEHOLDER },
        ],
        ['Authorization']
      )
    ).toEqual([
      { key: 'Content-Type', value: 'application/json', fixed: true },
    ]);

    expect(
      headersForSubmission(
        [{ key: 'Authorization', value: 'Bearer replacement' }],
        ['Authorization']
      )
    ).toEqual([
      { key: 'Authorization', value: 'Bearer replacement', fixed: undefined },
    ]);
  });
});
