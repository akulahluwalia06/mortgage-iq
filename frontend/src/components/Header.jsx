import React, { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import './Header.css';

export default function Header() {
  return (
    <header className="header">
      <motion.div
        className="header-inner"
        initial={{ opacity: 0, y: -24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
      >
        <div className="logo">
          <div className="logo-icon">
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
              <polygon points="16,2 30,28 2,28" fill="none" stroke="url(#tri)" strokeWidth="1.5" strokeLinejoin="round"/>
              <circle cx="16" cy="18" r="4" fill="url(#dot)" opacity="0.9"/>
              <defs>
                <linearGradient id="tri" x1="2" y1="28" x2="30" y2="2" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stopColor="#00d4ff"/>
                  <stop offset="100%" stopColor="#7c3aed"/>
                </linearGradient>
                <radialGradient id="dot" cx="50%" cy="50%">
                  <stop offset="0%" stopColor="#00d4ff"/>
                  <stop offset="100%" stopColor="#7c3aed"/>
                </radialGradient>
              </defs>
            </svg>
          </div>
          <div>
            <h1>MortgageIQ</h1>
            <p>Canada's intelligent homebuying advisor</p>
          </div>
        </div>

        <nav className="header-nav">
          <span className="nav-pill">🍁 Canada</span>
          <span className="nav-pill live">
            <span className="live-dot" />
            Live Analysis
          </span>
        </nav>
      </motion.div>
    </header>
  );
}
