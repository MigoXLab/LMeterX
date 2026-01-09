/**
 * @file curl.ts
 * @description Curl command parsing helpers for reuse and testing
 */
import { parse as parseShellArgs } from 'shell-quote';

export interface ParsedCurlResult {
  method?: string;
  url?: string;
  headers?: { key: string; value: string }[];
  body?: string;
}

export const parseCurlCommand = (curl: string): ParsedCurlResult => {
  const result: ParsedCurlResult = {};
  const trimmed = curl?.trim();
  if (!trimmed) return result;

  const tokens = parseShellArgs(trimmed).filter(
    token => typeof token === 'string'
  ) as string[];

  if (!tokens.length) return result;

  const args = tokens[0].toLowerCase() === 'curl' ? tokens.slice(1) : tokens;

  const headers: { key: string; value: string }[] = [];
  let url: string | undefined;
  const dataParts: string[] = [];
  let method: string | undefined;

  // Flags whose next token is a value we should skip from URL detection
  const flagsWithValue = new Set([
    '-X',
    '--request',
    '-H',
    '--header',
    '--url',
    '-o',
    '--output',
    '-u',
    '--user',
    '-A',
    '--user-agent',
    '-e',
    '--referer',
    '-b',
    '--cookie',
    '-c',
    '--cookie-jar',
    '-F',
    '--form',
    '--form-string',
    '--compressed',
    '--config',
    '--proxy',
    '--resolve',
    '--connect-timeout',
  ]);

  const setUrlIfEmpty = (candidate: string) => {
    // Only accept obvious http/https URLs to avoid false positives
    if (!url && /^https?:\/\/[^\s'"`]+/i.test(candidate)) {
      url = candidate;
    }
  };

  const pushHeader = (headerStr: string) => {
    const separatorIndex = headerStr.indexOf(':');
    if (separatorIndex !== -1) {
      headers.push({
        key: headerStr.slice(0, separatorIndex).trim(),
        value: headerStr.slice(separatorIndex + 1).trim(),
      });
    }
  };

  const isDataFlag = (flag: string) =>
    [
      '-d',
      '--data',
      '--data-raw',
      '--data-binary',
      '--data-urlencode',
    ].includes(flag);

  for (let i = 0; i < args.length; i += 1) {
    const arg = args[i];
    const requestInline =
      arg.match(/^--request=(.+)$/i) || arg.match(/^-X(.+)$/i);
    const headerInline =
      arg.match(/^--header=(.+)$/i) || arg.match(/^-H(.+)$/i);
    const dataInline = arg.match(
      /^(-d|--data(?:-raw)?|--data-binary|--data-urlencode)=(.+)$/i
    );
    const urlInline = arg.match(/^--url=(.+)$/i);

    if (arg === '-X' || arg === '--request') {
      method = args[i + 1]?.toUpperCase();
      i += 1;
    } else if (requestInline) {
      method = requestInline[1].toUpperCase();
    } else if (arg === '-H' || arg === '--header') {
      const headerValue = args[i + 1];
      if (headerValue) pushHeader(headerValue);
      i += 1;
    } else if (headerInline) {
      pushHeader(headerInline[1]);
    } else if (isDataFlag(arg)) {
      const dataValue = args[i + 1];
      if (dataValue !== undefined) dataParts.push(dataValue);
      i += 1;
    } else if (dataInline) {
      dataParts.push(dataInline[2]);
    } else if (arg === '--url') {
      const candidate = args[i + 1];
      if (candidate) setUrlIfEmpty(candidate);
      i += 1;
    } else if (urlInline) {
      setUrlIfEmpty(urlInline[1]);
    } else if (/^https?:\/\//i.test(arg)) {
      setUrlIfEmpty(arg);
    } else if (flagsWithValue.has(arg)) {
      i += 1; // Skip its value safely
    } else if (!url && !arg.startsWith('-') && !arg.includes('=')) {
      setUrlIfEmpty(arg);
    }
  }

  if (headers.length) {
    result.headers = headers;
  }
  if (method) {
    result.method = method;
  }
  if (url) {
    result.url = url;
  }
  if (dataParts.length) {
    // Preserve multiple -d segments by joining with newlines to keep order
    result.body = dataParts.join('\n');
    if (!result.method) {
      result.method = 'POST';
    }
  }
  if (!result.method) {
    result.method = 'GET';
  }
  return result;
};

export default parseCurlCommand;
