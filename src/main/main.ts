/**
 * AtlasTrinity - Electron Main Process
 */

import { app, BrowserWindow, ipcMain, Menu, systemPreferences } from 'electron';

// Disable Electron Security Warnings in Dev
process.env.ELECTRON_DISABLE_SECURITY_WARNINGS = 'true';

// Fix for GPU/Skia errors on macOS (SharedImageManager::ProduceSkia)
// These errors are common in Electron 28+ with transparency/vibrancy enabled.
if (process.platform === 'darwin') {
  app.commandLine.appendSwitch('disable-features', 'Graphite,SkiaGraphite,UseSkiaRenderer');
  app.commandLine.appendSwitch('disable-gpu-memory-buffer-video-frames');
  app.commandLine.appendSwitch('disable-gpu-rasterization');
  app.commandLine.appendSwitch('disable-accelerated-2d-canvas');
  app.commandLine.appendSwitch('disable-zero-copy');
}

import { type ChildProcess, execSync, spawn } from 'node:child_process';
import * as fs from 'node:fs';
import * as os from 'node:os';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { checkPermissions, requestPermissions } from './permissions.js';

// Define Log Path
const LOG_PATH = path.join(os.homedir(), '.config/atlastrinity/logs/brain.log');

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let mainWindow: BrowserWindow | null = null;

const isDev = process.env.NODE_ENV === 'development';

// Check if first-run setup is needed
function isFirstRun(): boolean {
  const setupMarker = path.join(os.homedir(), '.config/atlastrinity/setup_complete');
  return !fs.existsSync(setupMarker);
}

// Run first-run setup in a terminal window
async function runFirstRunSetup(): Promise<boolean> {
  // Find Python executable
  let pythonExec = 'python3';
  const bundledPython = path.join(process.resourcesPath, '.venv/bin/python');
  if (fs.existsSync(bundledPython)) {
    pythonExec = bundledPython;
  }

  console.log('[SETUP] Running first-run installer...');

  return new Promise((resolve) => {
    const setupProcess = spawn(pythonExec, ['-m', 'brain.first_run_installer'], {
      cwd: process.resourcesPath,
      stdio: 'inherit', // Show output in terminal
      env: {
        ...process.env,
        PYTHONPATH: process.resourcesPath,
        PATH: `${path.dirname(pythonExec)}:/opt/homebrew/bin:${process.env.PATH}`,
      },
    });

    setupProcess.on('close', (code: number) => {
      console.log(`[SETUP] First-run installer exited with code ${code}`);
      resolve(code === 0);
    });

    setupProcess.on('error', (err: Error) => {
      console.error('[SETUP] Failed to run installer:', err);
      resolve(false);
    });
  });
}

