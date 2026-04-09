import React, { useState } from 'react';
import { motion } from 'framer-motion';
import ApprovalGauge     from './ui/ApprovalGauge';
import StatCard          from './ui/StatCard';
import RatioCard         from './ui/RatioCard';
import AmortizationChart from './charts/AmortizationChart';
import CostBreakdownChart from './charts/CostBreakdownChart';
import ScheduleTable     from './charts/ScheduleTable';
import './ResultPanel.css';

const CAD = (n) =>
  new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 }).format(n);

const PCT = (n) => `${(n * 100).toFixed(1)}%`;

// P10 — hoisted outside component so it's never recreated on render
const fadeUp = (delay = 0) => ({
  initial:    { opacity: 0, y: 14 },
  animate:    { opacity: 1, y: 0 },
  transition: { duration: 0.38, delay, ease: [0.4, 0, 0.2, 1] },
});

const TABS = [
  { key: 'overview',  label: 'Amortization'   },
  { key: 'breakdown', label: 'Cost Breakdown'  },
  { key: 'schedule',  label: 'Year-by-Year'    },
];

export default function ResultPanel({ result }) {
  const [tab, setTab] = useState('overview');

  const {
    approval_probability, approved, predicted_interest_rate,
    monthly_payment, total_payment, total_interest, cmhc_insurance,
    loan_amount, gds_ratio, tds_ratio, stress_test_rate,
    passes_stress_test, amortization_schedule, insights,
  } = result;

  const chartData = (amortization_schedule ?? []).map((row) => ({
    year:      row.year,
    Principal: Math.round(row.principal_paid),
    Interest:  Math.round(row.interest_paid),
    Balance:   Math.round(row.remaining_balance),
  }));

  const pieData = [
    { name: 'Principal', value: Math.round(loan_amount)     },
    { name: 'Interest',  value: Math.round(total_interest)  },
    ...(cmhc_insurance > 0
      ? [{ name: 'CMHC', value: Math.round(cmhc_insurance) }]
      : []),
  ];

  return (
    <div className="result-panel">

      {/* ── Approval banner ── */}
      <motion.div {...fadeUp(0)} className={`glass-card approval-banner ${approved ? 'approved' : 'declined'}`}>
        <div className="approval-text">
          <h2>{approved ? '✦ Likely Approved' : '◈ Review Required'}</h2>
          <p>
            {approved
              ? 'Your profile aligns with Canadian lending standards.'
              : 'Some criteria need attention — see insights below.'}
          </p>
        </div>
        <ApprovalGauge prob={approval_probability} />
      </motion.div>

      {/* ── Key stats ── */}
      <motion.div {...fadeUp(0.07)} className="stats-grid">
        <StatCard label="Monthly Payment"  value={CAD(monthly_payment)}           highlight />
        <StatCard label="Predicted Rate"   value={`${predicted_interest_rate}%`}  highlight />
        <StatCard label="Total Interest"   value={CAD(total_interest)}            color="red" />
        <StatCard label="Total Cost"       value={CAD(total_payment)} />
        {cmhc_insurance > 0 &&
          <StatCard label="CMHC Insurance" value={CAD(cmhc_insurance)}            color="yellow" />}
        <StatCard label="Loan Amount"      value={CAD(loan_amount)} />
      </motion.div>

      {/* ── Ratios + stress test ── */}
      <motion.div {...fadeUp(0.13)} className="ratio-row">
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
      </motion.div>

      {/* ── Insights ── */}
      {insights.length > 0 && (
        <motion.div {...fadeUp(0.19)} className="insights">
          <h3>Analysis &amp; Recommendations</h3>
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

      {/* ── Charts ── */}
      {tab === 'overview'  && <motion.div {...fadeUp(0.28)}><AmortizationChart  data={chartData} /></motion.div>}
      {tab === 'breakdown' && <motion.div {...fadeUp(0.10)}><CostBreakdownChart data={pieData}   /></motion.div>}
      {tab === 'schedule'  && <motion.div {...fadeUp(0.10)}><ScheduleTable      schedule={amortization_schedule} /></motion.div>}

    </div>
  );
}
