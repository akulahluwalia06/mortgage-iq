import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import MortgageForm from './components/MortgageForm';
import ResultPanel from './components/ResultPanel';
import Header from './components/Header';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

export default function App() {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (formData) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const { data } = await axios.post(`${API_URL}/predict`, formData);
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail || 'Unable to reach the analysis server.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app">
      <Header />
      <main className="main">
        <div className="grid">
          <motion.div
            className="form-col"
            initial={{ opacity: 0, x: -24 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, ease: 'easeOut' }}
          >
            <MortgageForm onSubmit={handleSubmit} loading={loading} />
          </motion.div>

          <div className="result-col">
            <AnimatePresence mode="wait">
              {loading && (
                <motion.div
                  key="loading"
                  className="loading-card"
                  initial={{ opacity: 0, scale: 0.96 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.96 }}
                  transition={{ duration: 0.3 }}
                >
                  <div className="spinner-ring" />
                  <p>Analysing your profile</p>
                  <span className="loading-sub">Running your inputs against Canadian lending criteria</span>
                </motion.div>
              )}

              {error && !loading && (
                <motion.div
                  key="error"
                  className="error-card"
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
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
                  transition={{ duration: 0.4 }}
                >
                  <ResultPanel result={result} />
                </motion.div>
              )}

              {!result && !loading && !error && (
                <motion.div
                  key="placeholder"
                  className="placeholder-card"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ duration: 0.5 }}
                >
                  <div className="placeholder-glyph">🏙</div>
                  <h3>Your Analysis Will Appear Here</h3>
                  <p>Complete your profile and tap <strong>Analyse My Mortgage</strong> for an instant assessment.</p>
                  <ul className="placeholder-features">
                    <li>Approval probability</li>
                    <li>Interest rate forecast</li>
                    <li>GDS &amp; TDS ratios</li>
                    <li>CMHC insurance</li>
                    <li>Amortization schedule</li>
                    <li>Stress test result</li>
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
