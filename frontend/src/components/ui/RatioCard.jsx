import React from 'react';

export default function RatioCard({ label, value, max, actual }) {
  const pct = Math.min(actual / max, 1) * 100;
  const ok  = actual <= max;
  const clr = ok ? '#1B5E3B' : '#C8102E';

  return (
    <div className={`ratio-card ${ok ? 'ok' : 'over'}`}>
      <div className="ratio-top">
        <span>{label}</span>
        <span className="ratio-value" style={{ color: clr }}>{value}</span>
      </div>
      <div className="ratio-bar">
        <div className="ratio-fill" style={{ width: `${pct}%`, background: clr }} />
      </div>
      <p className="ratio-limit">
        Max {(max * 100).toFixed(0)}% · {ok ? '✓ Within limit' : '✕ Exceeds limit'}
      </p>
    </div>
  );
}
