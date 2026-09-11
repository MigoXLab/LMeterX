export const INHERITED_SECRET_PLACEHOLDER = '••••••••';

export interface RequestHeaderRow {
  key: string;
  value: string | null;
  fixed?: boolean;
  configured?: boolean;
  sensitive?: boolean;
}

export const prepareHeadersForEditor = (
  headers: RequestHeaderRow[] | undefined,
  redactedKeys: string[] = []
): Array<RequestHeaderRow & { value: string }> => {
  const redacted = new Set(redactedKeys.map(key => key.toLowerCase()));
  const rows = (headers || []).map(header => {
    const inherited =
      header.configured &&
      (header.sensitive !== false || redacted.has(header.key.toLowerCase()));
    return {
      ...header,
      value: inherited
        ? INHERITED_SECRET_PLACEHOLDER
        : String(header.value ?? ''),
      fixed: header.key.toLowerCase() === 'content-type' || header.fixed,
    };
  });
  const contentType = rows.find(
    header => header.key.toLowerCase() === 'content-type'
  );
  if (contentType) {
    contentType.fixed = true;
  } else {
    rows.unshift({
      key: 'Content-Type',
      value: 'application/json',
      fixed: true,
    });
  }
  return rows;
};

export const headersForSubmission = (
  headers: RequestHeaderRow[] | undefined,
  redactedKeys: string[] = []
): Array<{ key: string; value: string; fixed?: boolean }> => {
  const redacted = new Set(redactedKeys.map(key => key.toLowerCase()));
  return (headers || []).flatMap(header => {
    const key = String(header.key || '').trim();
    const value = String(header.value ?? '').trim();
    if (!key) return [];
    if (
      redacted.has(key.toLowerCase()) &&
      (!value || value === INHERITED_SECRET_PLACEHOLDER)
    ) {
      return [];
    }
    return [{ key, value, fixed: header.fixed }];
  });
};
