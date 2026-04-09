import React from 'react';

export default function StatCard({ label, value, highlight, color }) {
  return (
    <div className={`stat-card${highlight ? ' highlight' : ''}`}>
      <p className="stat-label">{label}</p>
      <p className={`stat-value${color ? ` ${color}` : ''}`}>{value}</p>
    </div>
  );
}
