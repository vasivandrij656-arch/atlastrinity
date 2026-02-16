import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import {
  StdioClientTransport,
  type StdioServerParameters,
} from '@modelcontextprotocol/sdk/client/stdio.js';
import { CompatibilityCallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';
import type { CallToolResult, Tool } from '@modelcontextprotocol/sdk/types.js';
import process from 'node:process';

export interface BridgeBackendConfig {
  /** Unique identifier for this backend (e.g., 'macos-use', 'googlemaps') */
  id: string;
  /** Human-readable name */
  name: string;
  /** Server parameters for stdio transport */
  serverParams: StdioServerParameters;
  /** Connection timeout in ms (default: 15000) */
  connectTimeoutMs?: number;
  /** Tool listing timeout in ms (default: 15000) */
  listToolsTimeoutMs?: number;
  /** Tool call timeout in ms (default: 60000) */
  callToolTimeoutMs?: number;
}

export interface BridgeBackendStatus {
  id: string;
  name: string;
  connected: boolean;
  bridgePid: number | null;
  lastError: string | null;
  toolCount: number;
}

/**
 * Generic MCP bridge backend that connects to any Swift/native MCP server
 * via stdio transport. Supports auto-reconnect, health checks, and
 * graceful degradation.
 */
export class BridgeBackend {
  readonly config: BridgeBackendConfig;

  private transport: StdioClientTransport | null = null;
  private client: Client | null = null;
  private connectPromise: Promise<void> | null = null;
  private lastError: string | null = null;
  private discoveredTools: Tool[] = [];
  private onDisconnect?: () => void;

  constructor(config: BridgeBackendConfig, onDisconnect?: () => void) {
    this.config = config;
    this.onDisconnect = onDisconnect;
  }

  get id(): string {
    return this.config.id;
  }

  get isConnected(): boolean {
    return this.client !== null;
  }

  getStatus(): BridgeBackendStatus {
    return {
      id: this.config.id,
      name: this.config.name,
      connected: this.client !== null,
      bridgePid: this.transport?.pid ?? null,
      lastError: this.lastError,
      toolCount: this.discoveredTools.length,
    };
  }

  async connect(): Promise<void> {
    if (this.client) return;
    if (this.connectPromise) return this.connectPromise;

    this.connectPromise = (async (): Promise<void> => {
      try {
        const transport = new StdioClientTransport({
          ...this.config.serverParams,
          stderr: 'ignore', // Prevent buffer deadlock
        });
        transport.onclose = (): void => {
          this.client = null;
          this.transport = null;
          this.connectPromise = null;
          this.onDisconnect?.();
        };

        const client = new Client(
          { name: `atlastrinity-bridge-${this.config.id}`, version: '1.0.0' },
          { capabilities: { sampling: {} } },
        );

        const timeoutMs = this.config.connectTimeoutMs ?? 15_000;
        await client.connect(transport, { timeout: timeoutMs });

        this.transport = transport;
        this.client = client;
        this.lastError = null;

        // Discover tools on connect
        await this.refreshToolList();
      } catch (error) {
        this.lastError = error instanceof Error ? error.message : String(error);
        await this.disconnect();
        throw error;
      } finally {
        this.connectPromise = null;
      }
    })();

    return this.connectPromise;
  }

  async disconnect(): Promise<void> {
    const client = this.client;
    const transport = this.transport;
    this.client = null;
    this.transport = null;
    this.connectPromise = null;

    try {
      await client?.close();
    } finally {
      try {
        await transport?.close?.();
      } catch {
        // ignore
      }
    }
  }

  /**
   * Discover tools from the remote server. Called automatically on connect.
   */
  async refreshToolList(): Promise<Tool[]> {
    if (!this.client) {
      throw new Error(`Backend "${this.config.id}" is not connected`);
    }
    const timeoutMs = this.config.listToolsTimeoutMs ?? 15_000;
    const result = await this.client.listTools(undefined, { timeout: timeoutMs });
    this.discoveredTools = result.tools;
    return this.discoveredTools;
  }

  /**
   * Get the list of tools discovered from this backend.
   */
  getDiscoveredTools(): Tool[] {
    return this.discoveredTools;
  }

  /**
   * Call a tool on this backend with auto-reconnect on failure.
   */
  async callTool(name: string, args: Record<string, unknown>): Promise<CallToolResult> {
    if (!this.client) {
      try {
        await this.connect();
      } catch {
        throw new Error(`Backend "${this.config.id}" not connected and reconnection failed`);
      }
    }

    try {
      return await this.executeToolCall(name, args);
    } catch (error) {
      // Retry once on transport errors
      if (isTransportError(error)) {
        await this.disconnect();
        try {
          await this.connect();
          return await this.executeToolCall(name, args);
        } catch {
          throw new Error(
            `Backend "${this.config.id}" tool "${name}" failed after retry: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
      }
      throw error;
    }
  }

  private async executeToolCall(
    name: string,
    args: Record<string, unknown>,
  ): Promise<CallToolResult> {
    if (!this.client) {
      throw new Error(`Backend "${this.config.id}" is not connected`);
    }

    const timeoutMs = this.config.callToolTimeoutMs ?? 60_000;
    const result: unknown = await this.client.request(
      { method: 'tools/call', params: { name, arguments: args } },
      CompatibilityCallToolResultSchema,
      { timeout: timeoutMs },
    );

    if (isCallToolResult(result)) {
      return result;
    }
    if (result && typeof result === 'object' && 'toolResult' in result) {
      const toolResult = (result as { toolResult: unknown }).toolResult;
      if (isCallToolResult(toolResult)) {
        return toolResult;
      }
    }

    if (result && typeof result === 'object' && 'task' in result) {
      throw new Error(
        `Tool "${name}" returned a task result; task-based tools are not supported by the bridge`,
      );
    }

    throw new Error(`Tool "${name}" returned an unexpected result shape`);
  }

  /**
   * Health check: ping the backend by listing tools.
   * Returns true if healthy, false otherwise.
   */
  async healthCheck(): Promise<boolean> {
    try {
      if (!this.client) return false;
      await this.refreshToolList();
      return true;
    } catch {
      return false;
    }
  }
}

function isCallToolResult(result: unknown): result is CallToolResult {
  if (!result || typeof result !== 'object') return false;
  const record = result as Record<string, unknown>;
  return Array.isArray(record.content);
}

function isTransportError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const msg = error.message.toLowerCase();
  return (
    msg.includes('transport') ||
    msg.includes('connection') ||
    msg.includes('closed') ||
    msg.includes('eof') ||
    msg.includes('epipe') ||
    msg.includes('econnreset')
  );
}

/**
 * Helper to build a BridgeBackendConfig for a local Swift binary.
 */
export function createSwiftBackendConfig(
  id: string,
  name: string,
  binaryPath: string,
  envOverrides?: Record<string, string>,
): BridgeBackendConfig {
  return {
    id,
    name,
    serverParams: {
      command: binaryPath,
      args: [],
      env: { ...process.env, ...envOverrides } satisfies Record<
        string,
        string | undefined
      > as Record<string, string>,
    },
  };
}
