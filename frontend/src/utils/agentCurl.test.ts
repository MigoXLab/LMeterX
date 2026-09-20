import { describe, expect, it } from 'vitest';

import { detectAgentCurl } from './agentCurl';
import parseCurlCommand from './curl';

const detect = (curl: string) => detectAgentCurl(parseCurlCommand(curl), curl);

describe('detectAgentCurl', () => {
  it('detects A2A JSON-RPC streaming from method name', () => {
    const curl = `curl -X POST https://agent.example.com/a2a \\
      -H 'Content-Type: application/json' \\
      -H 'A2A-Version: 1.0' \\
      -d '{"jsonrpc":"2.0","method":"SendStreamingMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]}}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      targetUrl: 'https://agent.example.com/a2a',
      a2aBinding: 'jsonrpc',
      a2aMode: 'stream',
      protocolVersion: '1.0',
    });
  });

  it('maps returnImmediately=true to async_poll, not sync', () => {
    const curl = `curl https://agent.example.com/a2a -d '{"jsonrpc":"2.0","method":"message/send","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]},"configuration":{"returnImmediately":true}}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      a2aBinding: 'jsonrpc',
      a2aMode: 'async_poll',
    });
  });

  it('maps returnImmediately=false to sync', () => {
    const curl = `curl https://agent.example.com/a2a -d '{"jsonrpc":"2.0","method":"SendMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]},"configuration":{"returnImmediately":false}}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      a2aBinding: 'jsonrpc',
      a2aMode: 'sync',
    });
  });

  it('defaults REST /message:send to async_poll when returnImmediately is absent', () => {
    const curl = `curl https://agent.example.com/a2a/message:send -d '{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      targetUrl: 'https://agent.example.com/a2a',
      a2aBinding: 'http_json',
      a2aMode: 'async_poll',
    });
  });

  it('detects HTTP+JSON from REST route and strips it from the base URL', () => {
    const curl = `curl -X POST 'https://agent.example.com/a2a/message:stream?x=1' -d '{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      targetUrl: 'https://agent.example.com/a2a?x=1',
      a2aBinding: 'http_json',
      a2aMode: 'stream',
    });
  });

  it('does not let a JSON-RPC body override a REST route binding', () => {
    const curl = `curl https://agent.example.com/v1/message:send -d '{"jsonrpc":"2.0","method":"SendMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]}}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      targetUrl: 'https://agent.example.com/v1',
      a2aBinding: 'http_json',
    });
  });

  it('detects HTTP+JSON from a REST body without jsonrpc', () => {
    const curl = `curl https://agent.example.com/a2a -d '{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]},"configuration":{"returnImmediately":false}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'a2a',
      a2aBinding: 'http_json',
      a2aMode: 'sync',
    });
  });

  it('detects MCP tools/call instead of A2A JSON-RPC', () => {
    const curl = `curl https://mcp.example.com/mcp \\
      -H 'MCP-Protocol-Version: 2025-11-25' \\
      -d '{"jsonrpc":"2.0","method":"tools/call","params":{"name":"weather","arguments":{"city":"上海"}}}'`;
    expect(detect(curl)).toMatchObject({
      protocol: 'mcp',
      targetUrl: 'https://mcp.example.com/mcp',
      protocolVersion: '2025-11-25',
    });
    expect(detect(curl).a2aBinding).toBeUndefined();
  });

  it('detects gRPC from grpcurl and streaming method', () => {
    const cmd = `grpcurl -d '{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}]}}' agent.example.com:443 a2a.v1.A2AService/SendStreamingMessage`;
    expect(detect(cmd)).toMatchObject({
      protocol: 'a2a',
      targetUrl: 'agent.example.com:443',
      a2aBinding: 'grpc',
      a2aMode: 'stream',
    });
  });
});
