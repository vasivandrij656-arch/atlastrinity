/**
 * AtlasTrinity - Main App Component
 * Premium Design System Integration
 */

import type * as React from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import AgentStatus from './components/AgentStatus.tsx';
import ChatPanel from './components/ChatPanel.tsx';
import CommandLine from './components/CommandLine.tsx';
import ExecutionLog from './components/ExecutionLog.tsx';
import MapView from './components/MapView';
import NeuralCore from './components/NeuralCore';
import SessionManager from './components/SessionManager.tsx';
import { useBrainApi } from './hooks/useBrainApi';

const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || '';

const App: React.FC = () => {
  const {
    systemState,
    activeAgent,
    logs,
    chatHistory,
    metrics,
    isConnected,
    setIsConnected,
    mapData,
    setMapData,
    currentSessionId,
    pollState,
    handleCommand,
    handleNewSession,
    handleRestoreSession,
    handlePause,
    handleResume,
    currentTask,
    activeMode,
    voiceEnabled,
    handleToggleVoice,
  } = useBrainApi();

  const [isVoiceEnabled, setIsVoiceEnabled] = useState(true);

  // Sync local voice state with backend
  useEffect(() => {
    if (voiceEnabled !== isVoiceEnabled) {
      setIsVoiceEnabled(voiceEnabled);
    }
  }, [voiceEnabled, isVoiceEnabled]);
  const [viewMode, setViewMode] = useState<'NEURAL' | 'MAP'>('NEURAL');
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  // Command dock auto-hide state
  const [isDockVisible, setIsDockVisible] = useState(true);
  const [isInputFocused, setIsInputFocused] = useState(false);
  const showTimerRef = useRef<NodeJS.Timeout | null>(null);
  const hideTimerRef = useRef<NodeJS.Timeout | null>(null);

  const DOCK_DELAY_MS = 300;

  const handleHoverZoneEnter = useCallback(() => {
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
    if (!(isDockVisible || showTimerRef.current)) {
      showTimerRef.current = setTimeout(() => {
        setIsDockVisible(true);
        showTimerRef.current = null;
      }, DOCK_DELAY_MS);
    }
  }, [isDockVisible]);

  const handleHoverZoneLeave = useCallback(() => {
    if (showTimerRef.current) {
      clearTimeout(showTimerRef.current);
      showTimerRef.current = null;
    }
    if (isDockVisible && !hideTimerRef.current) {
      hideTimerRef.current = setTimeout(() => {
        setIsDockVisible(false);
        hideTimerRef.current = null;
      }, DOCK_DELAY_MS);
    }
  }, [isDockVisible]);

  useEffect(() => {
    if (isInputFocused) {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current);
        hideTimerRef.current = null;
      }
      setIsDockVisible(true);
    }
  }, [isInputFocused]);


  useEffect(() => {
    return () => {
      if (showTimerRef.current) clearTimeout(showTimerRef.current);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, []);

  const loaderRef = useRef<HTMLElement>(null);
  useEffect(() => {
    if (loaderRef.current && GOOGLE_MAPS_API_KEY) {
      loaderRef.current.setAttribute('key', GOOGLE_MAPS_API_KEY);
    }
  }, []);

  const isTourActive = Boolean(mapData.agentView);
  const pollInterval = isTourActive ? 1000 : 5000;

  // Handle backend-driven map display triggers (showMap: True)
  useEffect(() => {
    if (mapData.showMap && viewMode !== 'MAP') {
      console.log('[APP] Backend requested MAP view — auto-switching');
      setViewMode('MAP');
    }
  }, [mapData.showMap, viewMode]);

  // Auto-switch to MAP view when a tour starts (agentView appears)
  useEffect(() => {
    if (isTourActive && viewMode !== 'MAP') {
      console.log('[APP] Tour detected — auto-switching to MAP view');
      setViewMode('MAP');
    }
  }, [isTourActive, viewMode]);

  useEffect(() => {
    let mounted = true;
    let interval: NodeJS.Timeout;

    const onBrainReady = () => {
      if (!mounted) return;
      console.log('[BRAIN] Backend connected. Starting synchronization.');
      setIsConnected(true);
      interval = setInterval(() => {
        pollState(viewMode).catch(console.error);
      }, pollInterval);
    };

    if (window.__BRAIN_READY__) {
      onBrainReady();
    } else {
      window.addEventListener('brain-ready', onBrainReady, { once: true });
    }

    return () => {
      mounted = false;
      window.removeEventListener('brain-ready', onBrainReady);
      if (interval) clearInterval(interval);
    };
  }, [pollState, pollInterval, viewMode, setIsConnected]);

  const chatMessages = useMemo(() => {
    return chatHistory.map((m, idx) => {
      // Ensure we have a Date object
      const ts = m.timestamp instanceof Date ? m.timestamp : new Date(m.timestamp);
      const timeMs = Number.isNaN(ts.getTime()) ? Date.now() : ts.getTime();

      return {
        id: `chat-${timeMs}-${idx}`,
        agent: m.agent,
        text: m.text,
        timestamp: ts,
        type: m.type,
      };
    });
  }, [chatHistory]);

  return (
    <div className="app-container scanlines" role="application">
      {/* Top Level Google Maps API Loader - Prevents 429 errors by staying mounted */}
      {GOOGLE_MAPS_API_KEY && (
        <div style={{ display: 'none' }}>
          <gmpx-api-loader
            // biome-ignore lint/suspicious/noExplicitAny: custom element ref needs any cast in some react versions
            ref={loaderRef as any}
            api-key={GOOGLE_MAPS_API_KEY}
            solution-channel="GMP_CDN_extended_v0.6.11"
            version="beta"
          ></gmpx-api-loader>
        </div>
      )}
      {/* Pulsing Borders */}
      <div className="pulsing-border top"></div>
      <div className="pulsing-border bottom"></div>
      <div className="pulsing-border left"></div>
      <div className="pulsing-border right"></div>

      {/* Starting Overlay */}
      {!isConnected && systemState === 'IDLE' && (
        <div className="fixed inset-0 z-[20000] flex items-center justify-center bg-black/80 backdrop-blur-md">
          <div className="flex flex-col items-center gap-6">
            <div className="w-16 h-16 border-t-2 border-r-2 border-[#00f2ff] rounded-full animate-spin"></div>
            <div className="flex flex-col items-center gap-2">
              <div className="text-[10px] tracking-[0.5em] uppercase text-[#00f2ff]/60 animate-pulse">
                Waiting for neural link...
              </div>
              <div className="text-[8px] tracking-[0.2em] uppercase text-[#00f2ff]/30 font-mono">
                Searching for Brain Core...
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Global Title Bar Controls (Positioned exactly near traffic lights) */}
      <div
        className="fixed flex items-center gap-2 pointer-events-auto"
        style={
          {
            top: '12px',
            left: '78px',
            WebkitAppRegion: 'no-drag',
            zIndex: 10001,
          } as React.CSSProperties
        }
      >
        <button
          onClick={() => {
            console.log('History clicked');
            setIsHistoryOpen(!isHistoryOpen);
          }}
          className={`titlebar-btn group ${isHistoryOpen ? 'active' : ''}`}
          title="Session History"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polyline points="12 8 12 12 14 14"></polyline>
            <path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5"></path>
          </svg>
        </button>
        <button
          onClick={() => {
            if (systemState === 'PAUSED') {
              void handleResume();
            } else {
              void handlePause();
            }
          }}
          className={`titlebar-btn group ${systemState === 'PAUSED' ? 'active' : ''}`}
          title={systemState === 'PAUSED' ? 'Resume Session' : 'Pause Session'}
          style={{
            color: systemState === 'PAUSED' ? '#00FF41' : 'rgba(0, 163, 255, 0.6)',
          }}
        >
          {systemState === 'PAUSED' ? (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
              <path d="M5 3l14 9-14 9V3z" />
            </svg>
          ) : (
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
            >
              <line x1="10" y1="4" x2="10" y2="20"></line>
              <line x1="14" y1="4" x2="14" y2="20"></line>
            </svg>
          )}
        </button>
        <button
          onClick={() => {
            console.log('New Session clicked');
            void handleNewSession();
          }}
          className="titlebar-btn group"
          title="New Session"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
        </button>
        <button
          onClick={() => {
            const nextMode = viewMode === 'NEURAL' ? 'MAP' : 'NEURAL';
            setViewMode(nextMode);
            // If switching to MAP and no specific feed is active, default to INTERACTIVE manual control
            if (nextMode === 'MAP' && !mapData.url && mapData.type !== 'INTERACTIVE') {
              setMapData({
                type: 'INTERACTIVE',
                location: 'INTERACTIVE_FEED',
              });
            }
          }}
          className={`titlebar-btn group ${viewMode === 'MAP' ? 'active' : ''}`}
          title="Toggle Map/Neural Core"
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"></polygon>
            <line x1="8" y1="2" x2="8" y2="18"></line>
            <line x1="16" y1="6" x2="16" y2="22"></line>
          </svg>
        </button>
      </div>

      {/* Left Panel - Execution Log */}
      <aside className="panel glass-panel left-panel relative">
        <ExecutionLog logs={logs} />

        {/* Session History Sidebar Overlay */}
        <SessionManager
          currentSessionId={currentSessionId}
          isOpen={isHistoryOpen}
          onClose={() => setIsHistoryOpen(false)}
          onNewSession={() => {
            void handleNewSession();
          }}
          onSessionLoaded={(id) => {
            void handleRestoreSession(id);
          }}
        />
      </aside>

      {/* Center Panel: Neural Core / Map View */}
      <main
        className="panel center-panel relative overflow-hidden"
        style={{ pointerEvents: viewMode === 'MAP' ? 'none' : 'auto' }}
      >
        {/* Neural Core is always present, but minimized when map is active */}
        <NeuralCore state={systemState} activeAgent={activeAgent} minimized={viewMode === 'MAP'} />
      </main>

      {/* Right Panel: Chat Panel */}
      <aside className="panel glass-panel right-panel">
        <ChatPanel messages={chatMessages} />
      </aside>

      {/* Map View - Fixed overlay above all panels */}
      {viewMode === 'MAP' && (
        <div
          className="fixed z-[1000] animate-fade-in"
          style={{
            top: '32px',
            bottom: '24px',
            left: '129px' /* 2/3 overlap on left panel (388px - 388*2/3) */,
            right: '129px' /* 2/3 overlap on right panel */,
          }}
        >
          <MapView
            imageUrl={mapData.url}
            type={mapData.type}
            location={mapData.location}
            agentView={mapData.agentView}
            distanceInfo={mapData.distanceInfo}
            onClose={() => setViewMode('NEURAL')}
          />
        </div>
      )}

      {/* Hover zone for auto-revealing command dock */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: Hover zone for dock */}
      <div
        className="command-dock-hover-zone"
        onMouseEnter={handleHoverZoneEnter}
        onMouseLeave={handleHoverZoneLeave}
      />

      {/* biome-ignore lint/a11y/noStaticElementInteractions: Command dock container */}
      <div
        className={`command-dock command-dock-floating ${isDockVisible ? 'visible' : 'hidden'}`}
        onMouseEnter={handleHoverZoneEnter}
        onMouseLeave={handleHoverZoneLeave}
      >
        <CommandLine
          onCommand={(cmd, files) => {
            void handleCommand(cmd, files);
          }}
          isVoiceEnabled={isVoiceEnabled}
          onToggleVoice={() => {
            void handleToggleVoice(!isVoiceEnabled);
          }}
          isProcessing={false}
          onFocusChange={setIsInputFocused}
        />
      </div>

      {/* Bottom Status Bar - Integrated with AgentStatus */}
      <div className="status-bar !p-0 !bg-transparent !border-none">
        <AgentStatus
          activeAgent={activeAgent}
          systemState={systemState}
          currentTask={currentTask}
          activeMode={activeMode}
          isConnected={isConnected}
          metrics={metrics}
        />
      </div>
    </div>
  );
};

export default App;

// Add global declarations for Google Maps Web Components to satisfy TypeScript
declare global {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      'gmp-map': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        center?: string;
        zoom?: string;
        'rendering-type'?: string;
      };

      'gmpx-api-loader': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        key?: string;
        'solution-channel'?: string;
        version?: string;
      };

      'gmpx-place-picker': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      > & {
        placeholder?: string;
      };

      'gmp-advanced-marker': React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >;
    }
  }

  interface Window {
    __BRAIN_READY__?: boolean;
  }
}
