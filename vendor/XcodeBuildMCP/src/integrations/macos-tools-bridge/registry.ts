import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { BridgeBackend, type BridgeBackendConfig, type BridgeBackendStatus } from './backend.ts';
import { log } from '../../utils/logger.ts';

export interface RegistryStatus {
  backends: BridgeBackendStatus[];
  totalToolsRegistered: number;
  healthyBackends: number;
}

/**
 * Manages multiple BridgeBackend instances and routes tool calls
 * to the correct backend based on tool-to-backend mapping.
 */
export class BackendRegistry {
  private backends = new Map<string, BridgeBackend>();
  private toolToBackend = new Map<string, string>();

  /**
   * Register and connect a new backend.
   * Returns true if connected successfully, false if it failed (graceful degradation).
   */
  async addBackend(config: BridgeBackendConfig): Promise<boolean> {
    if (this.backends.has(config.id)) {
      log('warning', `[bridge-registry] Backend "${config.id}" already registered, skipping`);
      return this.backends.get(config.id)?.isConnected ?? false;
    }

    const backend = new BridgeBackend(config, () => {
      log('warning', `[bridge-registry] Backend "${config.id}" disconnected`);
    });

    this.backends.set(config.id, backend);

    try {
      await backend.connect();
      const status = backend.getStatus();
      log(
        'info',
        `[bridge-registry] Backend "${config.id}" connected (PID: ${status.bridgePid}, ${status.toolCount} server tools)`,
      );
      return true;
    } catch (error) {
      log(
        'warning',
        `[bridge-registry] Backend "${config.id}" unavailable: ${error instanceof Error ? error.message : String(error)}`,
      );
      return false;
    }
  }

  /**
   * Get a backend by ID.
   */
  getBackend(id: string): BridgeBackend | undefined {
    return this.backends.get(id);
  }

  /**
   * Map a bridged tool name to a backend ID.
   * Called during tool registration to build the routing table.
   */
  mapToolToBackend(toolName: string, backendId: string): void {
    this.toolToBackend.set(toolName, backendId);
  }

  /**
   * Route a tool call to the correct backend.
   */
  async callTool(
    bridgedToolName: string,
    remoteToolName: string,
    args: Record<string, unknown>,
  ): Promise<CallToolResult> {
    const backendId = this.toolToBackend.get(bridgedToolName);
    if (!backendId) {
      throw new Error(`No backend registered for tool "${bridgedToolName}"`);
    }

    const backend = this.backends.get(backendId);
    if (!backend) {
      throw new Error(`Backend "${backendId}" not found for tool "${bridgedToolName}"`);
    }

    return backend.callTool(remoteToolName, args);
  }

  /**
   * Get overall registry status.
   */
  getStatus(): RegistryStatus {
    const statuses = [...this.backends.values()].map((b) => b.getStatus());
    return {
      backends: statuses,
      totalToolsRegistered: this.toolToBackend.size,
      healthyBackends: statuses.filter((s) => s.connected).length,
    };
  }

  /**
   * Health check all backends. Returns map of backend ID -> healthy.
   */
  async healthCheckAll(): Promise<Map<string, boolean>> {
    const results = new Map<string, boolean>();
    const checks = [...this.backends.entries()].map(async ([id, backend]) => {
      const healthy = await backend.healthCheck();
      results.set(id, healthy);
      if (!healthy) {
        log('warning', `[bridge-registry] Backend "${id}" health check failed`);
      }
    });
    await Promise.all(checks);
    return results;
  }

  /**
   * Shutdown all backends gracefully.
   */
  async shutdownAll(): Promise<void> {
    const shutdowns = [...this.backends.values()].map(async (backend) => {
      try {
        await backend.disconnect();
      } catch {
        // ignore shutdown errors
      }
    });
    await Promise.all(shutdowns);
    this.backends.clear();
    this.toolToBackend.clear();
  }
}
