/**
 * @file agentCurl.ts
 * @description Infer A2A/MCP protocol, binding and execution mode from a parsed curl.
 */
import type { ParsedCurlResult } from './curl';

export type AgentProtocolKind = 'a2a' | 'mcp';
export type A2aBindingKind = 'jsonrpc' | 'http_json' | 'grpc';
export type A2aModeKind = 'async_poll' | 'stream' | 'sync';

export interface AgentCurlDetection {
  protocol: AgentProtocolKind | 'unknown';
  targetUrl?: string;
  a2aBinding?: A2aBindingKind;
  a2aMode?: A2aModeKind;
  protocolVersion?: string;
}

const A2A_JSONRPC_METHODS = new Set([
  'sendmessage',
  'sendstreamingmessage',
  'gettask',
  'canceltask',
  'listtasks',
  'message/send',
  'message/stream',
  'tasks/get',
  'tasks/cancel',
  'tasks/list',
  'tasks/resubscribe',
  'agent/getauthenticatedextendedcard',
]);

const A2A_STREAM_METHODS = new Set([
  'sendstreamingmessage',
  'message/stream',
  'tasks/resubscribe',
]);

const MCP_METHOD_PREFIXES = [
  'initialize',
  'ping',
  'notifications/',
  'tools/',
  'resources/',
  'prompts/',
  'logging/',
  'completion/',
  'sampling/',
];

