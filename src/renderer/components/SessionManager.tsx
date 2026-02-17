import type * as React from 'react';
import { useCallback, useEffect, useState } from 'react';
import type { Session } from '../types';

const API_BASE = 'http://127.0.0.1:8000';

interface SessionManagerProps {
  currentSessionId: string;
  onSessionLoaded: (sessionId: string) => void;
  onNewSession: (sessionId: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

const SessionManager: React.FC<SessionManagerProps> = ({
  currentSessionId,
  onSessionLoaded,
  onNewSession,
  isOpen,
  onClose,
}) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const response = await fetch(`${API_BASE}/api/sessions`);
      if (response.ok) {
        const data = await response.json();
        setSessions(Array.isArray(data) ? data : []);
      } else {
        console.error('[SessionManager] Server returned', response.status);
        setFetchError('Failed to load sessions');
      }
    } catch (err) {
      console.error('[SessionManager] Failed to fetch sessions:', err);
      setFetchError('Cannot reach server');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      void fetchSessions();
    }
  }, [isOpen, fetchSessions]);

  const handleNewSession = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/session/reset`, { method: 'POST' });
      if (response.ok) {
        const result = await response.json();
        if (result.session_id) {
          onNewSession(result.session_id);
          void fetchSessions();
        }
      }
    } catch (err) {
      console.error('Failed to reset session:', err);
    }
  };

  const handleRestoreSession = async (sessionId: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/sessions/restore`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId }),
      });
      if (response.ok) {
        onSessionLoaded(sessionId);
        onClose();
      }
    } catch (err) {
      console.error('Failed to restore session:', err);
    }
  };

  // Logic for the drawer UI would go here if we were to move the whole JSX
  // But for now, we'll keep the UI in App.tsx and just move the logic
  // and pass sessions back if needed, OR we move the whole Sidebar here.
  // Re-evaluating: Moving the whole "Session History Sidebar Overlay" is best.

  if (!isOpen) return null;

  return (
    <div
      className="absolute inset-0 z-50 backdrop-blur-xl border-r border-[#00e5ff]/20 animate-slide-in"
      style={{ backgroundColor: '#000000' }}
    >
      <div className="p-6 h-full flex flex-col">
        <div className="flex items-center justify-between mb-8">
          <h2 className="text-[10px] tracking-[0.4em] uppercase font-bold text-[#00e5ff] drop-shadow-[0_0_5px_rgba(0,229,255,0.5)]">
            Session History
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                void handleNewSession();
              }}
              className="group flex items-center justify-center w-8 h-8 rounded-sm border"
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.6)',
                borderColor: 'rgba(0, 229, 255, 0.4)',
              }}
              title="New Session"
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#00e5ff"
                strokeWidth="3"
              >
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
            </button>
            <button
              onClick={onClose}
              className="group flex items-center justify-center w-8 h-8 rounded-sm border"
              style={{
                backgroundColor: 'rgba(0, 0, 0, 0.6)',
                borderColor: 'rgba(0, 229, 255, 0.4)',
              }}
            >
              <svg
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="#00e5ff"
                strokeWidth="3"
              >
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto pr-2">
          {isLoading ? (
            <div
              className="flex items-center justify-center mt-20"
              style={{
                fontSize: '8px',
                color: 'rgba(0, 229, 255, 0.4)',
                letterSpacing: '0.3em',
                textTransform: 'uppercase',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              Loading sessions...
            </div>
          ) : fetchError ? (
            <div
              className="text-center mt-20"
              style={{
                fontSize: '8px',
                color: 'rgba(255, 77, 77, 0.6)',
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              {fetchError}
            </div>
          ) : sessions.length === 0 ? (
            <div
              className="text-center mt-20"
              style={{
                fontSize: '8px',
                color: 'rgba(0, 229, 255, 0.4)',
                letterSpacing: '0.3em',
                textTransform: 'uppercase',
                fontFamily: "'JetBrains Mono', monospace",
              }}
            >
              No previous sessions found
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {sessions.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    void handleRestoreSession(s.id);
                  }}
                  className={`session-item p-4 border text-left rounded-sm transition-all ${
                    s.id === currentSessionId
                      ? 'border-[#00e5ff] bg-[#00e5ff]/5'
                      : 'border-[#00e5ff]/20 bg-black/40'
                  }`}
                >
                  <div
                    style={{
                      fontSize: '9px',
                      letterSpacing: '0.1em',
                      textTransform: 'uppercase',
                      color: '#00e5ff',
                      marginBottom: '4px',
                      fontFamily: "'Outfit', sans-serif",
                    }}
                  >
                    {s.theme || 'Untitled Session'}
                  </div>
                  <div
                    style={{
                      fontSize: '7px',
                      letterSpacing: '0.15em',
                      textTransform: 'uppercase',
                      color: 'rgba(0, 229, 255, 0.4)',
                      fontFamily: "'JetBrains Mono', monospace",
                    }}
                  >
                    ID: {s.id} • {new Date(s.saved_at).toLocaleString()}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SessionManager;
