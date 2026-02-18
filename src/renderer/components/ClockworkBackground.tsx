/**
 * ClockworkBackground — Static interlocking gear mechanism
 * Renders behind agent layers as a premium "open watch" aesthetic.
 * Each gear meshes with neighbors; colors follow agent theme palette.
 */

import type React from 'react';

/* ─── Gear path generator ─── */
const gearPath = (innerR: number, outerR: number, teeth: number): string => {
  const pts: string[] = [];
  const ta = (2 * Math.PI) / teeth;
  const tw = 0.35;

  for (let i = 0; i < teeth; i++) {
    const s = i * ta;
    const a1 = s;
    const a2 = s + ta * (0.5 - tw / 2);
    const a3 = a2;
    const a4 = s + ta * (0.5 + tw / 2);
    const a5 = a4;
    const a6 = (i + 1) * ta;

    if (i === 0) pts.push(`M ${innerR * Math.cos(a1)} ${innerR * Math.sin(a1)}`);
    pts.push(`A ${innerR} ${innerR} 0 0 1 ${innerR * Math.cos(a2)} ${innerR * Math.sin(a2)}`);
    pts.push(`L ${outerR * Math.cos(a3)} ${outerR * Math.sin(a3)}`);
    pts.push(`A ${outerR} ${outerR} 0 0 1 ${outerR * Math.cos(a4)} ${outerR * Math.sin(a4)}`);
    pts.push(`L ${innerR * Math.cos(a5)} ${innerR * Math.sin(a5)}`);
    pts.push(`A ${innerR} ${innerR} 0 0 1 ${innerR * Math.cos(a6)} ${innerR * Math.sin(a6)}`);
  }
  pts.push('Z');
  return pts.join(' ');
};

/* ─── Gear definition type ─── */
interface GearDef {
  cx: number;
  cy: number;
  innerR: number;
  outerR: number;
  teeth: number;
  color: string;
  opacity: number;
  speed: number; // seconds per revolution
  cw: boolean; // clockwise?
  glowColor: string;
}

/**
 * Gears laid out to interlock — adjacent gears share tangent edges
 * and rotate in opposite directions. Sizes vary to create a complex
 * clockwork aesthetic reminiscent of an open pocket-watch back.
 */
