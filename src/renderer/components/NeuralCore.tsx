/**
 * NeuralCore - Central Orbital Visualization
 * Gear Mechanism Edition — Reducer/Gearbox viewed from shaft side
 * Trinity agent spheres surrounded by rotating gears
 */

import type React from 'react';
import { useEffect, useRef, useState } from 'react';

type AgentName = 'ATLAS' | 'TETYANA' | 'GRISHA' | 'SYSTEM' | 'USER';
type SystemState =
  | 'IDLE'
  | 'PLANNING'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'ERROR'
  | 'CHAT'
  | 'PROCESSING'
  | 'PAUSED';

interface NeuralCoreProps {
  state: SystemState;
  activeAgent: AgentName;
  minimized?: boolean;
}

/**
 * Generate SVG path for a gear with given parameters.
 * Creates a gear shape centered at origin.
 */
const generateGearPath = (
  innerRadius: number,
  outerRadius: number,
  teeth: number,
): string => {
  const points: string[] = [];
  const toothAngle = (2 * Math.PI) / teeth;
  const toothWidth = 0.35; // fraction of tooth angle for the top

  for (let i = 0; i < teeth; i++) {
    const startAngle = i * toothAngle;
    // Inner arc start
    const a1 = startAngle;
    // Tooth rise
    const a2 = startAngle + toothAngle * (0.5 - toothWidth / 2);
    // Tooth top start
    const a3 = startAngle + toothAngle * (0.5 - toothWidth / 2);
    // Tooth top end
    const a4 = startAngle + toothAngle * (0.5 + toothWidth / 2);
    // Tooth fall
    const a5 = startAngle + toothAngle * (0.5 + toothWidth / 2);
    // Inner arc end
    const a6 = (i + 1) * toothAngle;

    if (i === 0) {
      points.push(`M ${innerRadius * Math.cos(a1)} ${innerRadius * Math.sin(a1)}`);
    }

    // Inner arc to tooth start
    points.push(`A ${innerRadius} ${innerRadius} 0 0 1 ${innerRadius * Math.cos(a2)} ${innerRadius * Math.sin(a2)}`);
    // Rise to outer
    points.push(`L ${outerRadius * Math.cos(a3)} ${outerRadius * Math.sin(a3)}`);
    // Outer arc (tooth top)
    points.push(`A ${outerRadius} ${outerRadius} 0 0 1 ${outerRadius * Math.cos(a4)} ${outerRadius * Math.sin(a4)}`);
    // Fall to inner
    points.push(`L ${innerRadius * Math.cos(a5)} ${innerRadius * Math.sin(a5)}`);
    // Inner arc to next tooth
    points.push(`A ${innerRadius} ${innerRadius} 0 0 1 ${innerRadius * Math.cos(a6)} ${innerRadius * Math.sin(a6)}`);
  }

  points.push('Z');
  return points.join(' ');
};