const REST_ROUTE_TO_MODE: Array<{
  pattern: RegExp;
  mode?: A2aModeKind;
  strip: RegExp;
}> = [
  {
    pattern: /\/message:stream\/?$/i,
    mode: 'stream',
    strip: /\/message:stream\/?$/i,
  },
  {
    pattern: /\/message:send\/?$/i,
    strip: /\/message:send\/?$/i,
  },
  {
    pattern: /\/tasks(\/[^/?#]*)?\/?$/i,
    mode: 'async_poll',
    strip: /\/tasks(\/[^/?#]*)?\/?$/i,
  },
];

const headerValue = (
  headers: ParsedCurlResult['headers'],
  name: string
): string | undefined =>
  headers?.find(item => item.key.toLowerCase() === name.toLowerCase())?.value;

const parseJsonBody = (body?: string): Record<string, unknown> | null => {
  if (!body) return null;
  try {
    const value = JSON.parse(body);
    return value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
};

const asRecord = (value: unknown): Record<string, unknown> | null =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;

const normalizeRpcMethod = (method: unknown): string =>
  String(method || '')
    .trim()
    .replace(/^\//, '')
    .toLowerCase();

const isMcpMethod = (method: string): boolean =>
  MCP_METHOD_PREFIXES.some(
    prefix => method === prefix.replace(/\/$/, '') || method.startsWith(prefix)
  );

const isA2aMethod = (method: string): boolean =>
  A2A_JSONRPC_METHODS.has(method);

const readReturnImmediately = (
  body: Record<string, unknown>
): boolean | undefined => {
  const fromConfig = (value: unknown): boolean | undefined => {
    const config = asRecord(value);
    if (!config || typeof config.returnImmediately !== 'boolean')
      return undefined;
    return config.returnImmediately;
  };
  const params = asRecord(body.params);
  return (
    fromConfig(body.configuration) ??
    fromConfig(params?.configuration) ??
    fromConfig(asRecord(params?.message)?.configuration)
  );
};

const pathnameOf = (rawUrl: string): { pathname: string } | null => {
  try {
    return { pathname: new URL(rawUrl).pathname };
  } catch {
    return null;
  }
};

const stripQueryAndHash = (
  rawUrl: string
): { base: string; suffix: string } => {
  const [withoutHash] = rawUrl.split('#');
  const [withoutQuery, query] = withoutHash.split('?');
  return {
    base: withoutQuery,
    suffix: query ? `?${query}` : '',
  };
};

const toGrpcTarget = (rawUrl: string): string => {
  if (/^https?:\/\//i.test(rawUrl) || /^grpcs?:\/\//i.test(rawUrl)) {
    try {
      const parsed = new URL(rawUrl);
      return parsed.port
        ? `${parsed.hostname}:${parsed.port}`
        : parsed.hostname;
    } catch {
      // fall through to host:port stripping
    }
  }
  return rawUrl.replace(/^(grpcs?|https?):\/\//i, '').split('/')[0];
};

const extractGrpcurlTarget = (rawCurl: string): string | undefined => {
  if (!/^\s*grpcurl\b/i.test(rawCurl)) return undefined;
  const match = rawCurl.match(
    /(?:^|\s)((?:localhost|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)(?::\d{2,5})|\[[0-9a-fA-F:]+\](?::\d{2,5})?|(?:grpcs?:\/\/)[^\s]+)/
  );
  if (!match) return undefined;
  return match[1].replace(/^grpcs?:\/\//i, '');
};

const looksLikeGrpc = (
  parsed: ParsedCurlResult,
  rawCurl: string,
  pathname: string
): boolean => {
  const contentType = (
    headerValue(parsed.headers, 'content-type') || ''
  ).toLowerCase();
  if (contentType.includes('application/grpc')) return true;
  if (/^\s*grpcurl\b/i.test(rawCurl)) return true;
  if (/a2aservice\//i.test(pathname) || /a2a\.v\d/i.test(pathname)) return true;
  return false;
};

const methodFromText = (value: string): string => {
  const grpc = value.match(
    /A2AService\/(SendStreamingMessage|SendMessage|GetTask|CancelTask)\b/i
  );
  if (grpc?.[1]) return normalizeRpcMethod(grpc[1]);
  const rpc = value.match(
    /\b(SendStreamingMessage|SendMessage|message\/stream|message\/send|tasks\/resubscribe|tasks\/get)\b/i
  );
  return rpc?.[1] ? normalizeRpcMethod(rpc[1]) : '';
};

export const detectAgentCurl = (
  parsed: ParsedCurlResult,
  rawCurl = ''
): AgentCurlDetection => {
  const result: AgentCurlDetection = { protocol: 'unknown' };
  const body = parseJsonBody(parsed.body);
  const method =
    normalizeRpcMethod(body?.method) ||
    methodFromText(parsed.url || '') ||
    methodFromText(rawCurl);
  const a2aVersion = headerValue(parsed.headers, 'a2a-version');
  const mcpVersion = headerValue(parsed.headers, 'mcp-protocol-version');
  const mcpSession = headerValue(parsed.headers, 'mcp-session-id');
  const mcpMethodHeader = headerValue(parsed.headers, 'mcp-method');
  const accept = (headerValue(parsed.headers, 'accept') || '').toLowerCase();
  const rawUrl = parsed.url || extractGrpcurlTarget(rawCurl) || '';
  const parts = rawUrl ? pathnameOf(rawUrl) : null;
  const pathname = parts?.pathname || rawUrl;

  const restRoute = REST_ROUTE_TO_MODE.find(item =>
    item.pattern.test(pathname)
  );
  const grpc = looksLikeGrpc(parsed, rawCurl, pathname);
  const a2aRpc = Boolean(
    body?.jsonrpc === '2.0' && method && isA2aMethod(method)
  );
  const mcpRpc = Boolean(
    (body?.jsonrpc === '2.0' && method && isMcpMethod(method)) ||
    mcpVersion ||
    mcpSession ||
    mcpMethodHeader
  );
  const httpJsonBody = Boolean(
    body && asRecord(body.message) && body.jsonrpc !== '2.0'
  );

  if (mcpRpc && !restRoute && !a2aRpc && !grpc) {
    result.protocol = 'mcp';
    result.targetUrl = rawUrl || undefined;
    result.protocolVersion = mcpVersion;
    return result;
  }

  if (restRoute || a2aRpc || httpJsonBody || grpc || a2aVersion) {
    result.protocol = 'a2a';
  }

  if (grpc) {
    result.a2aBinding = 'grpc';
    result.targetUrl = rawUrl ? toGrpcTarget(rawUrl) : undefined;
  } else if (restRoute) {
    result.a2aBinding = 'http_json';
    const { base, suffix } = stripQueryAndHash(rawUrl);
    result.targetUrl = `${base.replace(restRoute.strip, '')}${suffix}`;
    if (restRoute.mode) result.a2aMode = restRoute.mode;
  } else if (a2aRpc) {
    result.a2aBinding = 'jsonrpc';
    result.targetUrl = rawUrl || undefined;
  } else if (httpJsonBody) {
    result.a2aBinding = 'http_json';
    result.targetUrl = rawUrl || undefined;
  } else if (rawUrl) {
    result.targetUrl = rawUrl;
  }

  if (!result.a2aMode && A2A_STREAM_METHODS.has(method)) {
    result.a2aMode = 'stream';
  }
  if (
    !result.a2aMode &&
    result.protocol === 'a2a' &&
    accept.includes('text/event-stream') &&
    !accept.includes('application/json')
  ) {
    result.a2aMode = 'stream';
  }
  if (result.a2aMode !== 'stream' && body && result.protocol === 'a2a') {
    const returnImmediately = readReturnImmediately(body);
    if (returnImmediately === true) result.a2aMode = 'async_poll';
    if (returnImmediately === false) result.a2aMode = 'sync';
  }
  if (!result.a2aMode && restRoute && /\/message:send\/?$/i.test(pathname)) {
    result.a2aMode = 'async_poll';
  }

  if (result.protocol === 'a2a' && a2aVersion) {
    result.protocolVersion = a2aVersion;
  } else if (result.protocol === 'mcp' && mcpVersion) {
    result.protocolVersion = mcpVersion;
  }

  return result;
};

export default detectAgentCurl;
