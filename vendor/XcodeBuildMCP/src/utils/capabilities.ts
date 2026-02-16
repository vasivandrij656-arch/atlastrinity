import { execFile } from 'node:child_process';
import { existsSync } from 'node:fs';
import process from 'node:process';
import { promisify } from 'node:util';

const execFileAsync = promisify(execFile);

export interface XcodeCapabilities {
  installed: boolean;
  version: string | null;
  build: string | null;
  path: string | null;
  hasMcpBridge: boolean;
  hasSimulatorRuntime: boolean;
  hasPredictiveModel: boolean;
  sdks: string[];
}

export interface MacOSCapabilities {
  version: string | null;
  build: string | null;
  arch: string | null;
  hasAccessibilityPermission: boolean | null;
  hasScreenRecordingPermission: boolean | null;
}

export interface BridgeAvailability {
  macosUse: boolean;
  googlemaps: boolean;
}

export interface SystemCapabilities {
  xcode: XcodeCapabilities;
  macos: MacOSCapabilities;
  macosUseBridgeAvailable: boolean;
  bridgeBackends: BridgeAvailability;
}

async function runQuiet(command: string, args: string[], timeoutMs = 3000): Promise<string | null> {
  try {
    const res = await execFileAsync(command, args, { timeout: timeoutMs });
    return (res.stdout ?? '').toString().trim() || null;
  } catch {
    return null;
  }
}

export async function detectXcodeCapabilities(): Promise<XcodeCapabilities> {
  const [xcodeSelectPath, versionOutput, mcpBridgePath] = await Promise.all([
    runQuiet('xcode-select', ['-p']),
    runQuiet('xcodebuild', ['-version']),
    runQuiet('xcrun', ['--find', 'mcpbridge'], 2000),
  ]);

  const installed = xcodeSelectPath !== null;

  let version: string | null = null;
  let build: string | null = null;
  if (versionOutput) {
    const versionMatch = versionOutput.match(/Xcode\s+([\d.]+\s*(?:beta\s*\d*)?)/i);
    const buildMatch = versionOutput.match(/Build version\s+(\w+)/i);
    version = versionMatch?.[1]?.trim() ?? null;
    build = buildMatch?.[1] ?? null;
  }

  const hasSimulatorRuntime = installed ? existsSync('/Library/Developer/CoreSimulator') : false;

  // Xcode 26+ ships a Predictive Code Completion Model that gets downloaded
  // via Xcode > Settings > Components.  The model lands at a well-known path
  // under CoreSimulator or Xcode support directories.
  const predictiveModelPaths = [
    `${xcodeSelectPath ?? ''}/usr/lib/swift/PredictiveCodeCompletion`,
    '/Library/Developer/CommandLineTools/usr/lib/swift/PredictiveCodeCompletion',
  ];
  const hasPredictiveModel = predictiveModelPaths.some((p) => p && existsSync(p));

  const sdks = await detectInstalledSdks();

  return {
    installed,
    version,
    build,
    path: xcodeSelectPath,
    hasMcpBridge: mcpBridgePath !== null,
    hasSimulatorRuntime,
    hasPredictiveModel,
    sdks,
  };
}

async function detectInstalledSdks(): Promise<string[]> {
  const output = await runQuiet('xcodebuild', ['-showsdks', '-json']);
  if (!output) return [];
  try {
    const parsed: unknown = JSON.parse(output);
    if (Array.isArray(parsed)) {
      return parsed
        .filter(
          (sdk): sdk is { canonicalName: string } =>
            typeof sdk === 'object' && sdk !== null && 'canonicalName' in sdk,
        )
        .map((sdk) => sdk.canonicalName);
    }
  } catch {
    // Fall back to line-based parsing
    return output
      .split('\n')
      .map((line) => line.match(/-sdk\s+(\S+)/)?.[1])
      .filter((s): s is string => s !== undefined);
  }
  return [];
}

export async function detectMacOSCapabilities(): Promise<MacOSCapabilities> {
  const [swVers, arch] = await Promise.all([runQuiet('sw_vers', []), runQuiet('uname', ['-m'])]);

  let version: string | null = null;
  let build: string | null = null;
  if (swVers) {
    version = swVers.match(/ProductVersion:\s*(.+)/)?.[1]?.trim() ?? null;
    build = swVers.match(/BuildVersion:\s*(.+)/)?.[1]?.trim() ?? null;
  }

  // Check accessibility permission via System Events (heuristic)
  let hasAccessibilityPermission: boolean | null = null;
  try {
    const axCheck = await runQuiet(
      'osascript',
      ['-e', 'tell application "System Events" to return name of first process'],
      2000,
    );
    hasAccessibilityPermission = axCheck !== null;
  } catch {
    hasAccessibilityPermission = null;
  }

  return {
    version,
    build,
    arch,
    hasAccessibilityPermission,
    hasScreenRecordingPermission: null, // Cannot be reliably detected without prompting
  };
}

export async function detectSystemCapabilities(): Promise<SystemCapabilities> {
  const [xcode, macos] = await Promise.all([detectXcodeCapabilities(), detectMacOSCapabilities()]);

  // Detect availability of native Swift MCP backend binaries
  const macosUseBinaryPath =
    process.env['MACOS_USE_BINARY_PATH'] ??
    '../mcp-server-macos-use/.build/release/mcp-server-macos-use';
  const googlemapsBinaryPath =
    process.env['GOOGLEMAPS_BINARY_PATH'] ??
    '../mcp-server-googlemaps/.build/release/mcp-server-googlemaps';

  const bridgeBackends: BridgeAvailability = {
    macosUse: existsSync(macosUseBinaryPath),
    googlemaps: existsSync(googlemapsBinaryPath),
  };

  return {
    xcode,
    macos,
    macosUseBridgeAvailable: bridgeBackends.macosUse,
    bridgeBackends,
  };
}
