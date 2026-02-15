
import type { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import process from 'node:process';
import { createSwiftBackendConfig } from './backend.ts';
import { BackendRegistry, type RegistryStatus } from './registry.ts';
import {
  ALL_BRIDGED_TOOLS,
  type BridgedToolDefinition,
  type ToolCategoryValue,
  getToolsByCategories,
  getToolsByPriority,
  searchToolsByTags,
  getCatalogStats,
} from './catalog.ts';
import { log } from '../../utils/logger.ts';

// Re-export for external use
export { ToolCategory, type ToolCategoryValue, type BridgedToolDefinition } from './catalog.ts';
export type { RegistryStatus } from './registry.ts';
export type { BridgeBackendStatus } from './backend.ts';

// ─── Backend Binary Paths ───────────────────────────────────────────────────

const MACOS_USE_BINARY =
  process.env['MACOS_USE_BINARY_PATH'] ??
  '../mcp-server-macos-use/.build/release/mcp-server-macos-use';

const GOOGLEMAPS_BINARY =
  process.env['GOOGLEMAPS_BINARY_PATH'] ??
  '../mcp-server-googlemaps/.build/release/mcp-server-googlemaps';

// ─── Singleton Registry ─────────────────────────────────────────────────────

let registry: BackendRegistry | null = null;
let registeredToolCount = 0;

function getRegistry(): BackendRegistry {
  registry ??= new BackendRegistry();
  return registry;
}

// ─── Configuration ──────────────────────────────────────────────────────────

export interface BridgeRegistrationOptions {
  /** Which categories of tools to register. If empty/undefined, registers all. */
  categories?: ToolCategoryValue[];
  /** Maximum priority level to register (1=critical only, 5=everything). Default: 5 */
  maxPriority?: number;
  /** Semantic tag query to filter tools. Experimental. */
  tagQuery?: string[];
  /** Specific backend IDs to enable. If empty/undefined, tries all. */
  enabledBackends?: string[];
}

// ─── Main Registration ──────────────────────────────────────────────────────

/**
 * Register bridged tools from all available native MCP backends.
 *
 * Supports three filtering modes (composable):
 *   1. Category filter:  only register tools from specific categories
 *   2. Priority filter:  only register tools up to a priority threshold
 *   3. Tag search:       experimental semantic matching by tags
 *
 * Backends that fail to connect are skipped gracefully.
 */
export async function registerBridgedTools(
  server: McpServer,
  options: BridgeRegistrationOptions = {},
): Promise<void> {
  const reg = getRegistry();

  // --- Connect backends ---
  const backends = [
    createSwiftBackendConfig('macos-use', 'macOS-use Automation', MACOS_USE_BINARY),
    createSwiftBackendConfig('googlemaps', 'Google Maps', GOOGLEMAPS_BINARY, {
      GOOGLE_MAPS_API_KEY: process.env['GOOGLE_MAPS_API_KEY'] ?? '',
    }),
  ];

  const enabledSet = options.enabledBackends
    ? new Set(options.enabledBackends)
    : null;

  const connectResults = await Promise.all(
    backends
      .filter((b) => !enabledSet || enabledSet.has(b.id))
      .map(async (config) => {
        log('info', `[bridge] Attempting to connect to backend: ${config.id} (${config.serverParams.command})`);
        try {
          const ok = await reg.addBackend(config);
          log('info', `[bridge] Backend ${config.id}: ${ok ? 'CONNECTED' : 'FAILED'}`);
          return { id: config.id, connected: ok };
        } catch (error) {
          log('error', `[bridge] Backend ${config.id} failed with error: ${error instanceof Error ? error.message : String(error)}`);
          return { id: config.id, connected: false };
        }
      }),
  );

  const connectedIds = new Set(
    connectResults.filter((r) => r.connected).map((r) => r.id),
  );

  if (connectedIds.size === 0) {
    log('warning', '[bridge] No backends available, skipping tool registration');
    return;
  }

  // --- Filter tools ---
  let tools: BridgedToolDefinition[] = ALL_BRIDGED_TOOLS;
  log('info', `[bridge] Total tools in catalog: ${tools.length}`);

  // Filter by connected backends
  tools = tools.filter((t) => connectedIds.has(t.backendId));
  log('info', `[bridge] Tools after backend filter: ${tools.length} (backends: ${Array.from(connectedIds).join(', ')})`);

  // Category filter
  if (options.categories && options.categories.length > 0) {
    const categoryTools = getToolsByCategories(options.categories);
    const categoryNames = new Set(categoryTools.map((t) => t.name));
    tools = tools.filter((t) => categoryNames.has(t.name));
  }

  // Priority filter
  if (options.maxPriority !== undefined) {
    const priorityTools = getToolsByPriority(options.maxPriority);
    const priorityNames = new Set(priorityTools.map((t) => t.name));
    tools = tools.filter((t) => priorityNames.has(t.name));
  }

  // Tag search (experimental)
  if (options.tagQuery && options.tagQuery.length > 0) {
    const tagTools = searchToolsByTags(options.tagQuery);
    const tagNames = new Set(tagTools.map((t) => t.name));
    tools = tools.filter((t) => tagNames.has(t.name));
  }

  // --- Register tools on the MCP server ---
  for (const toolDef of tools) {
    reg.mapToolToBackend(toolDef.name, toolDef.backendId);

    server.tool(
      toolDef.name,
      toolDef.description,
      toolDef.schema.shape,
      async (args: Record<string, unknown>) => {
        try {
          const result = await reg.callTool(toolDef.name, toolDef.remoteToolName, args);
          return {
            content: result.content,
            isError: result.isError,
          };
        } catch (error) {
          return {
            content: [
              {
                type: 'text' as const,
                text: `Error calling ${toolDef.name} (-> ${toolDef.remoteToolName}): ${error instanceof Error ? error.message : String(error)}`,
              },
            ],
            isError: true,
          };
        }
      },
    );
  }

  registeredToolCount = tools.length;

  // --- Log summary ---
  const stats = getCatalogStats();
  const backendSummary = connectResults
    .map((r) => `${r.id}:${r.connected ? 'ok' : 'unavailable'}`)
    .join(', ');

  log(
    'info',
    `[bridge] Registered ${tools.length}/${stats.total} bridged tools (backends: ${backendSummary})`,
  );
}

/**
 * Backward-compatible entry point. Registers all macOS-use tools.
 */
export async function registerMacOSTools(server: McpServer): Promise<void> {
  return registerBridgedTools(server, {
    enabledBackends: ['macos-use'],
  });
}

// ─── Status & Diagnostics ───────────────────────────────────────────────────

/**
 * Get full bridge status including all backends and routing info.
 */
export function getBridgeStatus(): RegistryStatus & { registeredToolCount: number } {
  const reg = getRegistry();
  return {
    ...reg.getStatus(),
    registeredToolCount,
  };
}

/**
 * Health check all backends.
 */
export async function healthCheckBridge(): Promise<Map<string, boolean>> {
  const reg = getRegistry();
  return reg.healthCheckAll();
}

// ─── Shutdown ───────────────────────────────────────────────────────────────

export async function shutdownBridge(): Promise<void> {
  if (registry) {
    await registry.shutdownAll();
    registry = null;
    registeredToolCount = 0;
  }
}

/**
 * Backward-compatible shutdown.
 */
export async function shutdownMacOSToolsBridge(): Promise<void> {
  return shutdownBridge();
}
