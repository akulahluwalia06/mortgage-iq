import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { predictMortgage, calculateRenewal } from './api/mortgageApi';
import MortgageForm  from './components/MortgageForm';
import ResultPanel   from './components/ResultPanel';
import RenewalForm   from './components/RenewalForm';
import RenewalPanel  from './components/RenewalPanel';
import Header        from './components/Header';
import './App.css';

const TABS = [
  { key: 'new',     label: 'New Mortgage' },
  { key: 'renewal', label: 'Renewal'      },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('new');
  const [result,    setResult]    = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState(null);

  const switchTab = (tab) => {
    setActiveTab(tab);
    setResult(null);
    setError(null);
  };

  const handleNewMortgage = async (formData) => {
    setLoading(true);
    setError(null);
    setResult(null);
    const { data, error: err } = await predictMortgage(formData);
    if (err) setError(err);
    else     setResult(data);
    setLoading(false);
  };

  const handleRenewal = async (formData) => {
    setLoading(true);
    setError(null);
    setResult(null);
    const { data, error: err } = await calculateRenewal(formData);
    if (err) setError(err);
    else     setResult(data);
    setLoading(false);
  };

  const placeholderText = activeTab === 'new'
    ? { icon: '🏙', heading: 'Your Analysis Will Appear Here', sub: 'Complete your profile and tap Analyse My Mortgage → for an instant assessment.' }
    : { icon: '🔄', heading: 'Renewal Comparison Will Appear Here', sub: 'Enter your current mortgage details and renewal offer to see a full comparison.' };

  const placeholderFeatures = activeTab === 'new'
    ? ['Approval probability', 'Interest rate forecast', 'GDS & TDS ratios', 'CMHC insurance', 'Amortization schedule', 'Stress test result']
    : ['Payment comparison', 'Total interest savings', 'Lump-sum impact', 'Amortization options', 'Stress test check', 'Renewal insights'];

  return (
    <div className="app">
      <Header />

      <main className="main">
        {/* ── Tab switcher ── */}
        <div className="tab-switcher">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab-btn${activeTab === t.key ? ' active' : ''}`}
              onClick={() => switchTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="grid">
          {/* ── Left: form column ── */}
          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab + '-form'}
              className="form-col"
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ duration: 0.28, ease: [0.4, 0, 0.2, 1] }}
            >
              {activeTab === 'new'
                ? <MortgageForm onSubmit={handleNewMortgage} loading={loading} />
                : <RenewalForm  onSubmit={handleRenewal}     loading={loading} />
              }
            </motion.div>
          </AnimatePresence>

          {/* ── Right: results column ── */}
          <div className="result-col">
            <AnimatePresence mode="wait">

              {loading && (
                <motion.div
                  key="loading"
                  className="loading-card"
                  initial={{ opacity: 0, scale: 0.97 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ duration: 0.25 }}
                >
                  <div className="spinner-ring" />
                  <p>{activeTab === 'new' ? 'Analysing your profile' : 'Calculating renewal'}</p>
                  <span className="loading-sub">
                    {activeTab === 'new'
                      ? 'Running your inputs against Canadian lending criteria'
                      : 'Comparing your current mortgage against the renewal offer'}
                  </span>
                </motion.div>
              )}

              {error && !loading && (
                <motion.div
                  key="error"
                  className="error-card"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                >
                  <span className="error-icon">⚠️</span>
                  <p>{error}</p>
                </motion.div>
              )}

              {result && !loading && (
                <motion.div
                  key="result"
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.35 }}
                >
                  {activeTab === 'new'
                    ? <ResultPanel  result={result} />
                    : <RenewalPanel result={result} />
                  }
                </motion.div>
              )}

              {!result && !loading && !error && (
                <motion.div
                  key={`placeholder-${activeTab}`}
                  className="placeholder-card"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.4 }}
                >
                  <div className="placeholder-glyph">{placeholderText.icon}</div>
                  <h3>{placeholderText.heading}</h3>
                  <p>{placeholderText.sub}</p>
                  <ul className="placeholder-features">
                    {placeholderFeatures.map((f) => <li key={f}>{f}</li>)}
                  </ul>
                </motion.div>
              )}

            </AnimatePresence>
          </div>
        </div>
      </main>

      <footer className="footer">
        🍁 MortgageIQ · For Canadian homebuyers · Not financial advice
      </footer>
    </div>
  );
}
