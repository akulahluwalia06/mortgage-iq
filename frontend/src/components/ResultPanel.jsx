import React, { useState } from 'react';
import { motion } from 'framer-motion';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, PieChart, Pie, Cell,
} from 'recharts';
import './ResultPanel.css';

const CAD = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n);

const PCT = (n) => `${(n * 100).toFixed(1)}%`;

function ApprovalGauge({ prob }) {
  const pct = Math.round(prob * 100);
  const color = pct >= 75 ? '#00ffa3' : pct >= 50 ? '#fbbf24' : '#ff4d6d';
  const arcLen = 173;
  const filled = (pct / 100) * arcLen;

  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 120 82" className="gauge-svg" style={{ color }}>
        {/* Track */}
        <path d="M10,76 A55,55 0 0,1 110,76" fill="none"
          stroke="rgba(255,255,255,0.06)" strokeWidth="8" strokeLinecap="round" />
        {/* Fill */}
        <path d="M10,76 A55,55 0 0,1 110,76" fill="none"
          stroke={color} strokeWidth="8" strokeLinecap="round"
          strokeDasharray={`${filled} ${arcLen}`}
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
        />
        <text x="60" y="73" textAnchor="middle" fontSize="19"
          fontWeight="700" fill={color} fontFamily="Space Grotesk, sans-serif">
          {pct}%
        </text>
      </svg>
      <p className="gauge-label" style={{ color }}>
        {pct >= 75 ? 'Strong Profile' : pct >= 50 ? 'Moderate Profile' : 'Low Probability'}
      </p>
    </div>
  );
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <p className="tooltip-label">Year {label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {CAD(p.value)}
        </p>
      ))}
    </div>
  );
};

