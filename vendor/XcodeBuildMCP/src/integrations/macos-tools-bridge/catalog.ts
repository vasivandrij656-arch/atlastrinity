import { z } from 'zod';

// ─── Tool Categories ────────────────────────────────────────────────────────

/**
 * Categories for bridged tools. Used for:
 * 1. Static filtering: only register tools from enabled categories
 * 2. Dynamic filtering: adjust available tools based on context
 * 3. Priority hints: tell AI which tools are most relevant right now
 */
export const ToolCategory = {
  /** Core UI automation: click, type, scroll, drag */
  UI_AUTOMATION: 'ui-automation',
  /** Window and app management */
  APP_MANAGEMENT: 'app-management',
  /** Screenshots, OCR, visual testing */
  VISUAL_TESTING: 'visual-testing',
  /** System info: CPU, memory, battery, network */
  SYSTEM_INFO: 'system-info',
  /** System control: volume, brightness, dark mode */
  SYSTEM_CONTROL: 'system-control',
  /** File operations via Finder */
  FILE_OPS: 'file-ops',
  /** Clipboard operations */
  CLIPBOARD: 'clipboard',
  /** AppleScript execution */
  SCRIPTING: 'scripting',
  /** Notifications and alerts */
  NOTIFICATIONS: 'notifications',
  /** Calendar, reminders, productivity */
  PRODUCTIVITY: 'productivity',
  /** Apple Notes */
  NOTES: 'notes',
  /** Apple Mail */
  MAIL: 'mail',
  /** Maps and geolocation */
  MAPS: 'maps',
  /** Networking: fetch URLs, IP, WiFi */
  NETWORKING: 'networking',
  /** Time and timers */
  UTILITIES: 'utilities',
  /** Process management */
  PROCESS_MGMT: 'process-management',
  /** Permissions and onboarding */
  PERMISSIONS: 'permissions',
  /** Voice control and speech */
  VOICE_CONTROL: 'voice-control',
  /** Security: encryption, permissions */
  SECURITY: 'security',
  /** Meta-tools: help, diagnostics */
  META: 'meta',
  /** IDE integration: Windsurf, Xcode, etc. */
  IDE_INTEGRATION: 'ide-integration',
} as const;

export type ToolCategoryValue = (typeof ToolCategory)[keyof typeof ToolCategory];

// ─── Enhanced Tool Definition ───────────────────────────────────────────────

export interface BridgedToolDefinition {
  /** Name exposed to the AI agent */
  name: string;
  /** Human-readable description */
  description: string;
  /** Backend ID this tool belongs to (e.g., 'macos-use', 'googlemaps') */
  backendId: string;
  /** Actual tool name on the remote MCP server */
  remoteToolName: string;
  /** Zod schema for argument validation */
  schema: z.ZodObject<z.ZodRawShape>;
  /** Categories this tool belongs to */
  categories: ToolCategoryValue[];
  /** Priority hint (1=highest, 5=lowest). Used for dynamic filtering. */
  priority: number;
  /** Tags for experimental semantic search filtering */
  tags: string[];
}

// ─── Shared Schema Fragments ────────────────────────────────────────────────

const pidParam = z.number().optional().describe('Process ID of the target application');
const coordinateParams = {
  x: z.number().describe('X-coordinate for the action'),
  y: z.number().describe('Y-coordinate for the action'),
};
const regionParam = z
  .object({ x: z.number(), y: z.number(), width: z.number(), height: z.number() })
  .optional()
  .describe('Optional screen region to target');
const traversalOptions = {
  traverseBefore: z.boolean().optional().describe('Traverse accessibility tree before action'),
  traverseAfter: z.boolean().optional().describe('Traverse accessibility tree after action'),
  showDiff: z.boolean().optional().describe('Include diff between traversals'),
  onlyVisibleElements: z.boolean().optional().describe('Limit traversal to visible elements'),
  showAnimation: z.boolean().optional().describe('Show visual feedback animation'),
  animationDuration: z.number().optional().describe('Animation duration in seconds'),
  delayAfterAction: z.number().optional().describe('Delay in seconds after performing action'),
};

// ─── macOS-use Tools ────────────────────────────────────────────────────────

const MACOS_USE = 'macos-use';

