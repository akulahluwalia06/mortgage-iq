import React, { useState } from 'react';
import { motion } from 'framer-motion';
import './MortgageForm.css';

const PROVINCES = [
  { code: 'ON', name: 'Ontario' },
  { code: 'BC', name: 'British Columbia' },
  { code: 'AB', name: 'Alberta' },
  { code: 'QC', name: 'Quebec' },
  { code: 'MB', name: 'Manitoba' },
  { code: 'SK', name: 'Saskatchewan' },
  { code: 'NS', name: 'Nova Scotia' },
  { code: 'NB', name: 'New Brunswick' },
  { code: 'NL', name: 'Newfoundland' },
  { code: 'PE', name: 'PEI' },
];

const INITIAL = {
  annual_income: '',
  credit_score: '',
  property_value: '',
  down_payment: '',
  existing_monthly_debt: '',
  employment_type: 'salaried',
  province: 'ON',
  amortization: '25',
  property_type: 'house',
};

const fmt = (val) =>
  val === '' ? '' : Number(val).toLocaleString('en-CA', { maximumFractionDigits: 0 });

const unformat = (val) => val.replace(/[^0-9.]/g, '');

export default function MortgageForm({ onSubmit, loading }) {
  const [form, setForm] = useState(INITIAL);
  const [errors, setErrors] = useState({});

  const set = (field) => (e) => {
    const raw = unformat(e.target.value);
    setForm((prev) => ({ ...prev, [field]: raw }));
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: null }));
  };

  const setSelect = (field) => (e) => setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const validate = () => {
    const errs = {};
    const pv = parseFloat(form.property_value);
    const dp = parseFloat(form.down_payment);
    if (!form.annual_income || parseFloat(form.annual_income) < 1) errs.annual_income = 'Required';
    if (!form.credit_score || form.credit_score < 300 || form.credit_score > 900) errs.credit_score = '300–900';
    if (!form.property_value || pv < 1) errs.property_value = 'Required';
    if (!form.down_payment || dp < 1) errs.down_payment = 'Required';
    if (dp >= pv) errs.down_payment = 'Must be less than property value';
    // Canadian CMHC pro-rated minimum: 5% on first $500k + 10% on remainder up to $999k, 20% on $1M+
    const minDp = pv >= 1000000
      ? pv * 0.20
      : pv <= 500000
        ? pv * 0.05
        : 500000 * 0.05 + (pv - 500000) * 0.10;
    if (!errs.down_payment && dp < minDp)
      errs.down_payment = `Min down payment is $${Math.ceil(minDp).toLocaleString('en-CA')} (CMHC rules)`;
    return errs;
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const errs = validate();
    if (Object.keys(errs).length) { setErrors(errs); return; }
    onSubmit({
      annual_income: parseFloat(form.annual_income),
      credit_score: parseInt(form.credit_score),
      property_value: parseFloat(form.property_value),
      down_payment: parseFloat(form.down_payment),
      existing_monthly_debt: parseFloat(form.existing_monthly_debt) || 0,
      employment_type: form.employment_type,
      province: form.province,
      amortization: parseInt(form.amortization),
      property_type: form.property_type,
    });
  };

  const dpPct = form.property_value && form.down_payment
    ? ((parseFloat(form.down_payment) / parseFloat(form.property_value)) * 100).toFixed(1)
    : null;

  return (
    <form className="mortgage-form" onSubmit={handleSubmit} noValidate>
      <div className="form-header">
        <h2>Your Property Profile</h2>
        <p>Enter your details for an instant assessment</p>
      </div>

      <section className="form-section">
        <h3>Financials</h3>

        <div className={`field ${errors.annual_income ? 'error' : ''}`}>
          <label>Annual Gross Income</label>
          <div className="input-wrap">
            <span className="prefix">$</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="95,000"
              value={fmt(form.annual_income)}
              onChange={set('annual_income')}
            />
            <span className="suffix">CAD</span>
          </div>
          {errors.annual_income && <span className="err-msg">{errors.annual_income}</span>}
        </div>

        <div className={`field ${errors.credit_score ? 'error' : ''}`}>
          <label>Credit Score</label>
          <input
            type="number"
            placeholder="720"
            min="300" max="900"
            value={form.credit_score}
            onChange={(e) => { setForm((p) => ({ ...p, credit_score: e.target.value })); }}
          />
          {errors.credit_score && <span className="err-msg">{errors.credit_score}</span>}
          {form.credit_score && (
            <div className="credit-bar-wrap">
              <div className="credit-bar">
                <div className="credit-fill" style={{ width: `${((form.credit_score - 300) / 600) * 100}%` }} />
              </div>
              <span className="credit-label">
                {form.credit_score < 580 ? '🔴 Poor' :
                  form.credit_score < 650 ? '🟡 Fair' :
                  form.credit_score < 720 ? '🟢 Good' : '⭐ Excellent'}
              </span>
            </div>
          )}
        </div>

        <div className={`field ${errors.existing_monthly_debt ? 'error' : ''}`}>
          <label>Existing Monthly Debt Payments <span className="optional">(optional)</span></label>
          <div className="input-wrap">
            <span className="prefix">$</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="500"
              value={fmt(form.existing_monthly_debt)}
              onChange={set('existing_monthly_debt')}
            />
            <span className="suffix">/ mo</span>
          </div>
          <span className="hint">Car loans, student loans, credit cards</span>
        </div>
      </section>

      <section className="form-section">
        <h3>Property</h3>

        <div className={`field ${errors.property_value ? 'error' : ''}`}>
          <label>Property Value</label>
          <div className="input-wrap">
            <span className="prefix">$</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="750,000"
              value={fmt(form.property_value)}
              onChange={set('property_value')}
            />
            <span className="suffix">CAD</span>
          </div>
          {errors.property_value && <span className="err-msg">{errors.property_value}</span>}
        </div>

        <div className={`field ${errors.down_payment ? 'error' : ''}`}>
          <label>Down Payment {dpPct && <span className="pct-badge">{dpPct}%</span>}</label>
          <div className="input-wrap">
            <span className="prefix">$</span>
            <input
              type="text"
              inputMode="numeric"
              placeholder="150,000"
              value={fmt(form.down_payment)}
              onChange={set('down_payment')}
            />
            <span className="suffix">CAD</span>
          </div>
          {errors.down_payment && <span className="err-msg">{errors.down_payment}</span>}
          {dpPct && !errors.down_payment && (
            <span className={`hint ${parseFloat(dpPct) >= 20 ? 'green' : 'yellow'}`}>
              {parseFloat(dpPct) >= 20 ? '✅ No CMHC insurance required' : '📋 CMHC insurance will apply'}
            </span>
          )}
        </div>

        <div className="field-row">
          <div className="field">
            <label>Province</label>
            <select value={form.province} onChange={setSelect('province')}>
              {PROVINCES.map((p) => (
                <option key={p.code} value={p.code}>{p.code} — {p.name}</option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Property Type</label>
            <select value={form.property_type} onChange={setSelect('property_type')}>
              <option value="house">House</option>
              <option value="condo">Condo</option>
              <option value="townhouse">Townhouse</option>
            </select>
          </div>
        </div>
      </section>

      <section className="form-section">
        <h3>Mortgage Terms</h3>

        <div className="field">
          <label>Amortization Period</label>
          <div className="toggle-group">
            {['15', '20', '25', '30'].map((y) => (
              <button
                key={y}
                type="button"
                className={`toggle-btn ${form.amortization === y ? 'active' : ''}`}
                onClick={() => setForm((p) => ({ ...p, amortization: y }))}
              >
                {y} yr
              </button>
            ))}
          </div>
        </div>

        <div className="field">
          <label>Employment Type</label>
          <div className="employment-group">
            {[
              { value: 'salaried', label: '🏢 Salaried' },
              { value: 'self_employed', label: '💼 Self-Employed' },
              { value: 'contract', label: '📋 Contract' },
            ].map((opt) => (
              <button
                key={opt.value}
                type="button"
                className={`emp-btn ${form.employment_type === opt.value ? 'active' : ''}`}
                onClick={() => setForm((p) => ({ ...p, employment_type: opt.value }))}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </section>

      <div className="submit-wrap">
        <motion.button
          type="submit"
          className="submit-btn"
          disabled={loading}
          whileTap={{ scale: 0.98 }}
        >
          {loading ? 'Analysing…' : 'Analyse My Mortgage →'}
        </motion.button>
      </div>
    </form>
  );
}
