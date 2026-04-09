import React from 'react';

const ARC_LEN = 173;

const label = (pct) => {
  if (pct >= 75) return 'Strong Profile';
  if (pct >= 50) return 'Moderate Profile';
  return 'Low Probability';
};

const color = (pct) => {
  if (pct >= 75) return '#1B5E3B';
  if (pct >= 50) return '#B45309';
  return '#C8102E';
};

export default function ApprovalGauge({ prob }) {
  const pct    = Math.round(prob * 100);
  const clr    = color(pct);
  const filled = (pct / 100) * ARC_LEN;

  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 120 82" className="gauge-svg" style={{ color: clr }}>
        <path d="M10,76 A55,55 0 0,1 110,76" fill="none"
          stroke="rgba(28,18,8,0.07)" strokeWidth="8" strokeLinecap="round" />
        <path d="M10,76 A55,55 0 0,1 110,76" fill="none"
          stroke={clr} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${filled} ${ARC_LEN}`} />
        <text x="60" y="73" textAnchor="middle" fontSize="19"
          fontWeight="700" fill={clr} fontFamily="IBM Plex Mono, monospace">
          {pct}%
        </text>
      </svg>
      <p className="gauge-label" style={{ color: clr }}>{label(pct)}</p>
    </div>
  );
}