const GEARS: GearDef[] = [
  // ── Large hero gears ──
  {
    cx: -120,
    cy: -80,
    innerR: 80,
    outerR: 100,
    teeth: 24,
    color: 'var(--atlas-blue)',
    opacity: 0.12,
    speed: 60,
    cw: true,
    glowColor: 'rgba(0,163,255,0.25)',
  },
  {
    cx: 80,
    cy: 60,
    innerR: 70,
    outerR: 88,
    teeth: 20,
    color: 'var(--tetyana-green)',
    opacity: 0.1,
    speed: 52,
    cw: false,
    glowColor: 'rgba(0,255,65,0.22)',
  },
  {
    cx: 160,
    cy: -140,
    innerR: 60,
    outerR: 76,
    teeth: 18,
    color: 'var(--grisha-orange)',
    opacity: 0.11,
    speed: 48,
    cw: true,
    glowColor: 'rgba(255,140,0,0.22)',
  },

  // ── Medium gears ──
  {
    cx: -220,
    cy: 70,
    innerR: 50,
    outerR: 64,
    teeth: 16,
    color: 'var(--atlas-blue)',
    opacity: 0.09,
    speed: 40,
    cw: false,
    glowColor: 'rgba(0,163,255,0.18)',
  },
  {
    cx: 0,
    cy: -200,
    innerR: 45,
    outerR: 58,
    teeth: 14,
    color: 'var(--tetyana-green)',
    opacity: 0.1,
    speed: 36,
    cw: true,
    glowColor: 'rgba(0,255,65,0.18)',
  },
  {
    cx: 250,
    cy: 30,
    innerR: 48,
    outerR: 62,
    teeth: 15,
    color: 'var(--grisha-orange)',
    opacity: 0.08,
    speed: 38,
    cw: false,
    glowColor: 'rgba(255,140,0,0.16)',
  },
  {
    cx: -50,
    cy: 190,
    innerR: 55,
    outerR: 70,
    teeth: 16,
    color: 'var(--atlas-blue)',
    opacity: 0.09,
    speed: 44,
    cw: true,
    glowColor: 'rgba(0,163,255,0.18)',
  },

  // ── Small accent gears ──
  {
    cx: -280,
    cy: -170,
    innerR: 28,
    outerR: 38,
    teeth: 10,
    color: 'var(--grisha-orange)',
    opacity: 0.07,
    speed: 24,
    cw: false,
    glowColor: 'rgba(255,140,0,0.14)',
  },
  {
    cx: 290,
    cy: -60,
    innerR: 25,
    outerR: 34,
    teeth: 9,
    color: 'var(--tetyana-green)',
    opacity: 0.08,
    speed: 22,
    cw: true,
    glowColor: 'rgba(0,255,65,0.14)',
  },
  {
    cx: -160,
    cy: 230,
    innerR: 30,
    outerR: 40,
    teeth: 10,
    color: 'var(--grisha-orange)',
    opacity: 0.07,
    speed: 26,
    cw: true,
    glowColor: 'rgba(255,140,0,0.12)',
  },
  {
    cx: 200,
    cy: 200,
    innerR: 22,
    outerR: 30,
    teeth: 8,
    color: 'var(--atlas-blue)',
    opacity: 0.08,
    speed: 20,
    cw: false,
    glowColor: 'rgba(0,163,255,0.14)',
  },

  // ── Tiny connector gears ──
  {
    cx: -30,
    cy: -110,
    innerR: 18,
    outerR: 26,
    teeth: 8,
    color: 'var(--tetyana-green)',
    opacity: 0.06,
    speed: 16,
    cw: false,
    glowColor: 'rgba(0,255,65,0.10)',
  },
  {
    cx: 140,
    cy: 170,
    innerR: 16,
    outerR: 22,
    teeth: 7,
    color: 'var(--grisha-orange)',
    opacity: 0.06,
    speed: 14,
    cw: true,
    glowColor: 'rgba(255,140,0,0.10)',
  },
  {
    cx: -260,
    cy: -30,
    innerR: 20,
    outerR: 28,
    teeth: 8,
    color: 'var(--atlas-blue)',
    opacity: 0.06,
    speed: 18,
    cw: true,
    glowColor: 'rgba(0,163,255,0.10)',
  },
  {
    cx: 310,
    cy: 170,
    innerR: 18,
    outerR: 25,
    teeth: 7,
    color: 'var(--tetyana-green)',
    opacity: 0.05,
    speed: 15,
    cw: false,
    glowColor: 'rgba(0,255,65,0.08)',
  },
];