function createAppMenu() {
  const isMac = process.platform === 'darwin';

  // biome-ignore lint/suspicious/noExplicitAny: Electron menu templates are complex nested objects
  const template: any[] = [
    // { role: 'appMenu' }
    ...(isMac
      ? [
          {
            label: app.name,
            submenu: [
              { role: 'about' },
              { type: 'separator' },
              { role: 'services' },
              { type: 'separator' },
              { role: 'hide' },
              { role: 'hideOthers' },
              { role: 'unhide' },
              { type: 'separator' },
              { role: 'quit' },
            ],
          },
        ]
      : []),
    // { role: 'fileMenu' }
    {
      label: 'File',
      submenu: [isMac ? { role: 'close' } : { role: 'quit' }],
    },
    // { role: 'editMenu' }
    {
      label: 'Edit',
      submenu: [
        { role: 'undo' },
        { role: 'redo' },
        { type: 'separator' },
        { role: 'cut' },
        { role: 'copy' },
        { role: 'paste' },
        ...(isMac
          ? [
              { role: 'pasteAndMatchStyle' },
              { role: 'delete' },
              { role: 'selectAll' },
              { type: 'separator' },
              {
                label: 'Speech',
                submenu: [{ role: 'startSpeaking' }, { role: 'stopSpeaking' }],
              },
            ]
          : [{ role: 'delete' }, { type: 'separator' }, { role: 'selectAll' }]),
      ],
    },
    // { role: 'viewMenu' }
    {
      label: 'View',
      submenu: [
        { role: 'reload' },
        { role: 'forceReload' },
        { role: 'toggleDevTools' },
        { type: 'separator' },
        { role: 'resetZoom' },
        { role: 'zoomIn' },
        { role: 'zoomOut' },
        { type: 'separator' },
        { role: 'togglefullscreen' },
      ],
    },
    // { role: 'windowMenu' }
    {
      label: 'Window',
      submenu: [
        { role: 'minimize' },
        { role: 'zoom' },
        ...(isMac
          ? [{ type: 'separator' }, { role: 'front' }, { type: 'separator' }, { role: 'window' }]
          : [{ role: 'close' }]),
      ],
    },
    {
      role: 'help',
      submenu: [
        {
          label: 'Learn More',
          click: async () => {
            const { shell } = await import('electron');
            await shell.openExternal('https://electronjs.org');
          },
        },
      ],
    },
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

async function createWindow(): Promise<void> {
  // First-run setup (production only)
  if (!isDev && isFirstRun()) {
    console.log('[SETUP] First run detected, launching setup...');
    const setupSuccess = await runFirstRunSetup();
    if (!setupSuccess) {
      console.error('[SETUP] First-run setup failed, but continuing...');
    }
  }

  // Create window immediately to avoid black screen/hang
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 1200,
    minHeight: 700,
    // transparent: true,
    // vibrancy: 'under-window',
    // visualEffectState: 'active',
    titleBarStyle: 'hiddenInset',
    backgroundColor: '#000000',
    webPreferences: {
      devTools: isDev,
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: false, // Required for extension compatibility
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // Check required permissions in background after window is created
  void checkPermissions().then(async (ok) => {
    if (!ok) {
      await requestPermissions();
    }
  });

  // Load the app
  if (isDev) {
    // Dynamic port detection for Vite (handles 3000 vs 3001 conflict)
    const findVitePort = async (): Promise<number> => {
      const ports = [3000, 3001];
      for (const port of ports) {
        try {
          const response = await fetch(`http://localhost:${port}`, { method: 'HEAD' });
          if (response.ok) return port;
        } catch {
          // Port not active
        }
      }
      return 3000; // Fallback
    };

    console.log('[ELECTRON] Searching for Vite dev server...');
    const attemptLoad = async (retryCount = 0) => {
      if (!mainWindow) return;

      const port = await findVitePort();
      const url = `http://localhost:${port}`;

      console.log(`[ELECTRON] Attempting to load ${url} (Retry ${retryCount})...`);
      try {
        await mainWindow.loadURL(url);
        mainWindow.webContents.openDevTools();
      } catch {
        if (retryCount < 10) {
          console.log(`[ELECTRON] Load failed, retrying in 2s...`);
          setTimeout(() => {
            void attemptLoad(retryCount + 1);
          }, 2000);
        } else {
          console.error('[ELECTRON] Failed to load renderer after 10 attempts');
        }
      }
    };

    void attemptLoad();
    // In dev, Python is started externally — just wait for it
    waitForBrainReady();
  } else {
    await mainWindow.loadFile(path.join(__dirname, '../renderer/index.html'));

    // Spawn Python Server in Production
    startPythonServer();
    waitForBrainReady();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // Protect against focus loss causing black screen
  // Вимкнено, щоб не перемикати фокус автоматично
  // mainWindow.on('blur', () => {
  //     console.log('[ELECTRON] Window lost focus - monitoring for recovery');
  //
  //     // Set timeout to restore focus if needed
  //     setTimeout(() => {
  //         if (mainWindow && !mainWindow.isFocused()) {
  //             console.log('[ELECTRON] Auto-restoring window focus');
  //             mainWindow.focus();
  //         }
  //     }, 500);
  // });

  // Protect renderer from hanging
  mainWindow.webContents.on('unresponsive', () => {
    console.error('[ELECTRON] Renderer became unresponsive - attempting reload');
    if (mainWindow) {
      mainWindow.webContents.reload();
    }
  });

  mainWindow.webContents.on('responsive', () => {
    console.log('[ELECTRON] Renderer became responsive again');
  });
}

// Python Server Management
let pythonProcess: ChildProcess | null = null;

/*
function startPythonServerDev() {
    // В dev режимі використовуємо .venv з проекту
    const projectRoot = path.join(__dirname, '../../..');
    const venvPython = path.join(projectRoot, '.venv/bin/python');

    let pythonExec = 'python3';
    if (fs.existsSync(venvPython)) {
        pythonExec = venvPython;
    }

    console.log(`[DEV] Starting Python server with: ${pythonExec}`);
    console.log(`[DEV] Working directory: ${projectRoot}`);

    pythonProcess = spawn(pythonExec, ['-m', 'uvicorn', 'brain.server:app', '--host', '127.0.0.1', '--port', '8000', '--reload'], {
        cwd: projectRoot,
        env: {
            ...process.env,
            PYTHONUNBUFFERED: '1',
            PYTHONPATH: path.join(projectRoot, 'src'),
        }
    });

    pythonProcess.stdout?.on('data', (data: Buffer) => {
        const message = data.toString();
        console.log(`[Python]: ${message}`);
    });

    pythonProcess.stderr?.on('data', (data: Buffer) => {
        const message = data.toString();
        // uvicorn пише в stderr
        console.log(`[Python]: ${message}`);
    });

    pythonProcess.on('error', (err: Error) => {
        console.error(`[DEV] Failed to start Python server: ${err}`);
    });

    pythonProcess.on('close', (code: number | null) => {
        console.log(`[DEV] Python process exited with code ${code}`);
    });
}
*/

function startPythonServer() {
  // Robust Python discovery
  let pythonExec = process.env.ATLASTRINITY_PYTHON || 'python3'; // Default fallback

  // 1. Try app-local .venv (dev/local prod test)
  const projectVenvPath = path.join(app.getAppPath(), '.venv/bin/python');

  // 2. Try packaged .venv if it was bundled (Portable mode)
  // When moved to /Applications, app.getAppPath() points to the app content
  const bundledVenvPath = path.join(process.resourcesPath, '.venv/bin/python');

  if (fs.existsSync(bundledVenvPath)) {
    pythonExec = bundledVenvPath;
  } else if (fs.existsSync(projectVenvPath)) {
    pythonExec = projectVenvPath;
  }

  console.log(`Starting Python server with: ${pythonExec}`);
  console.log(`Working directory: ${process.resourcesPath}`);

  pythonProcess = spawn(pythonExec, ['-m', 'brain.server'], {
    cwd: process.resourcesPath,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      PYTHONPATH: process.resourcesPath,
      PATH: `${path.dirname(pythonExec)}:${process.env.PATH}`, // Add venv/bin to PATH
    },
  });

  pythonProcess.stdout?.on('data', (data: Buffer) => {
    const message = data.toString();
    console.log(`[Python]: ${message}`);
    if (mainWindow) {
      void mainWindow.webContents.executeJavaScript(
        `console.log('[Python]: ' + ${JSON.stringify(message)})`,
      );
    }
  });

  pythonProcess.stderr?.on('data', (data: Buffer) => {
    const message = data.toString();
    console.error(`[Python Err]: ${message}`);
    if (mainWindow) {
      void mainWindow.webContents.executeJavaScript(
        `console.error('[Python Err]: ' + ${JSON.stringify(message)})`,
      );
    }
  });

  pythonProcess.on('error', (err: Error) => {
    console.error(`Failed to start Python server: ${err}`);
    if (mainWindow) {
      void mainWindow.webContents.executeJavaScript(
        `console.error('CRITICAL: Failed to start Python server: ' + ${JSON.stringify(err.message)})`,
      );
    }
  });

  pythonProcess.on('close', (code: number | null) => {
    console.log(`Python process exited with code ${code}`);
    if (mainWindow && code !== 0 && code !== null) {
      void mainWindow.webContents.executeJavaScript(
        `console.error('CRITICAL: Python server exited with code ' + ${code})`,
      );
    }
  });
}

// Signal renderer when Python backend is ready (avoids ERR_CONNECTION_REFUSED noise in DevTools)
function waitForBrainReady() {
  const checkHealth = async (attempt = 0) => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/health');
      if (res.ok) {
        console.log('[MAIN] Brain backend is ready.');
        if (mainWindow) {
          void mainWindow.webContents.executeJavaScript(
            'window.__BRAIN_READY__ = true; window.dispatchEvent(new Event("brain-ready"));',
          );
        }
        return;
      }
    } catch {
      // Backend not up yet — expected during startup
    }
    const delay = Math.min(1000 * 1.5 ** attempt, 5000);
    setTimeout(() => void checkHealth(attempt + 1), delay);
  };
  // Start checking after a short delay to let Python spin up
  setTimeout(() => void checkHealth(), 3000);
}

// IPC Handlers for renderer communication
ipcMain.handle('get-system-info', async () => {
  return {
    platform: process.platform,
    arch: process.arch,
    version: app.getVersion(),
  };
});

ipcMain.handle('check-accessibility', async () => {
  return systemPreferences.isTrustedAccessibilityClient(false);
});

ipcMain.handle('request-accessibility', async () => {
  return systemPreferences.isTrustedAccessibilityClient(true);
});

ipcMain.handle('read-brain-log', async () => {
  try {
    if (!fs.existsSync(LOG_PATH)) return [];

    // Read last 50KB for initial load
    const stats = await fs.promises.stat(LOG_PATH);
    const size = stats.size;
    const bufferSize = Math.min(50 * 1024, size);
    const buffer = Buffer.alloc(bufferSize);

    const handle = await fs.promises.open(LOG_PATH, 'r');
    await handle.read(buffer, 0, bufferSize, size - bufferSize);
    await handle.close();

    const content = buffer.toString('utf-8');
    return content.split('\n').filter(Boolean);
  } catch (error) {
    console.error('Failed to read log:', error);
    return [];
  }
});

// Log Streaming (Push Model)
let logWatcher: fs.FSWatcher | null = null;
let lastLogSize = 0;

ipcMain.on('start-log-stream', (_event) => {
  if (logWatcher) return; // Already watching

  void (async () => {
    try {
      if (!fs.existsSync(LOG_PATH)) return;

      const stats = await fs.promises.stat(LOG_PATH);
      lastLogSize = stats.size;

      console.log('[ELECTRON] Starting log stream watcher...');

      let logBuffer = '';
      let isProcessingLog = false;
      logWatcher = fs.watch(LOG_PATH, (eventType) => {
        void (async () => {
          if (eventType === 'change' && !isProcessingLog) {
            isProcessingLog = true;
            try {
              const newStats = await fs.promises.stat(LOG_PATH);
              const newSize = newStats.size;

              if (newSize > lastLogSize) {
                // Read only the new part
                const bufferSize = newSize - lastLogSize;
                const buffer = Buffer.alloc(bufferSize);

                const handle = await fs.promises.open(LOG_PATH, 'r');
                await handle.read(buffer, 0, bufferSize, lastLogSize);
                await handle.close();

                const newContent = buffer.toString('utf-8');
                const rawLines = (logBuffer + newContent).split('\n');

                // Keep the last part (potentially incomplete line) in the buffer
                logBuffer = rawLines.pop() || '';

                const lines = rawLines.filter(Boolean);

                if (lines.length > 0 && mainWindow) {
                  mainWindow.webContents.send('log-update', lines);
                }

                lastLogSize = newSize;
              } else if (newSize < lastLogSize) {
                // File truncated / rotated
                lastLogSize = newSize;
                logBuffer = '';
              }
            } catch (err) {
              console.error('[ELECTRON] Error reading log update:', err);
            } finally {
              isProcessingLog = false;
            }
          }
        })();
      });
    } catch (error) {
      console.error('[ELECTRON] Failed to start log stream:', error);
    }
  })();
});

ipcMain.on('stop-log-stream', () => {
  if (logWatcher) {
    logWatcher.close();
    logWatcher = null;
    console.log('[ELECTRON] Log stream stopped.');
  }
});

// App lifecycle
void app.whenReady().then(() => {
  createAppMenu();
  void createWindow();
});

app.on('window-all-closed', () => {
  // В development режимі завжди закриваємо додаток (включно з macOS)
  // В production на macOS - стандартна поведінка (додаток залишається в dock)
  if (isDev || process.platform !== 'darwin') {
    app.quit();
  }
});

// Ensure Python server is killed when app quits
app.on('before-quit', () => {
  if (pythonProcess) {
    console.log('Quitting: Killing Python server...');
    // Send SIGTERM to allow graceful shutdown via lifespan manager
    pythonProcess.kill('SIGTERM');
    pythonProcess = null;
  }

  // Clean up any stray processes (dev always aggressive, production as safety net)
  console.log('Final process cleanup...');
  try {
    // Targeted pkill for core components to avoid "orphans"
    // brain.server handles its own children, but this is a final fail-safe
    const targets =
      'vibe_server vibe brain.server mcp-server memory_server graph_server macos-use watch_config';
    const command = `${targets
      .split(' ')
      .map((t) => `pkill -15 -f "${t}"`)
      .join('; ')}; true`;

    execSync(command, {
      stdio: 'ignore',
      timeout: 2000, // Shorter timeout for graceful cleanup
    });

    // Attempt to free port 3000 (Vite) if it was spawned by us or is lingering
    try {
      execSync('lsof -ti :3000 | xargs kill -9', { stdio: 'ignore' });
    } catch {
      // Ignore error if port 3000 is already free
    }

    console.log('Cleanup completed.');
  } catch {
    console.log('Cleanup finished.');
  }
});

app.on('will-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill('SIGKILL');
  }
});

app.on('activate', () => {
  if (mainWindow === null) {
    void createWindow();
  }
});

// Handle certificate errors in development
if (isDev) {
  app.on('certificate-error', (event, _webContents, _url, _error, _certificate, callback) => {
    event.preventDefault();
    callback(true);
  });
}