const MACOS_USE_TOOLS: BridgedToolDefinition[] = [
  // --- UI Automation: Core Interactions ---
  {
    name: 'macos-use_click_and_traverse',
    description: 'Click at coordinates with accessibility traversal for reliable UI interaction',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_click_and_traverse',
    schema: z.object({ ...coordinateParams, pid: pidParam, ...traversalOptions }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 1,
    tags: ['click', 'tap', 'mouse', 'xcode', 'gui'],
  },
  {
    name: 'macos-use_right_click_and_traverse',
    description: 'Right-click (context menu) at coordinates with accessibility traversal',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_right_click_and_traverse',
    schema: z.object({ ...coordinateParams, pid: pidParam, ...traversalOptions }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 2,
    tags: ['right-click', 'context-menu', 'mouse', 'gui'],
  },
  {
    name: 'macos-use_double_click_and_traverse',
    description: 'Double-click at coordinates with accessibility traversal',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_double_click_and_traverse',
    schema: z.object({ ...coordinateParams, pid: pidParam, ...traversalOptions }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 2,
    tags: ['double-click', 'mouse', 'gui'],
  },
  {
    name: 'macos-use_type_and_traverse',
    description: 'Type text into application with accessibility traversal feedback',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_type_and_traverse',
    schema: z.object({
      text: z.string().describe('The text to type'),
      pid: pidParam,
      ...traversalOptions,
    }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 1,
    tags: ['type', 'keyboard', 'input', 'text', 'gui'],
  },
  {
    name: 'macos-use_press_key_and_traverse',
    description: 'Press keys with modifier support and accessibility traversal',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_press_key_and_traverse',
    schema: z.object({
      keyName: z.string().describe('Key name (e.g., "Return", "Escape", "Tab", "ArrowUp", "a")'),
      modifierFlags: z
        .array(z.string())
        .optional()
        .describe('Modifier keys: "Command", "Shift", "Control", "Option", "Function"'),
      pid: pidParam,
      ...traversalOptions,
    }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 1,
    tags: ['key', 'keyboard', 'shortcut', 'hotkey', 'gui'],
  },
  {
    name: 'macos-use_scroll_and_traverse',
    description: 'Scroll in a direction with accessibility traversal',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_scroll_and_traverse',
    schema: z.object({
      direction: z.enum(['up', 'down', 'left', 'right']).describe('Scroll direction'),
      amount: z.number().optional().describe('Scroll amount (default: 3)'),
      pid: pidParam,
      ...traversalOptions,
    }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 2,
    tags: ['scroll', 'mouse', 'gui'],
  },
  {
    name: 'macos-use_drag_and_drop_and_traverse',
    description: 'Drag and drop between two points with accessibility traversal',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_drag_and_drop_and_traverse',
    schema: z.object({
      startX: z.number().describe('Start X-coordinate'),
      startY: z.number().describe('Start Y-coordinate'),
      endX: z.number().describe('End X-coordinate'),
      endY: z.number().describe('End Y-coordinate'),
      pid: pidParam,
      duration: z.number().optional().describe('Drag duration in seconds'),
      ...traversalOptions,
    }),
    categories: [ToolCategory.UI_AUTOMATION],
    priority: 3,
    tags: ['drag', 'drop', 'mouse', 'gui'],
  },

  // --- App & Window Management ---
  {
    name: 'macos-use_open_application_and_traverse',
    description: 'Open or activate an application and traverse its accessibility tree',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_open_application_and_traverse',
    schema: z.object({
      identifier: z.string().describe('App name, bundle ID, or file path'),
      ...traversalOptions,
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 1,
    tags: ['open', 'app', 'launch', 'activate', 'xcode'],
  },
  {
    name: 'macos-use_refresh_traversal',
    description: 'Re-traverse an application accessibility tree without performing any action',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_refresh_traversal',
    schema: z.object({
      pid: z.number().describe('Process ID of the application to traverse'),
      ...traversalOptions,
    }),
    categories: [ToolCategory.APP_MANAGEMENT, ToolCategory.UI_AUTOMATION],
    priority: 2,
    tags: ['traverse', 'accessibility', 'refresh', 'inspect'],
  },
  {
    name: 'macos-use_list_running_apps',
    description: 'List all running applications with PIDs, bundle IDs, and window info',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_list_running_apps',
    schema: z.object({
      filter: z.string().optional().describe('Optional: Filter by application name or bundle identifier.'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 2,
    tags: ['apps', 'running', 'pid', 'list'],
  },
  {
    name: 'macos-use_list_all_windows',
    description: 'List all open windows across applications with titles and positions',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_list_all_windows',
    schema: z.object({}),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 2,
    tags: ['windows', 'list', 'titles'],
  },
  {
    name: 'macos-use_list_browser_tabs',
    description: 'List open browser tabs with titles and URLs',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_list_browser_tabs',
    schema: z.object({
      browser: z
        .string()
        .optional()
        .describe('Browser name (chrome, safari, firefox). Omit to check all.'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 3,
    tags: ['browser', 'tabs', 'chrome', 'safari'],
  },
  {
    name: 'macos-use_window_management',
    description: 'Window management: move, resize, minimize, maximize, snapshot, tile',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_window_management',
    schema: z.object({
      action: z
        .enum([
          'move',
          'resize',
          'minimize',
          'maximize',
          'close',
          'fullscreen',
          'snapshot',
          'restore',
          'tile',
          'list',
        ])
        .describe('Window action'),
      pid: pidParam,
      x: z.number().optional().describe('X position for move'),
      y: z.number().optional().describe('Y position for move'),
      width: z.number().optional().describe('Width for resize'),
      height: z.number().optional().describe('Height for resize'),
      snapshotName: z.string().optional().describe('Name for snapshot/restore'),
      tilePosition: z.string().optional().describe('Tile position: left, right, top, bottom'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 2,
    tags: ['window', 'move', 'resize', 'minimize', 'maximize', 'tile'],
  },
  {
    name: 'macos-use_get_frontmost_app',
    description: 'Get information about the currently active (frontmost) application',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_frontmost_app',
    schema: z.object({}),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 1,
    tags: ['frontmost', 'active', 'app', 'focus', 'xcode'],
  },
  {
    name: 'macos-use_get_active_window_info',
    description: 'Get detailed information about the frontmost window',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_active_window_info',
    schema: z.object({}),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 1,
    tags: ['window', 'active', 'info', 'title', 'xcode'],
  },
  {
    name: 'macos-use_close_window',
    description: 'Close a specific window by name or the frontmost window',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_close_window',
    schema: z.object({
      windowName: z
        .string()
        .optional()
        .describe('Title of the window to close. If omitted, closes front window.'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 3,
    tags: ['window', 'close', 'dismiss'],
  },
  {
    name: 'macos-use_move_window',
    description: 'Move a window to specified screen coordinates',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_move_window',
    schema: z.object({
      x: z.number().describe('New X coordinate'),
      y: z.number().describe('New Y coordinate'),
      windowName: z.string().optional().describe('Window title'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 3,
    tags: ['window', 'move', 'position'],
  },
  {
    name: 'macos-use_resize_window',
    description: 'Resize a window to specified dimensions',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_resize_window',
    schema: z.object({
      width: z.number().describe('New width'),
      height: z.number().describe('New height'),
      windowName: z.string().optional().describe('Window title'),
    }),
    categories: [ToolCategory.APP_MANAGEMENT],
    priority: 3,
    tags: ['window', 'resize', 'dimensions'],
  },

  // --- Visual Testing / Screenshots / OCR ---
  {
    name: 'macos-use_take_screenshot',
    description:
      'Take screenshots with region selection, multi-monitor support, compression, and OCR',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_take_screenshot',
    schema: z.object({
      path: z.string().optional().describe('Absolute path to save the screenshot'),
      region: regionParam,
      monitor: z.number().optional().describe('Monitor index (0 for main)'),
      quality: z
        .enum(['low', 'medium', 'high', 'lossless'])
        .optional()
        .describe('Compression quality'),
      format: z.enum(['png', 'jpg', 'webp']).optional().describe('Image format (default: png)'),
      ocr: z.boolean().optional().describe('Run OCR on screenshot and return text'),
    }),
    categories: [ToolCategory.VISUAL_TESTING],
    priority: 1,
    tags: ['screenshot', 'capture', 'screen', 'image', 'xcode'],
  },
  {
    name: 'macos-use_analyze_screen',
    description: 'Perform OCR (text recognition) on the screen or a specific region',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_analyze_screen',
    schema: z.object({
      region: regionParam,
      language: z
        .enum(['en', 'uk', 'ru', 'auto'])
        .optional()
        .describe('Language hint (default: auto)'),
      confidence: z.boolean().optional().describe('Include confidence scores'),
      format: z.enum(['json', 'text', 'both']).optional().describe('Output format (default: both)'),
    }),
    categories: [ToolCategory.VISUAL_TESTING],
    priority: 1,
    tags: ['ocr', 'text-recognition', 'screen', 'read', 'xcode'],
  },

  // --- System Monitoring ---
  {
    name: 'macos-use_system_monitoring',
    description: 'Real-time system monitoring: CPU, memory, disk, network, battery',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_system_monitoring',
    schema: z.object({
      metric: z
        .enum(['cpu', 'memory', 'disk', 'network', 'battery', 'all'])
        .describe('Metric to monitor'),
      duration: z.number().optional().describe('Duration in seconds'),
    }),
    categories: [ToolCategory.SYSTEM_INFO],
    priority: 2,
    tags: ['cpu', 'memory', 'disk', 'battery', 'monitor'],
  },
  {
    name: 'macos-use_system_control',
    description: 'System control: volume, brightness, dark mode, do-not-disturb',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_system_control',
    schema: z.object({
      action: z
        .enum(['volume', 'brightness', 'dark_mode', 'dnd', 'sleep', 'lock', 'info'])
        .describe('System action'),
      value: z.union([z.string(), z.number(), z.boolean()]).optional().describe('Action value'),
    }),
    categories: [ToolCategory.SYSTEM_CONTROL],
    priority: 3,
    tags: ['volume', 'brightness', 'dark-mode', 'system'],
  },
  {
    name: 'macos-use_process_management',
    description: 'Advanced process management with monitoring, control, and priority adjustment',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_process_management',
    schema: z.object({
      action: z
        .enum(['list', 'kill', 'restart', 'monitor', 'priority'])
        .describe('Action to perform'),
      pid: z.number().optional().describe('PID for kill/priority/restart actions'),
      name: z.string().optional().describe('Process name for specific actions'),
      priority: z.enum(['low', 'normal', 'high']).optional().describe('Priority level'),
      duration: z.number().optional().describe('Duration for monitoring in seconds'),
    }),
    categories: [ToolCategory.PROCESS_MGMT],
    priority: 2,
    tags: ['process', 'kill', 'monitor', 'priority', 'restart'],
  },
  {
    name: 'macos-use_get_battery_info',
    description: 'Get current battery status, percentage, and charging state',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_battery_info',
    schema: z.object({}),
    categories: [ToolCategory.SYSTEM_INFO],
    priority: 4,
    tags: ['battery', 'power', 'charging'],
  },
  {
    name: 'macos-use_get_wifi_details',
    description: 'Get current WiFi connection details (SSID, signal strength)',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_wifi_details',
    schema: z.object({}),
    categories: [ToolCategory.SYSTEM_INFO, ToolCategory.NETWORKING],
    priority: 4,
    tags: ['wifi', 'network', 'ssid', 'signal'],
  },
  {
    name: 'macos-use_set_system_volume',
    description: 'Set the system output volume (0-100)',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_set_system_volume',
    schema: z.object({ level: z.number().describe('Volume level from 0 to 100') }),
    categories: [ToolCategory.SYSTEM_CONTROL],
    priority: 4,
    tags: ['volume', 'sound', 'audio'],
  },
  {
    name: 'macos-use_set_screen_brightness',
    description: 'Set the primary display brightness (0.0 to 1.0)',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_set_screen_brightness',
    schema: z.object({ level: z.number().describe('Brightness level from 0.0 to 1.0') }),
    categories: [ToolCategory.SYSTEM_CONTROL],
    priority: 4,
    tags: ['brightness', 'display', 'screen'],
  },
  {
    name: 'macos-use_list_network_interfaces',
    description: 'List all active network interfaces on the system',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_list_network_interfaces',
    schema: z.object({}),
    categories: [ToolCategory.NETWORKING],
    priority: 4,
    tags: ['network', 'interfaces', 'ethernet', 'wifi'],
  },
  {
    name: 'macos-use_get_ip_address',
    description: 'Get local and estimated public IP address',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_ip_address',
    schema: z.object({}),
    categories: [ToolCategory.NETWORKING],
    priority: 4,
    tags: ['ip', 'address', 'network', 'public'],
  },

  // --- File & Finder Operations ---
  {
    name: 'macos-use_finder_list_files',
    description: 'List files via Finder with filtering, sorting, and metadata',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_finder_list_files',
    schema: z.object({
      path: z.string().optional().describe('Directory path (omit for frontmost Finder window)'),
      filter: z
        .string()
        .optional()
        .describe('Filter pattern (e.g., "*.txt", "name contains test")'),
      sort: z.enum(['name', 'date', 'size', 'type']).optional().describe('Sort order'),
      order: z.enum(['asc', 'desc']).optional().describe('Sort direction'),
      limit: z.number().optional().describe('Max number of results'),
      metadata: z.boolean().optional().describe('Include file metadata (size, dates, permissions)'),
    }),
    categories: [ToolCategory.FILE_OPS],
    priority: 2,
    tags: ['files', 'list', 'finder', 'directory'],
  },
  {
    name: 'macos-use_finder_open_path',
    description: 'Open a file or directory in Finder',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_finder_open_path',
    schema: z.object({ path: z.string().describe('POSIX path to open') }),
    categories: [ToolCategory.FILE_OPS],
    priority: 2,
    tags: ['open', 'finder', 'path', 'file'],
  },
  {
    name: 'macos-use_finder_get_selection',
    description: 'Get POSIX paths of currently selected items in Finder',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_finder_get_selection',
    schema: z.object({
      metadata: z.boolean().optional().describe('Include file metadata for selected items'),
    }),
    categories: [ToolCategory.FILE_OPS],
    priority: 3,
    tags: ['finder', 'selection', 'selected', 'files'],
  },
  {
    name: 'macos-use_finder_move_to_trash',
    description: 'Move a file or folder to the Trash via Finder',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_finder_move_to_trash',
    schema: z.object({ path: z.string().describe('POSIX path of the item to trash') }),
    categories: [ToolCategory.FILE_OPS],
    priority: 3,
    tags: ['trash', 'delete', 'remove', 'finder'],
  },
  {
    name: 'macos-use_empty_trash',
    description: 'Empty the macOS Trash via Finder',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_empty_trash',
    schema: z.object({}),
    categories: [ToolCategory.FILE_OPS],
    priority: 5,
    tags: ['trash', 'empty', 'cleanup'],
  },
  {
    name: 'macos-use_spotlight_search',
    description: 'Search for files using Spotlight (mdfind)',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_spotlight_search',
    schema: z.object({ query: z.string().describe('Filename search query') }),
    categories: [ToolCategory.FILE_OPS],
    priority: 2,
    tags: ['spotlight', 'search', 'find', 'files'],
  },

  // --- Clipboard ---
  {
    name: 'macos-use_set_clipboard',
    description: 'Set clipboard content with rich text, images, and history support',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_set_clipboard',
    schema: z.object({
      text: z.string().describe('Text to copy to clipboard'),
      html: z.string().optional().describe('HTML content'),
      image: z.string().optional().describe('Base64 image data'),
      addToHistory: z.boolean().optional().describe('Add to clipboard history (default: true)'),
      showAnimation: z.boolean().optional().describe('Show visual feedback (default: true)'),
    }),
    categories: [ToolCategory.CLIPBOARD],
    priority: 2,
    tags: ['clipboard', 'copy', 'paste', 'text'],
  },
  {
    name: 'macos-use_get_clipboard',
    description: 'Get clipboard content with rich text and image support',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_clipboard',
    schema: z.object({
      format: z.enum(['text', 'html', 'image', 'all']).optional().describe('Content format to get'),
      history: z.boolean().optional().describe('Get from history instead of current'),
    }),
    categories: [ToolCategory.CLIPBOARD],
    priority: 2,
    tags: ['clipboard', 'paste', 'get', 'text'],
  },
  {
    name: 'macos-use_clipboard_history',
    description: 'Manage clipboard history: clear, limit, and view',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_clipboard_history',
    schema: z.object({
      action: z.enum(['list', 'clear', 'limit']).optional().describe('History action'),
      limit: z.number().optional().describe('Max history items'),
    }),
    categories: [ToolCategory.CLIPBOARD],
    priority: 4,
    tags: ['clipboard', 'history', 'clear'],
  },

  // --- AppleScript ---
  {
    name: 'macos-use_run_applescript',
    description: 'Execute AppleScript with templates, AI generation, debugging, and validation',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_run_applescript',
    schema: z.object({
      script: z.string().describe('AppleScript source code to execute'),
      template: z
        .string()
        .optional()
        .describe('Use predefined template (automation, file_ops, system_info)'),
      aiGenerate: z
        .boolean()
        .optional()
        .describe('Generate AppleScript using AI based on description'),
      description: z
        .string()
        .optional()
        .describe('Describe what you want to accomplish for AI generation'),
      debug: z.boolean().optional().describe('Enable debug output'),
      validate: z.boolean().optional().describe('Validate syntax before execution'),
      timeout: z.number().optional().describe('Execution timeout in seconds'),
    }),
    categories: [ToolCategory.SCRIPTING],
    priority: 1,
    tags: ['applescript', 'script', 'automation', 'xcode'],
  },
  {
    name: 'macos-use_applescript_templates',
    description: 'Manage AppleScript templates: create, list, and use templates',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_applescript_templates',
    schema: z.object({
      list: z.boolean().optional().describe('List all available templates'),
      create: z.string().optional().describe('Create new template with name'),
      name: z.string().optional().describe('Template name (required for create)'),
      script: z.string().optional().describe('Template script content (required for create)'),
      description: z.string().optional().describe('Template description'),
    }),
    categories: [ToolCategory.SCRIPTING],
    priority: 3,
    tags: ['applescript', 'templates', 'automation'],
  },

  // --- Notifications ---
  {
    name: 'macos-use_send_notification',
    description: 'Send macOS notifications with scheduling, custom sounds, and templates',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_send_notification',
    schema: z.object({
      title: z.string().describe('Notification title'),
      message: z.string().describe('Notification body text'),
      schedule: z.string().optional().describe('Schedule in ISO format'),
      sound: z.string().optional().describe('Sound: "default", "none", or system sound name'),
      persistent: z.boolean().optional().describe('Keep until dismissed'),
      template: z.string().optional().describe('Use predefined template'),
    }),
    categories: [ToolCategory.NOTIFICATIONS],
    priority: 3,
    tags: ['notification', 'alert', 'sound'],
  },
  {
    name: 'macos-use_notification_schedule',
    description: 'Manage scheduled notifications: clear, list, and schedule',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_notification_schedule',
    schema: z.object({
      clear: z.boolean().optional().describe('Clear all scheduled notifications'),
      list: z.boolean().optional().describe('List scheduled notifications'),
    }),
    categories: [ToolCategory.NOTIFICATIONS],
    priority: 4,
    tags: ['notification', 'schedule', 'clear'],
  },

  // --- Calendar & Reminders ---
  {
    name: 'macos-use_calendar_events',
    description: 'Fetch calendar events for a date range',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_calendar_events',
    schema: z.object({
      start: z.string().describe('Start date in ISO format'),
      end: z.string().describe('End date in ISO format'),
    }),
    categories: [ToolCategory.PRODUCTIVITY],
    priority: 3,
    tags: ['calendar', 'events', 'schedule'],
  },
  {
    name: 'macos-use_create_event',
    description: 'Create a calendar event with attendees, recurring, location, and reminders',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_create_event',
    schema: z.object({
      title: z.string().describe('Event title'),
      date: z.string().describe('Event date in ISO format'),
      endDate: z.string().optional().describe('End date in ISO format'),
      duration: z.number().optional().describe('Duration in minutes'),
      location: z.string().optional().describe('Event location'),
      notes: z.string().optional().describe('Event notes'),
      attendees: z.array(z.string()).optional().describe('List of attendee emails'),
      recurring: z.enum(['daily', 'weekly', 'monthly']).optional().describe('Recurring pattern'),
      reminder: z.number().optional().describe('Reminder in minutes before event'),
    }),
    categories: [ToolCategory.PRODUCTIVITY],
    priority: 3,
    tags: ['calendar', 'event', 'create', 'meeting'],
  },
  {
    name: 'macos-use_reminders',
    description: 'Fetch incomplete reminders',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_reminders',
    schema: z.object({ list: z.string().optional().describe('Filter by list name') }),
    categories: [ToolCategory.PRODUCTIVITY],
    priority: 3,
    tags: ['reminders', 'tasks', 'todo'],
  },
  {
    name: 'macos-use_create_reminder',
    description: 'Create a new reminder',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_create_reminder',
    schema: z.object({ title: z.string().describe('Reminder title') }),
    categories: [ToolCategory.PRODUCTIVITY],
    priority: 3,
    tags: ['reminder', 'create', 'task'],
  },

  // --- Apple Notes ---
  {
    name: 'macos-use_notes_list_folders',
    description: 'List all folders in Apple Notes',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_notes_list_folders',
    schema: z.object({}),
    categories: [ToolCategory.NOTES],
    priority: 3,
    tags: ['notes', 'folders', 'list'],
  },
  {
    name: 'macos-use_notes_create_note',
    description: 'Create a new note in Apple Notes',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_notes_create_note',
    schema: z.object({
      body: z.string().describe('HTML or plain text content (first line becomes title)'),
      folder: z.string().optional().describe('Target folder name'),
    }),
    categories: [ToolCategory.NOTES],
    priority: 3,
    tags: ['notes', 'create', 'write'],
  },
  {
    name: 'macos-use_notes_get_content',
    description: 'Get the HTML content of a note by name',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_notes_get_content',
    schema: z.object({ name: z.string().describe('Name/title of the note') }),
    categories: [ToolCategory.NOTES],
    priority: 3,
    tags: ['notes', 'read', 'get', 'content'],
  },

  // --- Mail ---
  {
    name: 'macos-use_mail_send',
    description: 'Send email via Apple Mail with CC/BCC, HTML, attachments, and draft support',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_mail_send',
    schema: z.object({
      to: z.string().describe('Recipient email address'),
      subject: z.string().describe('Subject line'),
      body: z.string().describe('Email body content'),
      cc: z.string().optional().describe('CC recipient'),
      bcc: z.string().optional().describe('BCC recipient'),
      html: z.boolean().optional().describe('Send as HTML email'),
      attachments: z.array(z.string()).optional().describe('File paths to attach'),
      draft: z.boolean().optional().describe('Save as draft instead of sending'),
    }),
    categories: [ToolCategory.MAIL],
    priority: 3,
    tags: ['mail', 'email', 'send'],
  },
  {
    name: 'macos-use_mail_read_inbox',
    description: 'Read recent subject lines from Apple Mail Inbox',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_mail_read_inbox',
    schema: z.object({
      limit: z.number().optional().describe('Number of recent messages to read (default: 5)'),
    }),
    categories: [ToolCategory.MAIL],
    priority: 3,
    tags: ['mail', 'email', 'inbox', 'read'],
  },

  // --- Utilities ---
  {
    name: 'macos-use_fetch_url',
    description: 'Fetch URL content and convert HTML to text/markdown',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_fetch_url',
    schema: z.object({ url: z.string().describe('URL to fetch') }),
    categories: [ToolCategory.NETWORKING],
    priority: 2,
    tags: ['fetch', 'url', 'http', 'web'],
  },
  {
    name: 'macos-use_get_time',
    description: 'Get current time with timezone conversion and formatting',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_get_time',
    schema: z.object({
      timezone: z.string().optional().describe('Target timezone (e.g., "America/New_York")'),
      format: z.string().optional().describe('Format: "readable", "iso", "unix", "custom"'),
      customFormat: z.string().optional().describe('Custom date format string'),
      convertTo: z.string().optional().describe('Convert to timezone'),
    }),
    categories: [ToolCategory.UTILITIES],
    priority: 4,
    tags: ['time', 'clock', 'timezone'],
  },
  {
    name: 'macos-use_countdown_timer',
    description: 'Countdown timer with notification support',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_countdown_timer',
    schema: z.object({
      seconds: z.number().describe('Countdown duration in seconds'),
      message: z.string().optional().describe('Message on completion'),
      notification: z.boolean().optional().describe('Send notification on completion'),
    }),
    categories: [ToolCategory.UTILITIES],
    priority: 5,
    tags: ['timer', 'countdown', 'alarm'],
  },

  // --- Voice Control ---
  {
    name: 'macos-use_voice_control',
    description: 'Voice control system with speech recognition and command execution',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_voice_control',
    schema: z.object({
      command: z
        .string()
        .describe('Voice command to execute (e.g., "open Safari", "take screenshot")'),
      language: z
        .enum(['en-US', 'uk-UA', 'ru-RU', 'de-DE'])
        .optional()
        .describe('Language for voice recognition'),
      confidence: z.number().optional().describe('Minimum confidence threshold (0.0-1.0)'),
    }),
    categories: [ToolCategory.VOICE_CONTROL],
    priority: 4,
    tags: ['voice', 'speech', 'command', 'recognition'],
  },

  // --- Security ---
  {
    name: 'macos-use_file_encryption',
    description: 'File and folder encryption with AES algorithms and secure password management',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_file_encryption',
    schema: z.object({
      action: z
        .enum(['encrypt', 'decrypt', 'encrypt_folder', 'decrypt_folder'])
        .describe('Encryption action'),
      path: z.string().describe('File or folder path to encrypt/decrypt'),
      password: z.string().describe('Encryption password'),
      algorithm: z.enum(['AES256', 'AES128']).optional().describe('Encryption algorithm'),
      output: z.string().optional().describe('Output path for encrypted/decrypted file'),
    }),
    categories: [ToolCategory.SECURITY],
    priority: 4,
    tags: ['encrypt', 'decrypt', 'aes', 'security', 'password'],
  },

  // --- Permissions ---
  {
    name: 'macos-use_request_permissions',
    description:
      'Request all necessary macOS permissions (Accessibility, Calendar, Reminders, Notifications)',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_request_permissions',
    schema: z.object({}),
    categories: [ToolCategory.PERMISSIONS],
    priority: 1,
    tags: ['permissions', 'accessibility', 'setup', 'onboarding'],
  },

  // --- Terminal / Command Execution ---
  {
    name: 'execute_command',
    description: 'Execute a terminal command in a persistent shell session (maintains CWD)',
    backendId: MACOS_USE,
    remoteToolName: 'execute_command',
    schema: z.object({
      command: z.string().describe('The shell command to execute'),
    }),
    categories: [ToolCategory.SCRIPTING],
    priority: 1,
    tags: ['terminal', 'command', 'shell', 'execute', 'bash'],
  },
  {
    name: 'terminal',
    description: 'Alias for execute_command - run a terminal command in a persistent shell session',
    backendId: MACOS_USE,
    remoteToolName: 'terminal',
    schema: z.object({
      command: z.string().describe('The shell command to execute'),
    }),
    categories: [ToolCategory.SCRIPTING],
    priority: 2,
    tags: ['terminal', 'command', 'shell', 'alias'],
  },

  // --- Aliases: Screenshot & OCR ---
  {
    name: 'macos-screenshot',
    description:
      'Alias for macos-use_take_screenshot - take screenshots with region, multi-monitor, compression, and OCR',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_take_screenshot',
    schema: z.object({
      path: z.string().optional().describe('Absolute path to save the screenshot'),
      region: regionParam,
      monitor: z.number().optional().describe('Monitor index (0 for main)'),
      quality: z
        .enum(['low', 'medium', 'high', 'lossless'])
        .optional()
        .describe('Compression quality'),
      format: z.enum(['png', 'jpg', 'webp']).optional().describe('Image format (default: png)'),
      ocr: z.boolean().optional().describe('Run OCR on screenshot and return text'),
    }),
    categories: [ToolCategory.VISUAL_TESTING],
    priority: 2,
    tags: ['screenshot', 'capture', 'screen', 'alias'],
  },
  {
    name: 'ocr',
    description: 'Alias for macos-use_analyze_screen - perform OCR text recognition on the screen',
    backendId: MACOS_USE,
    remoteToolName: 'ocr',
    schema: z.object({
      region: regionParam,
      language: z
        .enum(['en', 'uk', 'ru', 'auto'])
        .optional()
        .describe('Language hint (default: auto)'),
      confidence: z.boolean().optional().describe('Include confidence scores'),
      format: z.enum(['json', 'text', 'both']).optional().describe('Output format (default: both)'),
    }),
    categories: [ToolCategory.VISUAL_TESTING],
    priority: 2,
    tags: ['ocr', 'text-recognition', 'screen', 'alias'],
  },
  {
    name: 'analyze',
    description: 'Alias for macos-use_analyze_screen - perform OCR text recognition on the screen',
    backendId: MACOS_USE,
    remoteToolName: 'analyze',
    schema: z.object({
      region: regionParam,
      language: z
        .enum(['en', 'uk', 'ru', 'auto'])
        .optional()
        .describe('Language hint (default: auto)'),
      confidence: z.boolean().optional().describe('Include confidence scores'),
      format: z.enum(['json', 'text', 'both']).optional().describe('Output format (default: both)'),
    }),
    categories: [ToolCategory.VISUAL_TESTING],
    priority: 3,
    tags: ['analyze', 'ocr', 'text-recognition', 'alias'],
  },

  // --- Meta Tools ---
  {
    name: 'macos-use_list_tools_dynamic',
    description:
      'Returns a detailed JSON structure describing all available tools, their schemas, and usage examples',
    backendId: MACOS_USE,
    remoteToolName: 'macos-use_list_tools_dynamic',
    schema: z.object({
      toolName: z.string().optional().describe('Filter by tool name'),
    }),
    categories: [ToolCategory.META],
    priority: 3,
    tags: ['tools', 'list', 'schema', 'help', 'meta', 'dynamic'],
  },
];

// ─── Google Maps Tools ──────────────────────────────────────────────────────

const GOOGLEMAPS = 'googlemaps';

const GOOGLEMAPS_TOOLS: BridgedToolDefinition[] = [
  {
    name: 'maps_geocode',
    description: 'Convert an address to geographic coordinates (latitude, longitude)',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_geocode',
    schema: z.object({
      address: z.string().describe('Address to geocode (e.g., "Kyiv, Ukraine")'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 2,
    tags: ['geocode', 'address', 'coordinates', 'location'],
  },
  {
    name: 'maps_reverse_geocode',
    description: 'Convert coordinates to a human-readable address',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_reverse_geocode',
    schema: z.object({
      lat: z.number().describe('Latitude'),
      lng: z.number().describe('Longitude'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['geocode', 'reverse', 'coordinates', 'address'],
  },
  {
    name: 'maps_search_places',
    description: 'Search for places, businesses, and points of interest',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_search_places',
    schema: z.object({
      query: z.string().describe('Search query (e.g., "restaurants near Maidan")'),
      location: z.string().optional().describe('Center point as "lat,lng"'),
      radius: z.number().optional().describe('Search radius in meters (default: 5000)'),
      type: z.string().optional().describe('Filter by type: restaurant, cafe, hotel, etc.'),
      min_price: z.number().optional().describe('Minimum price level (0-4)'),
      max_price: z.number().optional().describe('Maximum price level (0-4)'),
      open_now: z.boolean().optional().describe('Show only places open now'),
      rankby: z.string().optional().describe('Rank by: prominence (default) or distance'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 2,
    tags: ['places', 'search', 'restaurants', 'business'],
  },
  {
    name: 'maps_place_details',
    description: 'Get detailed information about a specific place',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_place_details',
    schema: z.object({
      place_id: z.string().describe('Google Place ID'),
      fields: z.string().optional().describe('Comma-separated fields to return'),
      language: z.string().optional().describe('Language code (e.g., "en", "uk")'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['place', 'details', 'reviews', 'hours'],
  },
  {
    name: 'maps_directions',
    description: 'Get turn-by-turn directions with live traffic awareness',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_directions',
    schema: z.object({
      origin: z.string().describe('Starting point address or coordinates'),
      destination: z.string().describe('Destination address or coordinates'),
      mode: z
        .enum(['driving', 'walking', 'bicycling', 'transit'])
        .optional()
        .describe('Travel mode'),
      waypoints: z.string().optional().describe('Intermediate stops, pipe-separated'),
      alternatives: z.boolean().optional().describe('Return multiple route options'),
      avoid: z.string().optional().describe('Avoid: tolls, highways, ferries'),
      departure_time: z.string().optional().describe('Departure time (epoch or "now")'),
      arrival_time: z.string().optional().describe('Arrival time (epoch)'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 2,
    tags: ['directions', 'route', 'navigation', 'traffic'],
  },
  {
    name: 'maps_distance_matrix',
    description: 'Calculate travel distance and time between locations',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_distance_matrix',
    schema: z.object({
      origins: z.string().describe('Origin address(es), pipe-separated'),
      destinations: z.string().describe('Destination address(es), pipe-separated'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['distance', 'travel-time', 'matrix'],
  },
  {
    name: 'maps_street_view',
    description: 'Get a Street View panoramic image with optional Cyberpunk styling',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_street_view',
    schema: z.object({
      location: z.string().describe('Location as address or "lat,lng"'),
      heading: z.number().optional().describe('Camera heading (0-360 degrees)'),
      pitch: z.number().optional().describe('Camera pitch (-90 to 90)'),
      fov: z.number().optional().describe('Field of view (10-120, default 90)'),
      cyberpunk: z.boolean().optional().describe('Apply Cyberpunk color filter'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['street-view', 'panorama', 'image', 'cyberpunk'],
  },
  {
    name: 'maps_static_map',
    description: 'Generate a static map image with optional Cyberpunk styling',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_static_map',
    schema: z.object({
      center: z.string().describe('Map center as address or "lat,lng"'),
      zoom: z.number().optional().describe('Zoom level (1-21)'),
      maptype: z
        .enum(['roadmap', 'satellite', 'terrain', 'hybrid'])
        .optional()
        .describe('Map type'),
      markers: z.string().optional().describe('Markers specification'),
      cyberpunk: z.boolean().optional().describe('Apply Cyberpunk color filter'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['map', 'static', 'image', 'cyberpunk'],
  },
  {
    name: 'maps_elevation',
    description: 'Get elevation data for specified locations',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_elevation',
    schema: z.object({
      locations: z.string().describe('Locations as "lat,lng" or "lat,lng|lat,lng|..."'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 4,
    tags: ['elevation', 'altitude', 'height'],
  },
  {
    name: 'maps_open_interactive_search',
    description: 'Open the interactive map with autocomplete search bar in the Atlas UI',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_open_interactive_search',
    schema: z.object({
      initial_query: z.string().optional().describe('Optional initial search query'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 2,
    tags: ['map', 'interactive', 'search', 'ui'],
  },
  {
    name: 'maps_generate_link',
    description: 'Generate a Google Maps URL for specific coordinates or location',
    backendId: GOOGLEMAPS,
    remoteToolName: 'maps_generate_link',
    schema: z.object({
      location: z.string().describe('Location (address or coordinates)'),
      zoom: z.number().optional().describe('Zoom level (1-20, default 15)'),
      map_type: z
        .enum(['roadmap', 'satellite', 'terrain', 'hybrid'])
        .optional()
        .describe('Map type'),
    }),
    categories: [ToolCategory.MAPS],
    priority: 3,
    tags: ['map', 'link', 'url', 'share'],
  },
];

// ─── Windsurf IDE Tools ─────────────────────────────────────────────────────

const WINDSURF = 'windsurf';

const WINDSURF_TOOLS: BridgedToolDefinition[] = [
  {
    name: 'windsurf_status',
    description: 'Get Windsurf IDE connection status, active model, and server health',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_status',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 1,
    tags: ['windsurf', 'status', 'health', 'ide', 'connection'],
  },
  {
    name: 'windsurf_get_models',
    description: 'List all available Windsurf models with tier info (free/value/premium)',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_get_models',
    schema: z.object({
      tier: z
        .string()
        .optional()
        .describe('Filter by tier: free, value, premium, or all (default: all)'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 2,
    tags: ['windsurf', 'models', 'list', 'tier'],
  },
  {
    name: 'windsurf_chat',
    description:
      'Send a chat message to Windsurf AI via the local language server (uses Chat API quota)',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_chat',
    schema: z.object({
      message: z.string().describe('Message to send to Windsurf AI'),
      model: z
        .string()
        .optional()
        .describe('Model to use (default: active model). e.g., swe-1.5, deepseek-r1'),
      system_prompt: z.string().optional().describe('Optional system prompt to prepend'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 1,
    tags: ['windsurf', 'chat', 'ai', 'llm', 'code'],
  },
  {
    name: 'windsurf_cascade',
    description:
      'Execute a Cascade flow in Windsurf (uses Cascade Actions quota). Best for complex multi-step tasks',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_cascade',
    schema: z.object({
      message: z.string().describe('Task description for Cascade to execute'),
      model: z.string().optional().describe('Model for Cascade (default: active model)'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 2,
    tags: ['windsurf', 'cascade', 'flow', 'multi-step', 'task'],
  },
  {
    name: 'windsurf_switch_model',
    description: 'Switch the active Windsurf model for subsequent chat/cascade calls',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_switch_model',
    schema: z.object({
      model: z.string().describe('Model ID to switch to (e.g., swe-1.5, deepseek-r1, kimi-k2.5)'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 2,
    tags: ['windsurf', 'model', 'switch', 'configure'],
  },
  {
    name: 'windsurf_health',
    description: 'Get detailed health monitoring metrics and performance statistics',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_health',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 3,
    tags: ['windsurf', 'health', 'metrics', 'stats'],
  },
  {
    name: 'windsurf_workspace_list',
    description: 'List all available workspaces with their details',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_workspace_list',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 2,
    tags: ['windsurf', 'workspace', 'list'],
  },
  {
    name: 'windsurf_workspace_switch',
    description: 'Switch to a different workspace context',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_workspace_switch',
    schema: z.object({
      workspace_id: z.string().describe('Workspace ID to switch to'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 2,
    tags: ['windsurf', 'workspace', 'switch'],
  },
  {
    name: 'windsurf_workspace_create',
    description: 'Create a new workspace context',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_workspace_create',
    schema: z.object({
      path: z.string().describe('Path to the workspace directory'),
      name: z.string().optional().describe('Optional name for the workspace'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION],
    priority: 3,
    tags: ['windsurf', 'workspace', 'create'],
  },
  {
    name: 'windsurf_system_health',
    description: 'Get comprehensive system health and error recovery status',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_system_health',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 3,
    tags: ['windsurf', 'system', 'health', 'error'],
  },
  {
    name: 'windsurf_field_experiment',
    description: 'Run Protobuf field discovery experiments to find Cortex protocol fields',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_field_experiment',
    schema: z.object({
      model: z.string().optional().describe('Model to use for experiments (default: active model)'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 4,
    tags: ['windsurf', 'experiment', 'protobuf', 'cortex'],
  },
  {
    name: 'windsurf_api_version',
    description: 'Get API version information and supported features',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_api_version',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 4,
    tags: ['windsurf', 'api', 'version'],
  },
  {
    name: 'windsurf_version_info',
    description: 'Get detailed version information and build details',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_version_info',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 4,
    tags: ['windsurf', 'version', 'info'],
  },
  {
    name: 'windsurf_compatibility_matrix',
    description: 'Get compatibility matrix for different API versions',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_compatibility_matrix',
    schema: z.object({
      version: z.string().optional().describe('Version to get compatibility matrix for (optional)'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 5,
    tags: ['windsurf', 'compatibility', 'matrix'],
  },
  {
    name: 'windsurf_migration_path',
    description: 'Get migration path between API versions',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_migration_path',
    schema: z.object({
      fromVersion: z.string().describe('Source version for migration path'),
      toVersion: z.string().describe('Target version for migration path'),
    }),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 5,
    tags: ['windsurf', 'migration', 'path'],
  },
  {
    name: 'windsurf_deprecation_warnings',
    description: 'Get deprecation warnings and sunset information',
    backendId: WINDSURF,
    remoteToolName: 'windsurf_deprecation_warnings',
    schema: z.object({}),
    categories: [ToolCategory.IDE_INTEGRATION, ToolCategory.META],
    priority: 4,
    tags: ['windsurf', 'deprecation', 'warnings'],
  },
];

// ─── Full Catalog ───────────────────────────────────────────────────────────

/** All bridged tools from all backends */
export const ALL_BRIDGED_TOOLS: BridgedToolDefinition[] = [
  ...MACOS_USE_TOOLS,
  ...GOOGLEMAPS_TOOLS,
  ...WINDSURF_TOOLS,
];

/**
 * Get tools filtered by categories.
 */
export function getToolsByCategories(categories: ToolCategoryValue[]): BridgedToolDefinition[] {
  const categorySet = new Set(categories);
  return ALL_BRIDGED_TOOLS.filter((tool) => tool.categories.some((cat) => categorySet.has(cat)));
}

/**
 * Get tools filtered by backend ID.
 */
export function getToolsByBackend(backendId: string): BridgedToolDefinition[] {
  return ALL_BRIDGED_TOOLS.filter((tool) => tool.backendId === backendId);
}

/**
 * Get tools filtered by maximum priority (1 = most important).
 * Tools with priority <= maxPriority are included.
 */
export function getToolsByPriority(maxPriority: number): BridgedToolDefinition[] {
  return ALL_BRIDGED_TOOLS.filter((tool) => tool.priority <= maxPriority);
}

/**
 * EXPERIMENTAL: Semantic tag search.
 * Returns tools whose tags overlap with the query terms.
 * Scored by number of matching tags * inverse priority (higher priority = higher score).
 */
export function searchToolsByTags(queryTerms: string[]): BridgedToolDefinition[] {
  const normalizedQuery = queryTerms.map((t) => t.toLowerCase());

  const scored = ALL_BRIDGED_TOOLS.map((tool) => {
    const matchCount = tool.tags.filter((tag) =>
      normalizedQuery.some((q) => tag.includes(q) || q.includes(tag)),
    ).length;
    // Score: matches * inverse priority (priority 1 = weight 5, priority 5 = weight 1)
    const score = matchCount * (6 - tool.priority);
    return { tool, score };
  })
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score);

  return scored.map((entry) => entry.tool);
}

/**
 * Get all unique categories in the catalog.
 */
export function getAllCategories(): ToolCategoryValue[] {
  const categories = new Set<ToolCategoryValue>();
  for (const tool of ALL_BRIDGED_TOOLS) {
    for (const cat of tool.categories) {
      categories.add(cat);
    }
  }
  return [...categories];
}

/**
 * Get summary statistics for the catalog.
 */
export function getCatalogStats(): Record<string, number> {
  const stats: Record<string, number> = { total: ALL_BRIDGED_TOOLS.length };
  for (const tool of ALL_BRIDGED_TOOLS) {
    const key = `backend:${tool.backendId}`;
    stats[key] = (stats[key] ?? 0) + 1;
    for (const cat of tool.categories) {
      stats[`category:${cat}`] = (stats[`category:${cat}`] ?? 0) + 1;
    }
  }
  return stats;
}
