/**
 * ChatPanel - Right panel for agent messages
 * Smooth streaming with fade-in + slide animation
 */

import * as React from 'react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';

type AgentName = 'ATLAS' | 'TETYANA' | 'GRISHA' | 'SYSTEM' | 'USER';

interface Message {
  id: string;
  agent: AgentName;
  text: string;
  timestamp: Date;
  type?: 'text' | 'voice';
}

interface ChatPanelProps {
  messages: Message[];
}

const ChatPanel: React.FC<ChatPanelProps> = React.memo(({ messages }) => {
  // Show ALL messages — no filtering by type.
  // The backend sends both text and voice types; we want them all visible.
  const filteredMessages = messages;

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Track if user has scrolled away from bottom (to pause auto-scroll)
  const [userScrolledUp, setUserScrolledUp] = useState(false);
  const lastMessageCountRef = useRef(filteredMessages.length);

  // Track new message IDs for streaming animation
  const [newMessageIds, setNewMessageIds] = useState<Set<string>>(new Set());

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

  // Track new messages for streaming animation
  useEffect(() => {
    const hasNewMessages = filteredMessages.length > lastMessageCountRef.current;
    if (hasNewMessages) {
      const newIds = new Set<string>();
      for (let i = lastMessageCountRef.current; i < filteredMessages.length; i++) {
        newIds.add(filteredMessages[i].id);
      }
      setNewMessageIds(newIds);
      // Clear animation class after animation completes
      const timer = setTimeout(() => setNewMessageIds(new Set()), 800);
      return () => clearTimeout(timer);
    }
  }, [filteredMessages]);

  // Auto-scroll logic - smooth scrolling
  useLayoutEffect(() => {
    const hasNewMessages = filteredMessages.length > lastMessageCountRef.current;
    lastMessageCountRef.current = filteredMessages.length;

    if (isNearBottom() || (hasNewMessages && !userScrolledUp) || filteredMessages.length <= 1) {
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
  }, [filteredMessages, userScrolledUp, isNearBottom]);

  const getAgentColor = (agent: string) => {
    const a = agent.toUpperCase().trim();
    switch (a) {
      case 'GRISHA':
        return 'var(--grisha-orange, #FFB800)';
      case 'TETYANA':
        return 'var(--tetyana-green, #00FF88)';
      case 'USER':
        return 'var(--user-turquoise, #00E5FF)';
      case 'SYSTEM':
        return 'rgba(255, 255, 255, 0.5)';
      default:
        return 'var(--atlas-blue, #00A3FF)';
    }
  };

  const getMessageGlow = (agent: string) => {
    const a = agent.toUpperCase().trim();
    switch (a) {
      case 'GRISHA':
        return 'rgba(255, 140, 0, 0.03)';
      case 'TETYANA':
        return 'rgba(0, 255, 65, 0.03)';
      case 'USER':
        return 'rgba(0, 229, 255, 0.04)';
      default:
        return 'rgba(0, 163, 255, 0.03)';
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
      {/* Main Chat Stream */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto overflow-x-hidden scrollbar-thin min-h-0"
        style={{
          overscrollBehavior: 'contain',
          overflowY: 'auto',
          overflowX: 'hidden',
          flex: '1 1 0%',
          minHeight: 0,
        }}
      >
        {filteredMessages.length === 0 ? (
          <div
            className="h-full flex items-center justify-center"
            style={{
              opacity: 0.08,
              fontStyle: 'italic',
              fontSize: '9px',
              letterSpacing: '0.5em',
              textTransform: 'uppercase',
              fontFamily: "'Outfit', sans-serif",
            }}
          >
            Waiting for neural link...
          </div>
        ) : (
          <div
            className="flex flex-col py-1 pb-32 px-4"
            style={{ paddingLeft: '16px', paddingRight: '16px', gap: '6px' }}
          >
            {filteredMessages.map((msg) => {
              const isNew = newMessageIds.has(msg.id);
              const isUser = msg.agent === 'USER';

              return (
                <div
                  key={msg.id}
                  className={`group ${isNew ? 'chat-stream-in' : ''}`}
                  style={{
                    marginBottom: '8px',
                    paddingLeft: '6px',
                    borderLeft: `2px solid ${getAgentColor(msg.agent)}`,
                    borderLeftWidth: isUser ? '1px' : '2px',
                    borderLeftColor: isUser ? 'rgba(0, 229, 255, 0.15)' : getAgentColor(msg.agent),
                    opacity: isNew ? undefined : 1,
                    background: isUser ? 'transparent' : getMessageGlow(msg.agent),
                    borderRadius: '0 4px 4px 0',
                    padding: '6px 8px 6px 10px',
                    transition: 'background 0.3s ease, border-color 0.3s ease',
                  }}
                >
                  <div className="flex items-center" style={{ marginBottom: '4px', gap: '10px' }}>
                    <span
                      style={{
                        fontSize: '8px',
                        fontWeight: 700,
                        letterSpacing: '0.12em',
                        textTransform: 'uppercase',
                        color: getAgentColor(msg.agent),
                        fontFamily: "'JetBrains Mono', monospace",
                        opacity: 0.7,
                        transition: 'opacity 0.3s ease',
                      }}
                      className="group-hover-opacity-90"
                    >
                      {msg.agent}
                    </span>
                    <span
                      style={{
                        fontSize: '8px',
                        fontFamily: "'JetBrains Mono', monospace",
                        letterSpacing: '-0.02em',
                        textTransform: 'uppercase',
                        fontWeight: 500,
                        color: getAgentColor(msg.agent),
                        opacity: 0.35,
                      }}
                    >
                      {msg.timestamp.toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                      })}
                    </span>
                  </div>

                  <div
                    style={{
                      fontSize: '11px',
                      fontWeight: isUser ? 400 : 350,
                      lineHeight: '1.6',
                      overflowWrap: 'break-word',
                      wordBreak: 'break-word',
                      paddingLeft: '2px',
                      paddingTop: '1px',
                      paddingBottom: '1px',
                      fontFamily: isUser
                        ? "'JetBrains Mono', monospace"
                        : "'Outfit', 'Inter', sans-serif",
                      letterSpacing: isUser ? '0.01em' : '0.015em',
                      color: getAgentColor(msg.agent),
                      opacity: isUser ? 0.85 : 0.9,
                      transition: 'color 0.3s ease, opacity 0.3s ease',
                    }}
                  >
                    {msg.text}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>
    </div>
  );
});

ChatPanel.displayName = 'ChatPanel';

export default ChatPanel;