const ClockworkBackground: React.FC = () => {
  return (
    <div className="clockwork-bg" aria-hidden="true">
      <svg
        viewBox="-400 -320 800 640"
        preserveAspectRatio="xMidYMid slice"
        className="clockwork-svg"
      >
        <defs>
          {/* Per-gear glow filters */}
          <filter id="cw-glow-blue" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feFlood floodColor="rgba(0,163,255,0.35)" result="fc" />
            <feComposite in="fc" in2="b" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="cw-glow-green" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feFlood floodColor="rgba(0,255,65,0.30)" result="fc" />
            <feComposite in="fc" in2="b" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="cw-glow-orange" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="6" result="b" />
            <feFlood floodColor="rgba(255,140,0,0.30)" result="fc" />
            <feComposite in="fc" in2="b" operator="in" result="glow" />
            <feMerge>
              <feMergeNode in="glow" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          {/* Soft ambient glow behind everything */}
          <filter id="cw-ambient" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="12" />
          </filter>
        </defs>

        {/* Ambient glow circles behind each major gear group */}
        {GEARS.filter((g) => g.outerR >= 60).map((g, i) => (
          <circle
            key={`amb-${i}`}
            cx={g.cx}
            cy={g.cy}
            r={g.outerR * 1.4}
            fill={g.glowColor}
            filter="url(#cw-ambient)"
            className="gear-ambient-glow"
          />
        ))}

        {/* Render all gears */}
        {GEARS.map((g, i) => {
          const filterId = g.color.includes('blue')
            ? 'cw-glow-blue'
            : g.color.includes('green')
              ? 'cw-glow-green'
              : 'cw-glow-orange';

          const path = gearPath(g.innerR, g.outerR, g.teeth);
          const animDir = g.cw ? 'rotate-cw' : 'rotate-ccw';

          return (
            <g key={`gear-${i}`} transform={`translate(${g.cx}, ${g.cy})`}>
              {/* Gear body */}
              <g
                style={{
                  animation: `${animDir} ${g.speed}s linear infinite`,
                  transformOrigin: 'center',
                }}
                filter={`url(#${filterId})`}
              >
                <path
                  d={path}
                  fill="none"
                  stroke={g.color}
                  strokeWidth={g.outerR > 60 ? 1.5 : 1}
                  opacity={g.opacity}
                />
                {/* Hub circle */}
                <circle
                  r={g.innerR * 0.55}
                  fill="none"
                  stroke={g.color}
                  strokeWidth={0.8}
                  opacity={g.opacity * 0.6}
                />
                {/* Center axle */}
                <circle r={g.innerR * 0.15} fill={g.color} opacity={g.opacity * 0.8} />
                {/* Spokes for larger gears */}
                {g.outerR >= 50 && (
                  <>
                    <line
                      x1={0}
                      y1={-g.innerR * 0.55}
                      x2={0}
                      y2={g.innerR * 0.55}
                      stroke={g.color}
                      strokeWidth={0.5}
                      opacity={g.opacity * 0.4}
                    />
                    <line
                      x1={-g.innerR * 0.55}
                      y1={0}
                      x2={g.innerR * 0.55}
                      y2={0}
                      stroke={g.color}
                      strokeWidth={0.5}
                      opacity={g.opacity * 0.4}
                    />
                  </>
                )}
                {/* Diagonal spokes for large gears */}
                {g.outerR >= 70 && (
                  <>
                    <line
                      x1={-g.innerR * 0.39}
                      y1={-g.innerR * 0.39}
                      x2={g.innerR * 0.39}
                      y2={g.innerR * 0.39}
                      stroke={g.color}
                      strokeWidth={0.4}
                      opacity={g.opacity * 0.3}
                    />
                    <line
                      x1={g.innerR * 0.39}
                      y1={-g.innerR * 0.39}
                      x2={-g.innerR * 0.39}
                      y2={g.innerR * 0.39}
                      stroke={g.color}
                      strokeWidth={0.4}
                      opacity={g.opacity * 0.3}
                    />
                  </>
                )}
              </g>
            </g>
          );
        })}

        {/* Decorative connection lines between nearby gears */}
        <g opacity="0.03" stroke="var(--atlas-blue)" strokeWidth="0.5" strokeDasharray="4 6">
          <line x1="-120" y1="-80" x2="-30" y2="-110" />
          <line x1="-30" y1="-110" x2="0" y2="-200" />
          <line x1="80" y1="60" x2="140" y2="170" />
          <line x1="160" y1="-140" x2="290" y2="-60" />
          <line x1="-220" y1="70" x2="-260" y2="-30" />
          <line x1="-50" y1="190" x2="-160" y2="230" />
          <line x1="250" y1="30" x2="310" y2="170" />
        </g>
      </svg>

      <style>{`
        .clockwork-bg {
          position: absolute;
          inset: 0;
          z-index: 0;
          pointer-events: none;
          overflow: hidden;
        }
        .clockwork-svg {
          width: 100%;
          height: 100%;
        }
        .gear-ambient-glow {
          animation: gear-pulse 6s ease-in-out infinite alternate;
        }
        @keyframes gear-pulse {
          0%   { opacity: 0.6; }
          50%  { opacity: 1;   }
          100% { opacity: 0.6; }
        }
      `}</style>
    </div>
  );
};

export default ClockworkBackground;