const NeuralCore: React.FC<NeuralCoreProps> = ({ state, activeAgent, minimized = false }) => {
  const [prevState, setPrevState] = useState<SystemState>(state);
  const [pulseKey, setPulseKey] = useState(0);
  const rippleRef = useRef<SVGCircleElement>(null);

  // Detect state transitions for pulse/ripple effects
  useEffect(() => {
    if (state !== prevState) {
      setPrevState(state);
      setPulseKey((k) => k + 1);
    }
  }, [state, prevState]);

  // --- DYNAMIC CORE COLOR ---
  const getStateColor = (): string => {
    const isWorking = !['IDLE', 'COMPLETED', 'ERROR'].includes(state);
    if (isWorking) {
      switch (activeAgent) {
        case 'ATLAS':
          return 'var(--atlas-blue)';
        case 'TETYANA':
          return 'var(--tetyana-green)';
        case 'GRISHA':
          return 'var(--grisha-orange)';
        default:
          break;
      }
    }

    switch (state) {
      case 'IDLE':
      case 'COMPLETED':
        return '#00A3FF';
      case 'PLANNING':
      case 'CHAT':
      case 'PROCESSING':
        return 'var(--atlas-blue)';
      case 'EXECUTING':
        return 'var(--tetyana-green)';
      case 'VERIFYING':
        return 'var(--grisha-orange)';
      case 'ERROR':
        return 'var(--state-error, #FF4D4D)';
      default:
        return 'var(--atlas-blue)';
    }
  };

  const getStateLabel = () => {
    switch (state) {
      case 'IDLE':
        return 'SYSTEM_ONLINE';
      case 'COMPLETED':
        return 'TASK_COMPLETED';
      case 'PLANNING':
        return 'ANALYZING_REQUEST';
      case 'PROCESSING':
        return 'PROCESSING_DATA';
      case 'CHAT':
        return 'NEURAL_DIALOGUE';
      case 'EXECUTING':
        return 'EXECUTING_TASK';
      case 'VERIFYING':
        return 'VERIFYING_RESULTS';
      case 'ERROR':
        return 'SYSTEM_ERROR';
      default:
        return 'CORE_ACTIVE';
    }
  };

  // Dynamic speed multiplier based on state
  const isActive = !['IDLE', 'COMPLETED'].includes(state);
  const isError = state === 'ERROR';
  const speedFactor = isActive ? (isError ? 0.5 : 2.0) : 1.0;

  // Generate gear paths
  const outerGearPath = generateGearPath(280, 310, 28);
  const middleGearPath = generateGearPath(205, 230, 20);
  const innerGearPath = generateGearPath(130, 150, 14);

  const containerStyle = {
    color: getStateColor(),
  } as React.CSSProperties;

  return (
    <div
      className={`neural-core transition-colors-slow ${minimized ? 'minimized' : ''}`}
      style={containerStyle}
    >
      <svg viewBox="-400 -400 800 800" className="orbital-svg">
        <defs>
          <filter id="glow-core">
            <feGaussianBlur stdDeviation="5" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="glow-strong">
            <feGaussianBlur stdDeviation="10" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="glow-gear">
            <feGaussianBlur stdDeviation="3" result="gearBlur" />
            <feMerge>
              <feMergeNode in="gearBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="grad-core" cx="0.5" cy="0.5" r="0.5">
            <stop offset="0%" stopColor="currentColor" stopOpacity="0.6" />
            <stop offset="60%" stopColor="currentColor" stopOpacity="0.2" />
            <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* --- RIPPLE EFFECT on state change --- */}
        <circle
          key={`ripple-${pulseKey}`}
          ref={rippleRef}
          r="30"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className="state-ripple"
        />

        {/* ═══════════════════════════════════════════════
            GEAR MECHANISM — Reducer viewed from shaft side
            Three concentric gears rotating in alternating directions
            ═══════════════════════════════════════════════ */}

        {/* --- OUTER GEAR (28 teeth) — Slow CW rotation --- */}
        <g
          style={{
            animation: `rotate-cw ${40 / speedFactor}s linear infinite`,
            transformOrigin: 'center',
          }}
          filter="url(#glow-gear)"
        >
          <path
            d={outerGearPath}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            opacity={isActive ? 0.35 : 0.15}
          />
          {/* Inner ring of the outer gear (hub) */}
          <circle
            r="275"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            opacity="0.08"
          />
          {/* Spoke markings every 90° */}
          <line x1="275" y1="0" x2="310" y2="0" stroke="currentColor" strokeWidth="0.5" opacity="0.12" />
          <line x1="-275" y1="0" x2="-310" y2="0" stroke="currentColor" strokeWidth="0.5" opacity="0.12" />
          <line x1="0" y1="275" x2="0" y2="310" stroke="currentColor" strokeWidth="0.5" opacity="0.12" />
          <line x1="0" y1="-275" x2="0" y2="-310" stroke="currentColor" strokeWidth="0.5" opacity="0.12" />
        </g>

        {/* --- MIDDLE GEAR (20 teeth) — Medium CCW rotation --- */}
        <g
          style={{
            animation: `rotate-ccw ${22 / speedFactor}s linear infinite`,
            transformOrigin: 'center',
          }}
          filter="url(#glow-gear)"
        >
          <path
            d={middleGearPath}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            opacity={isActive ? 0.45 : 0.2}
          />
          {/* Inner ring of middle gear */}
          <circle
            r="200"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            opacity="0.1"
          />
          {/* Accent dots on gear face */}
          <circle cx="215" cy="0" r="2" fill="currentColor" opacity={isActive ? 0.5 : 0.15} />
          <circle cx="-215" cy="0" r="2" fill="currentColor" opacity={isActive ? 0.5 : 0.15} />
          <circle cx="0" cy="215" r="2" fill="currentColor" opacity={isActive ? 0.5 : 0.15} />
          <circle cx="0" cy="-215" r="2" fill="currentColor" opacity={isActive ? 0.5 : 0.15} />
          <circle cx="152" cy="152" r="1.5" fill="currentColor" opacity={isActive ? 0.4 : 0.1} />
          <circle cx="-152" cy="152" r="1.5" fill="currentColor" opacity={isActive ? 0.4 : 0.1} />
          <circle cx="152" cy="-152" r="1.5" fill="currentColor" opacity={isActive ? 0.4 : 0.1} />
          <circle cx="-152" cy="-152" r="1.5" fill="currentColor" opacity={isActive ? 0.4 : 0.1} />
        </g>

        {/* --- INNER GEAR (14 teeth) — Fast CW rotation --- */}
        <g
          style={{
            animation: `rotate-cw ${12 / speedFactor}s linear infinite`,
            transformOrigin: 'center',
          }}
          filter="url(#glow-gear)"
        >
          <path
            d={innerGearPath}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            opacity={isActive ? 0.55 : 0.25}
          />
          {/* Hub ring */}
          <circle
            r="125"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.8"
            opacity="0.12"
          />
          {/* Energy pulse on inner gear when active */}
          {isActive && (
            <circle
              r="140"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeDasharray="15 800"
              opacity="0.6"
            >
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0"
                to="360"
                dur="2s"
                repeatCount="indefinite"
              />
            </circle>
          )}
        </g>

        {/* --- Thin accent ring between gears --- */}
        <circle r="260" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.06" />
        <circle r="170" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.06" />

        {/* --- CENTRAL CORE --- */}
        <g className="core-group" filter={isActive ? 'url(#glow-strong)' : 'url(#glow-core)'}>
          {/* Multi-layered pulse */}
          <circle r="60" fill="url(#grad-core)" className="animate-pulse" />
          {/* Breathing ring */}
          <circle r="45" fill="none" stroke="currentColor" strokeWidth="0.3" opacity="0.15">
            <animate attributeName="r" values="42;48;42" dur="4s" repeatCount="indefinite" />
            <animate
              attributeName="opacity"
              values="0.1;0.25;0.1"
              dur="4s"
              repeatCount="indefinite"
            />
          </circle>

          <circle
            r="35"
            fill="none"
            stroke="currentColor"
            strokeWidth="0.5"
            className="animate-pulse-slow"
          />
          <circle r="15" fill="currentColor" className="animate-pulse-fast" />
          <circle r="5" fill="#fff" opacity="0.9" />

          {/* Core Crosshair */}
          <line
            x1="-20"
            y1="0"
            x2="20"
            y2="0"
            stroke="currentColor"
            strokeWidth="0.5"
            opacity="0.5"
          />
          <line
            x1="0"
            y1="-20"
            x2="0"
            y2="20"
            stroke="currentColor"
            strokeWidth="0.5"
            opacity="0.5"
          />
        </g>

        {/* --- AGENT NODES --- */}
        {/* ATLAS */}
        <g>
          <line
            x1="0"
            y1="-60"
            x2="0"
            y2="-170"
            stroke="var(--atlas-blue)"
            strokeWidth="0.5"
            opacity={activeAgent === 'ATLAS' ? 0.6 : 0.1}
          />
          {/* Data stream particles on active link */}
          {activeAgent === 'ATLAS' && (
            <circle r="2" fill="var(--atlas-blue)" opacity="0.8">
              <animateMotion dur="1.5s" repeatCount="indefinite" path="M0,-65 L0,-175" />
              <animate
                attributeName="opacity"
                values="0.9;0.2;0.9"
                dur="1.5s"
                repeatCount="indefinite"
              />
            </circle>
          )}
          <circle
            cx="0"
            cy="-180"
            r={activeAgent === 'ATLAS' ? 10 : 4}
            fill="var(--atlas-blue)"
            className={activeAgent === 'ATLAS' ? 'animate-pulse' : ''}
          />
          {activeAgent === 'ATLAS' && (
            <circle
              cx="0"
              cy="-180"
              r="16"
              fill="none"
              stroke="var(--atlas-blue)"
              strokeWidth="0.5"
              opacity="0.3"
            >
              <animate attributeName="r" values="14;20;14" dur="2s" repeatCount="indefinite" />
              <animate
                attributeName="opacity"
                values="0.3;0.05;0.3"
                dur="2s"
                repeatCount="indefinite"
              />
            </circle>
          )}
          <text
            x="0"
            y="-205"
            textAnchor="middle"
            fill="var(--atlas-blue)"
            fontSize="9"
            fontWeight="bold"
            letterSpacing="3"
            opacity={activeAgent === 'ATLAS' ? 1 : 0.3}
            style={{ fontFamily: "'JetBrains Mono', monospace" }}
          >
            ATLAS
          </text>
        </g>

        {/* GRISHA */}
        <g transform="rotate(120)">
          <line
            x1="0"
            y1="-60"
            x2="0"
            y2="-170"
            stroke="var(--grisha-orange)"
            strokeWidth="0.5"
            opacity={activeAgent === 'GRISHA' ? 0.6 : 0.1}
          />
          {activeAgent === 'GRISHA' && (
            <circle r="2" fill="var(--grisha-orange)" opacity="0.8">
              <animateMotion dur="1.5s" repeatCount="indefinite" path="M0,-65 L0,-175" />
              <animate
                attributeName="opacity"
                values="0.9;0.2;0.9"
                dur="1.5s"
                repeatCount="indefinite"
              />
            </circle>
          )}
          <g transform="translate(0, -180)">
            <circle
              r={activeAgent === 'GRISHA' ? 10 : 4}
              fill="var(--grisha-orange)"
              transform="rotate(-120)"
              className={activeAgent === 'GRISHA' ? 'animate-pulse' : ''}
            />
            {activeAgent === 'GRISHA' && (
              <circle
                r="16"
                fill="none"
                stroke="var(--grisha-orange)"
                strokeWidth="0.5"
                opacity="0.3"
                transform="rotate(-120)"
              >
                <animate attributeName="r" values="14;20;14" dur="2s" repeatCount="indefinite" />
                <animate
                  attributeName="opacity"
                  values="0.3;0.05;0.3"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            <text
              y="25"
              transform="rotate(-120)"
              textAnchor="middle"
              fill="var(--grisha-orange)"
              fontSize="9"
              fontWeight="bold"
              letterSpacing="3"
              opacity={activeAgent === 'GRISHA' ? 1 : 0.3}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              GRISHA
            </text>
          </g>
        </g>

        {/* TETYANA */}
        <g transform="rotate(240)">
          <line
            x1="0"
            y1="-60"
            x2="0"
            y2="-170"
            stroke="var(--tetyana-green)"
            strokeWidth="0.5"
            opacity={activeAgent === 'TETYANA' ? 0.6 : 0.1}
          />
          {activeAgent === 'TETYANA' && (
            <circle r="2" fill="var(--tetyana-green)" opacity="0.8">
              <animateMotion dur="1.5s" repeatCount="indefinite" path="M0,-65 L0,-175" />
              <animate
                attributeName="opacity"
                values="0.9;0.2;0.9"
                dur="1.5s"
                repeatCount="indefinite"
              />
            </circle>
          )}
          <g transform="translate(0, -180)">
            <circle
              r={activeAgent === 'TETYANA' ? 10 : 4}
              fill="var(--tetyana-green)"
              transform="rotate(-240)"
              className={activeAgent === 'TETYANA' ? 'animate-pulse' : ''}
            />
            {activeAgent === 'TETYANA' && (
              <circle
                r="16"
                fill="none"
                stroke="var(--tetyana-green)"
                strokeWidth="0.5"
                opacity="0.3"
                transform="rotate(-240)"
              >
                <animate attributeName="r" values="14;20;14" dur="2s" repeatCount="indefinite" />
                <animate
                  attributeName="opacity"
                  values="0.3;0.05;0.3"
                  dur="2s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            <text
              y="25"
              transform="rotate(-240)"
              textAnchor="middle"
              fill="var(--tetyana-green)"
              fontSize="9"
              fontWeight="bold"
              letterSpacing="3"
              opacity={activeAgent === 'TETYANA' ? 1 : 0.3}
              style={{ fontFamily: "'JetBrains Mono', monospace" }}
            >
              TETYANA
            </text>
          </g>
        </g>
      </svg>

      {/* --- RECTANGULAR STATUS INDICATOR --- */}
      {!minimized && (
        <div className="status-indicator">
          <div className="status-glow" />
          <div className="status-box">
            <span className="status-text">{getStateLabel()}</span>
          </div>
        </div>
      )}

      <style>{`
        .neural-core {
          position: relative;
          width: 100%;
          height: 100%;
          display: flex;
          align-items: center;
          justify-content: center;
          overflow: visible;
          transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .neural-core.minimized {
          opacity: 0.15;
          transform: scale(0.6);
          pointer-events: none;
          filter: blur(2px);
        }
        .orbital-svg {
          width: 480px;
          height: 480px;
          max-width: 90%;
          max-height: 90%;
        }
        .status-indicator {
          position: absolute;
          bottom: 12%;
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .status-box {
          position: relative;
          padding: 10px 30px;
          background: rgba(0, 0, 0, 0.95);
          border: 2px solid currentColor;
          box-shadow: 0 0 20px currentColor, inset 0 0 8px currentColor;
          z-index: 2;
          transition: all 0.5s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .status-glow {
          position: absolute;
          width: 120%;
          height: 140%;
          background: currentColor;
          filter: blur(30px);
          opacity: 0.45;
          z-index: 1;
          animation: breathe-glow 3s ease-in-out infinite;
        }
        .status-text {
          font-family: 'JetBrains Mono', monospace;
          font-size: 13px;
          font-weight: 700;
          letter-spacing: 3px;
          color: currentColor;
          text-transform: uppercase;
          text-shadow: 0 0 10px currentColor, 0 0 20px currentColor;
        }

        /* Breathing glow for status */
        @keyframes breathe-glow {
          0%, 100% { opacity: 0.35; filter: blur(30px); }
          50% { opacity: 0.55; filter: blur(35px); }
        }

        /* Ripple effect on state change */
        @keyframes state-ripple {
          0% { r: 30; opacity: 0.8; stroke-width: 3; }
          100% { r: 350; opacity: 0; stroke-width: 0.5; }
        }
        .state-ripple {
          animation: state-ripple 1.2s cubic-bezier(0, 0.5, 0.3, 1) forwards;
        }
      `}</style>
    </div>
  );
};

export default NeuralCore;
