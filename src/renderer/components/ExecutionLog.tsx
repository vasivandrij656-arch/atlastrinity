/**
 * ExecutionLog - Left panel log display
 * Smooth streaming with slide-in animations
 */

import type * as React from 'react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

import type { LogEntry } from '../types';

interface ExecutionLogProps {
  logs: LogEntry[];
}

const ExecutionLog: React.FC<ExecutionLogProps> = ({ logs }) => {
  // Filter out noisy connection logs
  const filteredLogs = logs.filter(
    (l) => !(l.message.includes('Connected to') || l.message.includes('health check')),
  );

  const logsEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Track if user has scrolled away from bottom (to pause auto-scroll)
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const lastLogCountRef = useRef(filteredLogs.length);

  // Track new log IDs for streaming animation
  const [newLogIds, setNewLogIds] = useState<Set<string>>(new Set());

  // Check if user is near bottom
  const isNearBottom = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return true;
    const { scrollTop, scrollHeight, clientHeight } = container;
    return Math.ceil(scrollHeight - scrollTop - clientHeight) <= 150;
  }, []);

  // Handle scroll events to detect user scrolling
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const handleScroll = () => {
      if (isNearBottom()) {
        setUserScrolledUp(false);
      }
    };

    const handleWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) {
        setUserScrolledUp(true);
      }
      if (e.deltaY > 0) {
        if (isNearBottom()) {
          setUserScrolledUp(false);
        }
      }
    };

    container.addEventListener('scroll', handleScroll, { passive: true });
    container.addEventListener('wheel', handleWheel, { passive: true });

    return () => {
      container.removeEventListener('scroll', handleScroll);
      container.removeEventListener('wheel', handleWheel);
    };
  }, [isNearBottom]);

  // Track new logs for streaming animation
  useEffect(() => {
    const hasNewLogs = filteredLogs.length > lastLogCountRef.current;
    if (hasNewLogs) {
      const newIds = new Set<string>();
      for (let i = lastLogCountRef.current; i < filteredLogs.length; i++) {
        newIds.add(filteredLogs[i].id);
      }
      setNewLogIds(newIds);
      const timer = setTimeout(() => setNewLogIds(new Set()), 600);
      return () => clearTimeout(timer);
    }
  }, [filteredLogs]);

  // Auto-scroll logic - smooth scrolling
  useLayoutEffect(() => {
    const hasNewLogs = filteredLogs.length > lastLogCountRef.current;
    lastLogCountRef.current = filteredLogs.length;

    if (isNearBottom() || filteredLogs.length <= 1 || (hasNewLogs && !userScrolledUp)) {
      const timer = setTimeout(() => {
        const container = scrollContainerRef.current;
        if (container) {
          container.scrollTo({
            top: container.scrollHeight,
            behavior: 'smooth',
          });
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [filteredLogs, userScrolledUp, isNearBottom]);

  const formatTime = (ts: Date | number | string) => {
    let d: Date;
    if (ts instanceof Date) {
      d = ts;
    } else if (typeof ts === 'number') {
      d = new Date(ts < 10000000000 ? ts * 1000 : ts);
    } else if (typeof ts === 'string') {
      const n = Number(ts);
      if (!Number.isNaN(n)) {
        d = new Date(n < 10000000000 ? n * 1000 : n);
      } else {
        d = new Date(ts);
      }
    } else {
      d = new Date();
    }

    if (Number.isNaN(d.getTime())) {
      return '??:??:??';
    }

    return d.toLocaleTimeString([], {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  };

  const getLogColor = (type: string) => {
    switch (type) {
      case 'error':
        return '#FF4D4D';
      case 'warning':
        return '#FFB800';
      case 'success':
        return '#00FF88';
      case 'action':
        return '#00A3FF';
      case 'voice':
        return '#BB86FC';
      default:
        return 'rgba(255, 255, 255, 0.45)';
    }
  };

  const getAgentColor = (agent: string) => {
    switch (agent) {
      case 'GRISHA':
        return 'var(--grisha-orange)';
      case 'TETYANA':
        return 'var(--tetyana-green)';
      case 'USER':
        return 'var(--user-turquoise)';
      default:
        return 'var(--atlas-blue)';
    }
  };

  const getLogTypeIcon = (type: string) => {
    switch (type) {
      case 'error':
        return '●';
      case 'warning':
        return '◆';
      case 'success':
        return '✓';
      case 'action':
        return '▸';
      default:
        return '·';
    }
  };

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden relative min-h-0"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        minHeight: 0,
        fontFamily: "'Outfit', 'Inter', sans-serif",
      }}
    >
      <div style={{ height: '32px', flexShrink: 0 }} /> {/* Spacer for title bar area */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin min-h-0"
        style={{
          overscrollBehavior: 'contain',
          paddingBottom: '120px',
          overflowY: 'auto',
          overflowX: 'hidden',
          flex: '1 1 0%',
          minHeight: 0,
          paddingRight: 0,
        }}
      >
        {filteredLogs.map((log) => {
          const isNew = newLogIds.has(log.id);

          return (
            <button
              type="button"
              key={log.id}
              className={`group ${isNew ? 'log-stream-in' : ''}`}
              style={{
                display: 'flex',
                flexDirection: 'column',
                marginBottom: '1px',
                padding: '5px 6px 5px 10px',
                marginRight: '2px',
                borderRadius: '2px',
                transition: 'background 0.2s ease',
                cursor: 'default',
                background: 'none',
                border: 'none',
                textAlign: 'left',
                width: 'calc(100% - 2px)',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent';
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  // If we added a click handler in the future, it would go here
                }
              }}
            >
              {/* Header Row: Agent + Time + Type */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '2px',
                }}
                className="group-hover-opacity-60 opacity-35"
              >
                <span
                  style={{
                    fontSize: '7.5px',
                    fontWeight: 700,
                    letterSpacing: '0.15em',
                    textTransform: 'uppercase',
                    color: getAgentColor(log.agent),
                    fontFamily: "'JetBrains Mono', monospace",
                  }}
                >
                  {log.agent}
                </span>

                <span
                  style={{
                    fontSize: '7.5px',
                    fontFamily: "'JetBrains Mono', monospace",
                    fontWeight: 500,
                    letterSpacing: '-0.02em',
                    color: getLogColor(log.type),
                  }}
                >
                  {formatTime(log.timestamp)}
                </span>

                <span
                  style={{
                    fontSize: '7.5px',
                    fontWeight: 700,
                    color: getLogColor(log.type),
                    fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: '0.05em',
                    textTransform: 'uppercase',
                  }}
                >
                  {getLogTypeIcon(log.type)} {log.type.toUpperCase()}
                </span>
              </div>
              <div style={{ flex: 1, paddingLeft: '2px' }}>
                <span
                  style={{
                    fontSize: '10.5px',
                    fontWeight: 350,
                    lineHeight: '1.55',
                    overflowWrap: 'break-word',
                    wordBreak: 'break-word',
                    transition: 'color 0.2s ease',
                    fontFamily: log.message.includes('[VIBE-')
                      ? "'JetBrains Mono', monospace"
                      : "'Outfit', 'Inter', sans-serif",
                    ...(log.message.includes('[VIBE-THOUGHT]')
                      ? {
                          color: 'rgba(180, 180, 200, 0.6)',
                          paddingLeft: '12px',
                          fontStyle: 'italic',
                          marginLeft: '6px',
                          borderLeft: '1px solid rgba(120, 120, 140, 0.2)',
                        }
                      : log.message.includes('[VIBE-ACTION]')
                        ? { color: '#FBBF24' }
                        : log.message.includes('[VIBE-GEN]')
                          ? { color: '#4ADE80' }
                          : log.message.includes('[VIBE-LIVE]')
                            ? { color: '#93C5FD' }
                            : log.agent === 'USER'
                              ? { color: '#00E5FF', opacity: 0.85 }
                              : { color: '#00A3FF', opacity: 0.8 }),
                  }}
                >
                  {typeof log.message === 'object'
                    ? JSON.stringify(log.message)
                    : log.message.replace('🧠 [VIBE-THOUGHT]', '').trim()}
                </span>
              </div>
            </button>
          );
        })}

        <div ref={logsEndRef} />

        {filteredLogs.length === 0 && (
          <div
            className="h-full flex flex-col items-center justify-center"
            style={{
              opacity: 0.08,
              fontSize: '9px',
              gap: '8px',
              letterSpacing: '0.4em',
              textTransform: 'uppercase',
              fontFamily: "'Outfit', sans-serif",
            }}
          >
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '50%',
                border: '1px solid currentColor',
                opacity: 0.2,
              }}
              className="animate-spin-slow"
            />
            <span>System Initialized</span>
            <span>Awaiting Core Link...</span>
          </div>
        )}
      </div>
    </div>
  );
};

export default ExecutionLog;