export default function ResultPanel({ result }) {
  const [tab, setTab] = useState('overview');

  const {
    approval_probability, approved, predicted_interest_rate,
    monthly_payment, total_payment, total_interest, cmhc_insurance,
    loan_amount, gds_ratio, tds_ratio, stress_test_rate,
    passes_stress_test, amortization_schedule, insights,
  } = result;

  const chartData = (amortization_schedule ?? []).map((row) => ({
    year: row.year,
    Principal: Math.round(row.principal_paid),
    Interest: Math.round(row.interest_paid),
    Balance: Math.round(row.remaining_balance),
  }));

  const pieData = [
    { name: 'Principal', value: Math.round(loan_amount) },
    { name: 'Interest',  value: Math.round(total_interest) },
    ...(cmhc_insurance > 0 ? [{ name: 'CMHC', value: Math.round(cmhc_insurance) }] : []),
  ];
  const PIE_COLORS = [
    getComputedStyle(document.documentElement).getPropertyValue('--cyan').trim()   || '#00d4ff',
    getComputedStyle(document.documentElement).getPropertyValue('--violet').trim() || '#7c3aed',
    getComputedStyle(document.documentElement).getPropertyValue('--amber').trim()  || '#fbbf24',
  ];

  return (
    <div className="result-panel">

      {/* ── Approval banner ── */}
      <div className={`glass-card approval-banner ${approved ? 'approved' : 'declined'}`}>
        <div className="approval-text">
          <h2>{approved ? '✦ Likely Approved' : '◈ Review Required'}</h2>
          <p>
            {approved
              ? 'Your profile aligns with Canadian lending standards.'
              : 'Some criteria need attention — see insights below.'}
          </p>
        </div>
        <ApprovalGauge prob={approval_probability} />
      </div>

      {/* ── Key stats ── */}
      <div className="stats-grid">
        <Stat label="Monthly Payment"   value={CAD(monthly_payment)}          highlight />
        <Stat label="Predicted Rate"    value={`${predicted_interest_rate}%`} highlight />
        <Stat label="Total Interest"    value={CAD(total_interest)}           color="red" />
        <Stat label="Total Cost"        value={CAD(total_payment)} />
        {cmhc_insurance > 0 && <Stat label="CMHC Insurance" value={CAD(cmhc_insurance)} color="yellow" />}
        <Stat label="Loan Amount"       value={CAD(loan_amount)} />
      </div>

      {/* ── Ratios + stress test ── */}
      <div className="ratio-row">
        <RatioCard label="GDS Ratio" value={PCT(gds_ratio)} max={0.39} actual={gds_ratio} />
        <RatioCard label="TDS Ratio" value={PCT(tds_ratio)} max={0.44} actual={tds_ratio} />
        <div className={`stress-card ${passes_stress_test ? 'pass' : 'fail'}`}>
          <span className="stress-icon">{passes_stress_test ? '✅' : '❌'}</span>
          <div>
            <p className="stress-title">Stress Test</p>
            <p className="stress-rate">@ {stress_test_rate}%</p>
            <p className="stress-status">{passes_stress_test ? 'PASSES' : 'FAILS'}</p>
          </div>
        </div>
      </div>

      {/* ── Insights ── */}
      {insights.length > 0 && (
        <div className="insights">
          <h3>Analysis &amp; Recommendations</h3>
          <ul>
            {insights.map((ins, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.06 }}
              >
                {ins}
              </motion.li>
            ))}
          </ul>
        </div>
      )}

      {/* ── Chart tabs ── */}
      <div className="chart-tabs">
        {[
          { key: 'overview',   label: 'Amortization' },
          { key: 'breakdown',  label: 'Cost Breakdown' },
          { key: 'schedule',   label: 'Year-by-Year' },
        ].map((t) => (
          <button
            key={t.key}
            className={`chart-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* ── Bar chart ── */}
      {tab === 'overview' && (
        <div className="chart-wrap">
          <h4>Annual Principal vs Interest</h4>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={chartData} barSize={12} barGap={2}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.07)" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: 'rgba(140,180,220,0.5)', fontSize: 10 }} tickFormatter={(v) => `Y${v}`} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(140,180,220,0.5)', fontSize: 10 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(0,212,255,0.04)' }} />
              <Legend wrapperStyle={{ fontSize: 11, color: 'rgba(140,180,220,0.6)' }} />
              <Bar dataKey="Principal" fill="#00d4ff" radius={[3,3,0,0]} opacity={0.85} />
              <Bar dataKey="Interest"  fill="#7c3aed" radius={[3,3,0,0]} opacity={0.85} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Area chart ── */}
      {tab === 'overview' && (
        <div className="chart-wrap">
          <h4>Remaining Balance</h4>
          <ResponsiveContainer width="100%" height={210}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="balGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#00d4ff" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#00d4ff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,212,255,0.07)" vertical={false} />
              <XAxis dataKey="year" tick={{ fill: 'rgba(140,180,220,0.5)', fontSize: 10 }} tickFormatter={(v) => `Y${v}`} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: 'rgba(140,180,220,0.5)', fontSize: 10 }} tickFormatter={(v) => `$${(v/1000).toFixed(0)}k`} axisLine={false} tickLine={false} />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(0,212,255,0.2)' }} />
              <Area type="monotone" dataKey="Balance" stroke="#00d4ff" fill="url(#balGrad)" strokeWidth={2} dot={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Pie chart ── */}
      {tab === 'breakdown' && (
        <div className="chart-wrap pie-wrap">
          <h4>Total Cost Breakdown</h4>
          <ResponsiveContainer width="100%" height={290}>
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius={72} outerRadius={112}
                paddingAngle={3} dataKey="value" strokeWidth={0}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i]}
                    style={{ filter: `drop-shadow(0 0 6px ${PIE_COLORS[i]}60)` }} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => CAD(v)}
                contentStyle={{ background: 'rgba(8,16,38,0.95)', border: '1px solid rgba(0,212,255,0.15)', borderRadius: 10, fontSize: 12 }} />
              <Legend formatter={(v, e) => `${v}: ${CAD(e.payload.value)}`}
                wrapperStyle={{ fontSize: 12, color: 'rgba(140,180,220,0.7)' }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* ── Schedule table ── */}
      {tab === 'schedule' && (
        <div className="schedule-table-wrap">
          <h4>Year-by-Year Schedule</h4>
          <div className="table-scroll">
            <table className="schedule-table">
              <thead>
                <tr>
                  <th>Year</th>
                  <th>Principal</th>
                  <th>Interest</th>
                  <th>Balance</th>
                </tr>
              </thead>
              <tbody>
                {amortization_schedule.map((row) => (
                  <tr key={row.year}>
                    <td>{row.year}</td>
                    <td className="green">{CAD(row.principal_paid)}</td>
                    <td className="red">{CAD(row.interest_paid)}</td>
                    <td>{CAD(row.remaining_balance)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, highlight, color }) {
  return (
    <div className={`stat-card ${highlight ? 'highlight' : ''}`}>
      <p className="stat-label">{label}</p>
      <p className={`stat-value ${color || ''}`}>{value}</p>
    </div>
  );
}

function RatioCard({ label, value, max, actual }) {
  const pct = Math.min(actual / max, 1) * 100;
  const ok  = actual <= max;
  return (
    <div className={`ratio-card ${ok ? 'ok' : 'over'}`}>
      <div className="ratio-top">
        <span style={{ color: 'rgba(140,180,220,0.6)', fontSize: '0.75rem' }}>{label}</span>
        <span className="ratio-value" style={{ color: ok ? '#00ffa3' : '#ff4d6d' }}>{value}</span>
      </div>
      <div className="ratio-bar">
        <div className="ratio-fill"
          style={{ width: `${pct}%`, background: ok ? '#00ffa3' : '#ff4d6d',
            boxShadow: ok ? '0 0 6px #00ffa360' : '0 0 6px #ff4d6d60' }} />
      </div>
      <p className="ratio-limit">Max {(max * 100).toFixed(0)}% · {ok ? '✓ Within limit' : '✕ Exceeds limit'}</p>
    </div>
  );
}
