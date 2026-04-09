import React, { useState } from 'react';
import { motion } from 'framer-motion';
import './MortgageForm.css';
import './RenewalForm.css';

const INITIAL = {
  remaining_balance: '',
  current_rate:      '',
  new_rate:          '',
  remaining_years:   '',
  lump_sum:          '',
  new_amortization:  '',
  annual_income:     '',
  monthly_debt:      '',
};

const fmt      = (v) => v === '' ? '' : Number(v).toLocaleString('en-CA', { maximumFractionDigits: 2 });
const unformat = (v) => v.replace(/[^0-9.]/g, '');

export default function RenewalForm({ onSubmit, loading }) {
  const [form,   setForm]   = useState(INITIAL);
  const [errors, setErrors] = useState({});

  const set = (field) => (e) => {
    const raw = unformat(e.target.value);
    setForm((p) => ({ ...p, [field]: raw }));
    if (errors[field]) setErrors((p) => ({ ...p, [field]: null }));
  };

  const validate = () => {
    const errs = {};
    const bal  = parseFloat(form.remaining_balance);
    const cr   = parseFloat(form.current_rate);
    const nr   = parseFloat(form.new_rate);
    const ry   = parseFloat(form.remaining_years);
    const ls   = parseFloat(form.lump_sum) || 0;
    const na   = parseFloat(form.new_amortization) || 0;

    if (!form.remaining_balance || bal <= 0)      errs.remaining_balance = 'Required';
    if (!form.current_rate      || cr <= 0)       errs.current_rate      = 'Required';
    if (!form.new_rate          || nr <= 0)       errs.new_rate          = 'Required';
    if (!form.remaining_years   || ry < 1)        errs.remaining_years   = 'Required (1–30)';
    if (ry > 30)                                  errs.remaining_years   = 'Max 30 years';
    if (ls >= bal)                                errs.lump_sum          = 'Must be less than balance';
    if (na > 30)                                  errs.new_amortization  = 'Max 30 years';
    return errs;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    onSubmit({
      remaining_balance: parseFloat(form.remaining_balance),
      current_rate:      parseFloat(form.current_rate),
      new_rate:          parseFloat(form.new_rate),
      remaining_years:   parseInt(form.remaining_years),
      lump_sum:          parseFloat(form.lump_sum)         || 0,
      new_amortization:  parseInt(form.new_amortization)   || 0,
      annual_income:     parseFloat(form.annual_income)    || 0,
      monthly_debt:      parseFloat(form.monthly_debt)     || 0,
    });
  };

  const rateDiff = form.current_rate && form.new_rate
    ? (parseFloat(form.new_rate) - parseFloat(form.current_rate)).toFixed(2)
    : null;

  return (
    <form className="mortgage-form" onSubmit={handleSubmit} noValidate>
      <div className="form-header">
        <h2>Renewal Calculator</h2>
        <p>Compare your current mortgage against renewal offers</p>
      </div>

      {/* ── Current mortgage ── */}
      <section className="form-section">
        <h3>Current Mortgage</h3>

        <div className={`field ${errors.remaining_balance ? 'error' : ''}`}>
          <label>Remaining Balance</label>
          <div className="input-wrap">
            <span className="prefix">$</span>
            <input
              inputMode="numeric" placeholder="320,000"
              value={fmt(form.remaining_balance)}
              onChange={set('remaining_balance')}
            />
            <span className="suffix">CAD</span>
          </div>
          {errors.remaining_balance && <span className="err-msg">{errors.remaining_balance}</span>}
        </div>

        <div className="field-row">
          <div className={`field ${errors.current_rate ? 'error' : ''}`}>
            <label>Current Rate</label>
            <div className="input-wrap">
              <input
                inputMode="decimal" placeholder="4.79"
                value={form.current_rate}
                onChange={set('current_rate')}
              />
              <span className="suffix">%</span>
            </div>
            {errors.current_rate && <span className="err-msg">{errors.current_rate}</span>}
          </div>

          <div className={`field ${errors.remaining_years ? 'error' : ''}`}>
            <label>Years Remaining</label>
            <div className="input-wrap">
              <input
                inputMode="numeric" placeholder="22"
                value={form.remaining_years}
                onChange={set('remaining_years')}
              />
              <span className="suffix">yrs</span>
            </div>
            {errors.remaining_years && <span className="err-msg">{errors.remaining_years}</span>}
          </div>
        </div>
      </section>

      {/* ── Renewal offer ── */}
      <section className="form-section">
        <h3>Renewal Offer</h3>

        <div className={`field ${errors.new_rate ? 'error' : ''}`}>
          <label>Offered Rate</label>
          <div className="input-wrap">
            <input
              inputMode="decimal" placeholder="5.24"
              value={form.new_rate}
              onChange={set('new_rate')}
            />
            <span className="suffix">%</span>
          </div>
          {errors.new_rate && <span className="err-msg">{errors.new_rate}</span>}
          {rateDiff !== null && (
            <span className={`hint ${parseFloat(rateDiff) <= 0 ? 'green' : 'yellow'}`}>
              {parseFloat(rateDiff) > 0 ? `↑ +${rateDiff}% from current` : parseFloat(rateDiff) < 0 ? `↓ ${rateDiff}% from current` : '↔ Same as current'}
            </span>
          )}
        </div>

        <div className="field-row">
          <div className={`field ${errors.lump_sum ? 'error' : ''}`}>
            <label>Lump-Sum Payment <span className="optional">(optional)</span></label>
            <div className="input-wrap">
              <span className="prefix">$</span>
              <input
                inputMode="numeric" placeholder="0"
                value={fmt(form.lump_sum)}
                onChange={set('lump_sum')}
              />
            </div>
            {errors.lump_sum && <span className="err-msg">{errors.lump_sum}</span>}
          </div>

          <div className={`field ${errors.new_amortization ? 'error' : ''}`}>
            <label>New Amortization <span className="optional">(optional)</span></label>
            <div className="input-wrap">
              <input
                inputMode="numeric" placeholder="same"
                value={form.new_amortization}
                onChange={set('new_amortization')}
              />
              <span className="suffix">yrs</span>
            </div>
            {errors.new_amortization && <span className="err-msg">{errors.new_amortization}</span>}
            {!errors.new_amortization && <span className="hint">Leave blank to keep current</span>}
          </div>
        </div>
      </section>

      {/* ── Stress test (optional) ── */}
      <section className="form-section">
        <h3>Stress Test <span className="optional" style={{ textTransform: 'none', letterSpacing: 0 }}>— optional</span></h3>

        <div className="field-row">
          <div className="field">
            <label>Annual Income</label>
            <div className="input-wrap">
              <span className="prefix">$</span>
              <input
                inputMode="numeric" placeholder="95,000"
                value={fmt(form.annual_income)}
                onChange={set('annual_income')}
              />
            </div>
          </div>

          <div className="field">
            <label>Monthly Debt</label>
            <div className="input-wrap">
              <span className="prefix">$</span>
              <input
                inputMode="numeric" placeholder="400"
                value={fmt(form.monthly_debt)}
                onChange={set('monthly_debt')}
              />
            </div>
          </div>
        </div>
        <p className="hint" style={{ marginTop: '-0.25rem' }}>Provide income to check OSFI B-20 compliance at renewal</p>
      </section>

      <div className="submit-wrap">
        <motion.button
          type="submit"
          className="submit-btn"
          disabled={loading}
          whileTap={{ scale: 0.98 }}
        >
          {loading ? 'Calculating…' : 'Calculate Renewal →'}
        </motion.button>
      </div>
    </form>
  );
}
