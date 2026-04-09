import React from 'react';
import { motion } from 'framer-motion';
import './Header.css';

export default function Header() {
  return (
    <header className="header">
      <motion.div
        className="header-inner"
        initial={{ opacity: 0, y: -16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: 'easeOut' }}
      >
        <div className="logo">
          <div className="logo-icon">
            {/* Maple leaf mark */}
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <rect width="36" height="36" rx="2" fill="#C8102E"/>
              <path
                d="M18 6 L20.2 12.5 L27 12.5 L21.4 16.5 L23.6 23 L18 19 L12.4 23 L14.6 16.5 L9 12.5 L15.8 12.5 Z"
                fill="white"
                opacity="0.95"
              />
            </svg>
          </div>
          <div>
            <h1>Mortgage<span>IQ</span></h1>
            <p>Canadian homebuying advisor</p>
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
