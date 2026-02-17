import { useCallback, useEffect, useState } from 'react';
import type {
  AgentName,
  ChatMessage,
  LogEntry,
  MapData,
  SystemMetrics,
  SystemState,
} from '../types';

const API_BASE = 'http://127.0.0.1:8000';

// Regex to capture timestamp, level, and message
// 2026-02-15 05:12:47,872 - brain - INFO - Message
const LOG_LINE_REGEX = /^(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2}),\d+\s-\s(\w+)\s-\s(\w+)\s-\s(.+)$/;
const AGENT_PREFIX_REGEX = /^\[.*?\]\s*/;

export const useBrainApi = () => {
  const [systemState, setSystemState] = useState<SystemState>('IDLE');
  const [activeAgent, setActiveAgent] = useState<AgentName>('ATLAS');
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [metrics, setMetrics] = useState<SystemMetrics>({
    cpu: '0%',
    memory: '0.0GB',
    net_up_val: '0.0',
    net_up_unit: 'K/S',
    net_down_val: '0.0',
    net_down_unit: 'K/S',
  });
  const [isConnected, setIsConnected] = useState(false);
  const [mapData, setMapData] = useState<MapData>({ type: 'STATIC' });
  const [activeMode, setActiveMode] = useState<'STANDARD' | 'LIVE'>('STANDARD');
  const [currentTask, setCurrentTask] = useState<string>('');
  const [currentSessionId, setCurrentSessionId] = useState<string>('current_session');

  const addLog = useCallback(
    (agent: AgentName, message: string, type: LogEntry['type'] = 'info') => {
      const entry: LogEntry = {
        id: `log-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        timestamp: new Date(),
        agent,
        message,
        type,
      };
      setLogs((prev) => [...prev.slice(-100), entry]);
    },
    [],
  );

  const pollState = useCallback(async (viewMode: 'NEURAL' | 'MAP') => {
    try {
      const response = await fetch(`${API_BASE}/api/state`);
      if (response.ok) {
        setIsConnected(true);
        const data = await response.json();
        if (data) {
          setSystemState(data.system_state || 'IDLE');
          setActiveAgent(data.active_agent || 'ATLAS');
          if (data.session_id) setCurrentSessionId(data.session_id);
          setCurrentTask(data.current_task || '');
          setActiveMode(data.active_mode || 'STANDARD');
          if (data.metrics) setMetrics(data.metrics);

          if (data.map_state) {
            const ms = data.map_state;
            const av = ms.agent_view;

            setMapData((prev) => {
              const newState = { ...prev };
              let changed = false;

              if (av?.image_path) {
                const fileUrl = `file://${av.image_path}`;
                if (
                  prev.url !== fileUrl ||
                  prev.type !== 'STREET' ||
                  prev.agentView?.timestamp !== av.timestamp
                ) {
                  newState.url = fileUrl;
                  newState.type = 'STREET';
                  newState.location = `AGENT_VIEW @ ${av.heading}°`;
                  newState.agentView = {
                    heading: av.heading,
                    pitch: av.pitch,
                    fov: av.fov,
                    timestamp: av.timestamp,
                    lat: av.lat,
                    lng: av.lng,
                  };
                  changed = true;
                }
              }

              if (JSON.stringify(prev.distanceInfo) !== JSON.stringify(ms.distance_info)) {
                newState.distanceInfo = ms.distance_info;
                changed = true;
              }

              if (ms.show_map && viewMode !== 'MAP') {
                // This logic might need to be handled by the caller too
              }

              return changed ? newState : prev;
            });
          }

          if (data.logs && !window.electron) {
            setLogs(
              data.logs.map((l: { timestamp: string | number }) => ({
                ...l,
                timestamp:
                  typeof l.timestamp === 'number'
                    ? new Date(l.timestamp > 10000000000 ? l.timestamp : l.timestamp * 1000)
                    : new Date(l.timestamp),
              })),
            );
          }

          if (data.messages) {
            setChatHistory(
              data.messages.map((m: { timestamp: string | number }) => ({
                ...m,
                timestamp:
                  typeof m.timestamp === 'number'
                    ? new Date(m.timestamp > 10000000000 ? m.timestamp : m.timestamp * 1000)
                    : new Date(m.timestamp),
              })),
            );
          }
        }
      }
    } catch {
      setIsConnected(false);
    }
  }, []);

  // Parse raw log line into LogEntry
  const parseLogLine = useCallback((line: string): LogEntry | null => {
    const match = line.match(LOG_LINE_REGEX);

    if (!match) return null;

    const [, timestampStr, agentRaw, levelRaw, message] = match;

    // Filter out noisy/repetitive logs
    if (
      message.includes('STT model loaded successfully') ||
      message.includes('Health check') ||
      message.includes('Connected to') ||
      message.includes('GET /api/state')
    ) {
      return null;
    }

    // Map Level to Type
    let type: LogEntry['type'] = 'info';
    const level = levelRaw.toLowerCase();
    if (level === 'error' || level === 'critical') type = 'error';
    if (level === 'warning') type = 'warning';

    // Map Logger to Agent
    let agent: AgentName = 'SYSTEM';
    const agentLower = agentRaw.toLowerCase();
    if (agentLower === 'atlas') agent = 'ATLAS';
    if (agentLower === 'tetyana') agent = 'TETYANA';
    if (agentLower === 'grisha') agent = 'GRISHA';
    if (agentLower === 'user') agent = 'USER';

    // Special handling for [AGENT] prefixes in message
    if (message.startsWith('[ATLAS]')) agent = 'ATLAS';
    if (message.startsWith('[TETYANA]')) agent = 'TETYANA';
    if (message.startsWith('[GRISHA]')) agent = 'GRISHA';

    return {
      // Robust ID: Timestamp + Hash of message + Random suffix to ensure uniqueness
      id: `file-${timestampStr}-${Math.abs(
        message.split('').reduce((a, b) => {
          a = (a << 5) - a + b.charCodeAt(0);
          return a & a;
        }, 0),
      )}-${Math.random().toString(36).substr(2, 5)}`,
      timestamp: new Date(timestampStr),
      agent,
      message: message.replace(AGENT_PREFIX_REGEX, ''), // Remove prefix if present

      type,
    };
  }, []);

  // Real-time Log Streaming via Electron IPC
  useEffect(() => {
    if (!window.electron) return;

    // 1. Load initial history
    void window.electron.readBrainLog().then((rawLines) => {
      const historicLogs = rawLines.map(parseLogLine).filter((l): l is LogEntry => l !== null);

      if (historicLogs.length > 0) {
        // Simple deduplication for initial load
        const uniqueLogs = Array.from(
          new Map(historicLogs.map((item) => [item.id, item])).values(),
        );
        setLogs(uniqueLogs.slice(-200));
      }
    });

    // 2. Subscribe to real-time updates
    const unsubscribe = window.electron.onLogUpdate((lines) => {
      const newLogs = lines.map(parseLogLine).filter((l): l is LogEntry => l !== null);

      if (newLogs.length > 0) {
        setLogs((current) => {
          // 1. Internal deduplication (within the incoming batch)
          const uniqueInBatch: LogEntry[] = [];
          for (const newLog of newLogs) {
            const isDuplicateInBatch = uniqueInBatch.some(
              (l) =>
                l.message === newLog.message &&
                l.agent === newLog.agent &&
                Math.abs(l.timestamp.getTime() - newLog.timestamp.getTime()) < 500,
            );
            if (!isDuplicateInBatch) uniqueInBatch.push(newLog);
          }

          // 2. Cross-batch deduplication (against the last N logs in history)
          const filteredNewLogs = uniqueInBatch.filter((newLog) => {
            // Check against last 10 entries instead of just the last one
            const recentLogs = current.slice(-10);
            return !recentLogs.some(
              (lastLog) =>
                lastLog.message === newLog.message &&
                lastLog.agent === newLog.agent &&
                Math.abs(lastLog.timestamp.getTime() - newLog.timestamp.getTime()) < 1000,
            );
          });

          if (filteredNewLogs.length === 0) return current;

          const combined = [...current, ...filteredNewLogs];
          // Keep buffer reasonable size (e.g. 500) to prevent memory issues
          return combined.length > 500 ? combined.slice(combined.length - 500) : combined;
        });
      }
    });

    // 3. Start watching
    window.electron.startLogStream();

    return () => {
      unsubscribe();
      window.electron.stopLogStream();
    };
  }, [parseLogLine]);

  const handleCommand = useCallback(
    async (cmd: string, files: File[] = []) => {
      addLog(
        'ATLAS',
        `Command: ${cmd}${files.length > 0 ? ` [${files.length} files]` : ''}`,
        'action',
      );

      // Add user message to chat history
      setChatHistory((prev) => [
        ...prev,
        {
          agent: 'USER' as const,
          text: cmd,
          timestamp: new Date(),
          type: 'text' as const,
        },
      ]);

      setSystemState('PROCESSING');
      try {
        const formData = new FormData();
        formData.append('request', cmd);
        for (const file of files) {
          formData.append('files', file);
        }

        const response = await fetch(`${API_BASE}/api/chat`, {
          method: 'POST',
          body: formData,
        });

        if (!response.ok) throw new Error(`Server Error: ${response.status}`);
        const data = await response.json();

        if (data.status === 'completed' || data.status === 'success') {
          const result = data.result || data.response;
          let message = '';
          if (typeof result === 'string') {
            message = result;
          } else if (typeof result === 'object') {
            if (Array.isArray(result)) {
              const steps = result.filter((r: { success?: boolean }) => r.success).length;
              message = `Task completed successfully: ${steps} steps executed.`;
            } else {
              message = result.result
                ? typeof result.result === 'string'
                  ? result.result
                  : JSON.stringify(result.result)
                : JSON.stringify(result);
            }
          } else {
            message = String(result);
          }
          addLog('ATLAS', message, 'success');

          // Add agent response to chat history
          const agentName = data.active_agent || 'ATLAS';
          setChatHistory((prev) => [
            ...prev,
            {
              agent: agentName,
              text: message,
              timestamp: new Date(),
              type: 'voice' as const,
            },
          ]);

          setSystemState('IDLE');
        } else {
          addLog('TETYANA', 'Task execution finished', 'info');
          setSystemState('IDLE');
        }
      } catch (error) {
        console.error(error);
        addLog('ATLAS', 'Failed to reach Neural Core. Is Python server running?', 'error');
        setSystemState('ERROR');
      }
    },
    [addLog],
  );

  const handleNewSession = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/session/reset`, {
        method: 'POST',
      });
      if (response.ok) {
        const result = await response.json();
        setLogs([]);
        setChatHistory([]);
        if (result.session_id) setCurrentSessionId(result.session_id);
        return result.session_id;
      }
    } catch (err) {
      console.error('Failed to reset session:', err);
    }
    return null;
  };

  const handleRestoreSession = async (sessionId: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/sessions/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (response.ok) {
        setLogs([]);
        setChatHistory([]);
        setCurrentSessionId(sessionId);
        await pollState('NEURAL'); // Refresh state after restore
        return true;
      }
    } catch (err) {
      console.error('Failed to restore session:', err);
    }
    return false;
  };

  const handlePause = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/pause`, { method: 'POST' });
      if (response.ok) {
        addLog('SYSTEM', '⏸️ Призупинено', 'warning');
        setSystemState('PAUSED');
        return true;
      }
    } catch (err) {
      console.error('Failed to pause:', err);
    }
    return false;
  };

  const handleResume = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/resume`, { method: 'POST' });
      if (response.ok) {
        addLog('SYSTEM', '▶️ Продовжено', 'success');
        return true;
      }
    } catch (err) {
      console.error('Failed to resume:', err);
    }
    return false;
  };

  return {
    systemState,
    setSystemState,
    activeAgent,
    logs,
    setLogs,
    chatHistory,
    setChatHistory,
    metrics,
    isConnected,
    setIsConnected,
    mapData,
    setMapData,
    currentTask,
    activeMode,
    currentSessionId,
    pollState,
    handleCommand,
    addLog,
    handleNewSession,
    handleRestoreSession,
    handlePause,
    handleResume,
  };
};
