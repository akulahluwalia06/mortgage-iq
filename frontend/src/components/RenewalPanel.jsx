import React, { useState } from 'react';
import { motion } from 'framer-motion';
import AmortizationChart from './charts/AmortizationChart';
import ScheduleTable     from './charts/ScheduleTable';
import StatCard          from './ui/StatCard';
import './ResultPanel.css';
import './RenewalPanel.css';

const CAD  = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n);
const CADD = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 2 }).format(Math.abs(n));

const fadeUp = (delay = 0) => ({
  initial:    { opacity: 0, y: 14 },
  animate:    { opacity: 1, y: 0 },
  transition: { duration: 0.38, delay, ease: [0.4, 0, 0.2, 1] },
});

const TABS = [
  { key: 'overview', label: 'Amortization' },
  { key: 'schedule', label: 'Year-by-Year' },
];

export default function RenewalPanel({ result }) {
  const [tab, setTab] = useState('overview');

  const {
    current_monthly, new_monthly, monthly_savings,
    current_total_interest, new_total_interest, interest_savings,
    new_balance, effective_amortization, stress_test_rate,
    passes_stress_test, amortization_schedule, insights,
  } = result;

  const improved = monthly_savings >= 0;

  const chartData = (amortization_schedule ?? []).map((row) => ({
    year:      row.year,
    Principal: Math.round(row.principal_paid),
    Interest:  Math.round(row.interest_paid),
    Balance:   Math.round(row.remaining_balance),
  }));

  return (
    <div className="result-panel">

      {/* ── Summary banner ── */}
      <motion.div {...fadeUp(0)} className={`glass-card renewal-banner ${improved ? 'saving' : 'costing'}`}>
        <div className="renewal-banner-text">
          <h2>{improved ? '↓ Payment Decreasing' : '↑ Payment Increasing'}</h2>
          <p>
            {improved
              ? `Your monthly payment drops by ${CADD(monthly_savings)} at renewal.`
              : `Your monthly payment rises by ${CADD(monthly_savings)} at renewal.`}
          </p>
        </div>
        <div className="renewal-delta">
          <span className="delta-label">Monthly change</span>
          <span className={`delta-value ${improved ? 'green' : 'red'}`}>
            {improved ? '−' : '+'}{CADD(monthly_savings)}/mo
          </span>
        </div>
      </motion.div>

      {/* ── Key stats ── */}
      <motion.div {...fadeUp(0.07)} className="stats-grid">
        <StatCard label="Current Payment" value={CAD(current_monthly)} />
        <StatCard label="New Payment"     value={CAD(new_monthly)}     highlight />
        <StatCard
          label="Interest Savings"
          value={interest_savings >= 0 ? CAD(interest_savings) : `−${CAD(Math.abs(interest_savings))}`}
          color={interest_savings >= 0 ? 'cyan' : 'red'}
        />
        <StatCard label="New Balance"         value={CAD(new_balance)} />
        <StatCard label="Current Total Int."  value={CAD(current_total_interest)} color="red" />
        <StatCard label="New Total Interest"  value={CAD(new_total_interest)}     color={new_total_interest < current_total_interest ? 'cyan' : 'red'} />
      </motion.div>

      {/* ── Stress test ── */}
      {passes_stress_test !== null && (
        <motion.div {...fadeUp(0.13)} className="ratio-row" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <div className={`stress-card ${passes_stress_test ? 'pass' : 'fail'}`}>
            <span className="stress-icon">{passes_stress_test ? '✅' : '❌'}</span>
            <div>
              <p className="stress-title">Stress Test</p>
              <p className="stress-rate">@ {stress_test_rate}%</p>
              <p className="stress-status">{passes_stress_test ? 'PASSES' : 'FAILS'}</p>
            </div>
          </div>
          <div className="renewal-amort-card">
            <p className="stress-title">New Amortization</p>
            <p className="stress-rate">{effective_amortization} years</p>
            <p className="stress-status" style={{ color: 'var(--navy)' }}>REMAINING</p>
          </div>
        </motion.div>
      )}

      {/* ── Insights ── */}
      {insights.length > 0 && (
        <motion.div {...fadeUp(0.19)} className="insights">
          <h3>Renewal Analysis</h3>
          <ul>
            {insights.map((ins, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.22 + i * 0.055, ease: [0.4, 0, 0.2, 1] }}
              >
                {ins}
              </motion.li>
            ))}
          </ul>
        </motion.div>
      )}

      {/* ── Chart tabs ── */}
      <motion.div {...fadeUp(0.24)} className="chart-tabs">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`chart-tab${tab === t.key ? ' active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </motion.div>

      {tab === 'overview' && <motion.div {...fadeUp(0.28)}><AmortizationChart data={chartData} /></motion.div>}
      {tab === 'schedule' && <motion.div {...fadeUp(0.10)}><ScheduleTable schedule={amortization_schedule} /></motion.div>}

    </div>
  );
}
