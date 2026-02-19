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
/**
 * Definitive Interlocking Map (m=5)
 * PR = T * 2.5
 */
const GEARS: GearDef[] = [
  // 1. Blue Primary (Anchor)
  {
    cx: -200,
    cy: -50,
    innerR: 90,
    outerR: 110,
    teeth: 40,
    color: 'var(--atlas-blue)',
    opacity: 0.35,
    speed: 120,
    cw: true,
    glowColor: 'rgba(0,163,255,0.4)',
  },
  // 2. Green Small (Meshes with 1)
  {
    cx: -50,
    cy: -50,
    innerR: 40,
    outerR: 55,
    teeth: 20,
    color: 'var(--tetyana-green)',
    opacity: 0.35,
    speed: 60,
    cw: false,
    glowColor: 'rgba(0,255,65,0.35)',
  },
  // 3. Orange Medium (Meshes with 2)
  {
    cx: 75,
    cy: -50,
    innerR: 65,
    outerR: 85,
    teeth: 30,
    color: 'var(--grisha-orange)',
    opacity: 0.3,
    speed: 90,
    cw: true,
    glowColor: 'rgba(255,140,0,0.35)',
  },
  // 4. Blue Small (Meshes with 3) - Lower
  {
    cx: 75,
    cy: 75,
    innerR: 35,
    outerR: 50,
    teeth: 20,
    color: 'var(--atlas-blue)',
    opacity: 0.25,
    speed: 135,
    cw: false,
    glowColor: 'rgba(0,163,255,0.3)',
  },
  // 5. Green Large (Meshes with 4) - Left
  {
    cx: -50,
    cy: 75,
    innerR: 65,
    outerR: 85,
    teeth: 30,
    color: 'var(--tetyana-green)',
    opacity: 0.3,
    speed: 90,
    cw: true,
    glowColor: 'rgba(0,255,65,0.3)',
  },
  // 6. Orange Small (Meshes with 5) - Left
  {
    cx: -175,
    cy: 75,
    innerR: 35,
    outerR: 50,
    teeth: 20,
    color: 'var(--grisha-orange)',
    opacity: 0.3,
    speed: 135,
    cw: false,
    glowColor: 'rgba(255,140,0,0.3)',
  },
  // 7. Blue Tiny (Meshes with 1) - Top
  {
    cx: -200,
    cy: -185,
    innerR: 25,
    outerR: 35,
    teeth: 14,
    color: 'var(--atlas-blue)',
    opacity: 0.25,
    speed: 342.8,
    cw: false,
    glowColor: 'rgba(0,163,255,0.25)',
  },
  // 8. Green Medium (Meshes with 7) - Right
  {
    cx: -85,
    cy: -185,
    innerR: 55,
    outerR: 75,
    teeth: 32,
    color: 'var(--tetyana-green)',
    opacity: 0.28,
    speed: 150,
    cw: true,
    glowColor: 'rgba(0,255,65,0.3)',
  },
];

const ClockworkBackground: React.FC = () => {
  return (
    <div className="clockwork-bg" aria-hidden="true">
      <svg
        viewBox="-400 -320 800 640"
        preserveAspectRatio="xMidYMid meet"
        className="clockwork-svg"
      >
        <defs>
          {/* 3D Gear Bevel/Lighting Filter */}
          <filter id="gear-3d" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur in="SourceAlpha" stdDeviation="1.5" result="blur" />
            <feOffset in="blur" dx="1" dy="1" result="offsetBlur" />
            <feSpecularLighting
              in="blur"
              surfaceScale="3"
              specularConstant="1.2"
              specularExponent="30"
              lighting-color="white"
              result="specOut"
            >
              <fePointLight x="-5000" y="-10000" z="20000" />
            </feSpecularLighting>
            <feComposite in="specOut" in2="SourceAlpha" operator="in" result="specOut" />
            <feComposite
              in="SourceGraphic"
              in2="specOut"
              operator="arithmetic"
              k1="0"
              k2="1"
              k3="1"
              k4="0"
              result="litGraphic"
            />
            <feMerge>
              <feMergeNode in="offsetBlur" />
              <feMergeNode in="litGraphic" />
            </feMerge>
          </filter>

          {/* Per-color inner gradients for depth */}
          <linearGradient id="grad-blue" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--atlas-blue)" stopOpacity="1" />
            <stop offset="100%" stopColor="#003a5c" stopOpacity="1" />
          </linearGradient>
          <linearGradient id="grad-green" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--tetyana-green)" stopOpacity="1" />
            <stop offset="100%" stopColor="green" stopOpacity="1" />
          </linearGradient>
          <linearGradient id="grad-orange" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="var(--grisha-orange)" stopOpacity="1" />
            <stop offset="100%" stopColor="#804600" stopOpacity="1" />
          </linearGradient>

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

        {/* Render all gears */}
        {GEARS.map((g) => {
          const gearColorTag = g.color.includes('blue')
            ? 'blue'
            : g.color.includes('green')
              ? 'green'
              : 'orange';

          const filterId = `cw-glow-${gearColorTag}`;
          const gradId = `grad-${gearColorTag}`;

          const path = gearPath(g.innerR, g.outerR, g.teeth);
          const animDir = g.cw ? 'rotate-cw' : 'rotate-ccw';

          return (
            <g key={`${g.cx}-${g.cy}`} transform={`translate(${g.cx}, ${g.cy})`}>
              {/* Gear body - IMPORTANT: remove transformOrigin center to prevent orbiting (flying) */}
              <g
                style={{
                  animation: `${animDir} ${g.speed}s linear infinite`,
                }}
                filter={`url(#gear-3d) url(#${filterId})`}
              >
                <path
                  d={path}
                  fill={`url(#${gradId})`}
                  fillOpacity={g.opacity * 0.4}
                  stroke={g.color}
                  strokeWidth={g.outerR > 60 ? 1.8 : 1.2}
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

        {/* Decorative connection lines refreshed for new positions */}
        <g opacity="0.04" stroke="var(--atlas-blue)" strokeWidth="0.5" strokeDasharray="4 6">
          <line x1="-200" y1="-50" x2="-50" y2="-50" />
          <line x1="-50" y1="-50" x2="75" y2="-50" />
          <line x1="75" y1="-50" x2="75" y2="75" />
          <line x1="75" y1="75" x2="-50" y2="75" />
          <line x1="-50" y1="75" x2="-175" y2="75" />
          <line x1="-200" y1="-50" x2="-200" y2="-185" />
          <line x1="-200" y1="-185" x2="-85" y2="-185" />
        </g>
      </svg>

      <style>{`
        .clockwork-bg {
          position: absolute;
          inset: 0;
          z-index: 100;
          pointer-events: none;
          overflow: hidden;
          mix-blend-mode: plus-lighter;
        }
        .clockwork-svg {
          width: 100%;
          height: 100%;
        }
      `}</style>
    </div>
  );
};

export default ClockworkBackground;
