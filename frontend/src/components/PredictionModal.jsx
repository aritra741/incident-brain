import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  AlertTriangle, CheckCircle, XCircle, MessageSquare, Monitor, Eye, Clock,
  X, Activity, Zap, ShieldAlert, Radio
} from 'lucide-react';

const sourceIcons = { screenshot: Monitor, slack: MessageSquare, log: Eye };
const sourceColors = { screenshot: '#5eead4', slack: '#818cf8', log: '#fbbf24' };
const sourceGlows = { screenshot: 'rgba(20,184,166,0.4)', slack: 'rgba(129,140,248,0.4)', log: 'rgba(245,158,11,0.4)' };

function useCountUp(target, duration = 1200, decimals = 0, active = true) {
  const [value, setValue] = useState(0);
  useEffect(() => {
    if (!active) { setValue(0); return; }
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min((now - start) / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setValue(eased * target);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }, [target, duration, active]);
  return decimals > 0 ? value.toFixed(decimals) : Math.floor(value);
}

function TypewriterText({ text, delay = 0, speed = 22 }) {
  const [displayed, setDisplayed] = useState('');
  useEffect(() => {
    setDisplayed('');
    if (!text) return;
    let i = 0;
    const timer = setTimeout(() => {
      const interval = setInterval(() => {
        i++;
        setDisplayed(text.slice(0, i));
        if (i >= text.length) clearInterval(interval);
      }, speed);
      return () => clearInterval(interval);
    }, delay);
    return () => clearTimeout(timer);
  }, [text, delay, speed]);
  return <>{displayed}<span className="typing-cursor" /></>;
}

function SignalNode({ item, visible, isLast, index }) {
  const Icon = sourceIcons[item.source] || Eye;
  const color = sourceColors[item.source] || '#818cf8';
  const glow = sourceGlows[item.source] || 'rgba(129,140,248,0.4)';

  return (
    <motion.div
      initial={{ opacity: 0, x: -30 }}
      animate={visible ? { opacity: 1, x: 0 } : {}}
      transition={{ duration: 0.5, delay: index * 0.12, ease: [0.16, 1, 0.3, 1] }}
      className="flex gap-0"
    >
      <div className="flex flex-col items-center" style={{ width: 28, flexShrink: 0 }}>
        <motion.div
          initial={{ scale: 0 }}
          animate={visible ? { scale: 1 } : {}}
          transition={{ type: 'spring', stiffness: 400, damping: 15, delay: index * 0.12 + 0.05 }}
          className="w-3 h-3 rounded-full"
          style={{ background: color, boxShadow: `0 0 12px ${glow}` }}
        />
        {!isLast && (
          <motion.div
            initial={{ scaleY: 0 }}
            animate={visible ? { scaleY: 1 } : {}}
            transition={{ duration: 0.4, delay: index * 0.12 + 0.15 }}
            className="w-[2px] flex-1 origin-top"
            style={{ background: `linear-gradient(to bottom, ${color}60, transparent)`, minHeight: 24 }}
          />
        )}
      </div>

      <motion.div
        initial={{ opacity: 0, x: 16, scale: 0.96 }}
        animate={visible ? { opacity: 1, x: 0, scale: 1 } : {}}
        transition={{ duration: 0.45, delay: index * 0.12 + 0.08, ease: [0.16, 1, 0.3, 1] }}
        className="flex-1 min-w-0 pb-3 pl-3"
      >
        <div
          className="p-3.5 rounded-xl"
          style={{
            background: 'rgba(12,14,24,0.7)',
            border: `1px solid ${color}20`,
            backdropFilter: 'blur(12px)',
            boxShadow: `0 4px 20px rgba(0,0,0,0.2), inset 0 1px 0 ${color}08`,
          }}
        >
          <div className="flex items-center gap-2.5 mb-1.5">
            <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider" style={{ color }}>
              <Icon size={11} /> {item.source}
            </span>
            {item.timestamp && item.timestamp !== 'N/A' && (
              <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                {item.timestamp}
              </span>
            )}
          </div>
          <p className="text-[13px] font-medium leading-relaxed" style={{ color: 'var(--text-primary)' }}>
            {item.signal}
          </p>
        </div>
      </motion.div>
    </motion.div>
  );
}

function ConfidenceRing({ confidence, visible }) {
  const animated = useCountUp(confidence * 100, 1500, 0, visible);
  const circumference = 2 * Math.PI * 22;
  const offset = circumference - (animated / 100) * circumference;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.5 }}
      animate={visible ? { opacity: 1, scale: 1 } : {}}
      transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.3 }}
      className="relative w-[56px] h-[56px] flex items-center justify-center flex-shrink-0"
    >
      <svg width="56" height="56" className="-rotate-90">
        <circle cx="28" cy="28" r="22" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
        <motion.circle
          cx="28" cy="28" r="22"
          fill="none"
          stroke={confidence > 0.7 ? '#ef4444' : confidence > 0.4 ? '#f59e0b' : '#10b981'}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={visible ? { strokeDashoffset: offset } : {}}
          transition={{ duration: 1.5, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
          style={{ filter: `drop-shadow(0 0 6px ${confidence > 0.7 ? 'rgba(239,68,68,0.5)' : confidence > 0.4 ? 'rgba(245,158,11,0.5)' : 'rgba(16,185,129,0.5)'})` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[12px] font-bold font-mono" style={{ color: confidence > 0.7 ? '#ef4444' : confidence > 0.4 ? '#f59e0b' : '#10b981' }}>
          {visible ? animated : 0}%
        </span>
      </div>
    </motion.div>
  );
}

export default function PredictionModal({ prediction, incidentTitle, onClose, isOpen }) {
  const [step, setStep] = useState(0);
  const chain = prediction?.causal_chain || [];
  const confidence = prediction?.confidence || 0;
  const isCorrect = prediction?.outcome === 'correct';
  const isIncorrect = prediction?.outcome === 'incorrect';

  useEffect(() => {
    if (!isOpen || !prediction?.id) { setStep(0); return; }
    setStep(0);
    const timers = [];
    for (let i = 0; i <= chain.length + 2; i++) {
      timers.push(setTimeout(() => setStep(i + 1), i * 500 + 300));
    }
    return () => timers.forEach(clearTimeout);
  }, [prediction?.id, isOpen]);

  if (!isOpen || !prediction) return null;

  const showPrediction = step > chain.length;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-5"
      style={{
        background: 'rgba(3,4,10,0.88)',
        backdropFilter: 'blur(20px) saturate(0.8)',
        animation: 'fadeIn 0.3s ease forwards',
      }}
      onClick={onClose}
    >
      {/* Vignette overlay */}
      <div className="absolute inset-0 pointer-events-none" style={{
        background: 'radial-gradient(ellipse at center, transparent 0%, rgba(239,68,68,0.06) 100%)'
      }} />

      <div
        className="relative w-full max-w-[560px] max-h-[90vh] flex flex-col overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, #0c1018 0%, #070910 100%)',
          borderRadius: 20,
          border: '1px solid rgba(239,68,68,0.15)',
          boxShadow: '0 32px 80px rgba(0,0,0,0.6), 0 0 0 1px rgba(239,68,68,0.08), inset 0 1px 0 rgba(255,255,255,0.04)',
          animation: 'scaleIn 0.4s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Animated top border glow */}
        <div className="absolute top-0 left-4 right-4 h-[1px]" style={{
          background: 'linear-gradient(90deg, transparent, rgba(239,68,68,0.5), transparent)',
          opacity: showPrediction ? 1 : 0.3,
          transition: 'opacity 0.5s',
        }} />

        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-3 flex-shrink-0">
          <div className="flex items-center gap-3">
            <motion.div
              animate={{ rotate: [0, -8, 8, -4, 0] }}
              transition={{ duration: 0.6, delay: 0.2 }}
              className="w-9 h-9 rounded-xl flex items-center justify-center"
              style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.2)' }}
            >
              <ShieldAlert size={18} style={{ color: '#ef4444' }} />
            </motion.div>
            <div>
              <h2 className="text-[15px] font-bold font-display tracking-tight" style={{ color: '#f87171' }}>Cascade Alert</h2>
              <div className="flex items-center gap-1.5 mt-0.5">
                <Radio size={8} className="animate-pulse" style={{ color: '#ef4444' }} />
                <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>Neural Prediction Engine</span>
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-white/5 transition-colors"
            style={{ color: 'var(--text-muted)' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 pb-2 custom-scrollbar">
          {/* Signal Chain */}
          <div className="py-2">
            {chain.map((item, i) => (
              <SignalNode
                key={i}
                item={item}
                visible={step > i}
                isLast={i === chain.length - 1}
                index={i}
              />
            ))}

            {/* Prediction Node */}
            {showPrediction && (
              <div className="flex gap-0 mt-1" style={{ animation: 'fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards' }}>
                <div className="flex flex-col items-center" style={{ width: 28, flexShrink: 0 }}>
                  <motion.div
                    initial={{ scale: 0 }}
                    animate={{ scale: 1 }}
                    transition={{ type: 'spring', stiffness: 400, damping: 12 }}
                    className="w-3.5 h-3.5 rounded-full"
                    style={{
                      background: isCorrect ? '#10b981' : '#ef4444',
                      boxShadow: isCorrect ? '0 0 16px rgba(16,185,129,0.6)' : '0 0 16px rgba(239,68,68,0.6)',
                    }}
                  />
                </div>

                <div className="flex-1 min-w-0 pl-3">
                  <div
                    className="relative p-5 rounded-2xl overflow-hidden"
                    style={{
                      background: 'linear-gradient(135deg, rgba(239,68,68,0.06), rgba(12,14,24,0.8))',
                      border: isCorrect
                        ? '1px solid rgba(16,185,129,0.25)'
                        : '1px solid rgba(239,68,68,0.25)',
                      boxShadow: isCorrect
                        ? '0 8px 32px rgba(16,185,129,0.1), inset 0 1px 0 rgba(255,255,255,0.03)'
                        : '0 8px 32px rgba(239,68,68,0.12), inset 0 1px 0 rgba(255,255,255,0.03)',
                    }}
                  >
                    {/* Inner glow */}
                    <div className="absolute inset-0 pointer-events-none rounded-2xl" style={{
                      background: isCorrect
                        ? 'radial-gradient(ellipse at top right, rgba(16,185,129,0.08), transparent 70%)'
                        : 'radial-gradient(ellipse at top right, rgba(239,68,68,0.1), transparent 70%)',
                    }} />

                    <div className="relative z-10 flex items-start gap-4">
                      <ConfidenceRing confidence={confidence} visible={showPrediction} />

                      <div className="flex-1 min-w-0 pt-1">
                        <div className="flex items-center gap-2 mb-3">
                          {isCorrect ? (
                            <CheckCircle size={14} style={{ color: '#34d399' }} />
                          ) : isIncorrect ? (
                            <XCircle size={14} style={{ color: '#ef4444' }} />
                          ) : (
                            <AlertTriangle size={14} style={{ color: '#fbbf24' }} />
                          )}
                          <span className="text-[10px] font-bold uppercase tracking-widest" style={{ color: 'var(--text-muted)' }}>
                            {isCorrect ? 'Confirmed' : isIncorrect ? 'Incorrect' : 'Predicted Failure'}
                          </span>
                        </div>

                        <h3 className="text-[15px] font-bold leading-snug mb-3" style={{ color: 'var(--text-primary)' }}>
                          <TypewriterText text={prediction.predicted_failure} delay={200} speed={18} />
                        </h3>

                        <div className="flex flex-wrap items-center gap-3 mb-4">
                          <span
                            className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-[11px] font-bold font-mono"
                            style={{
                              background: confidence > 0.7 ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)',
                              color: confidence > 0.7 ? '#f87171' : '#fbbf24',
                              border: `1px solid ${confidence > 0.7 ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
                            }}
                          >
                            <Activity size={10} />
                            {Math.round(confidence * 100)}% confidence
                          </span>
                          {prediction.time_to_failure_minutes !== null && (
                            <span className="flex items-center gap-1.5 text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                              <Clock size={10} /> ~{prediction.time_to_failure_minutes} min to failure
                            </span>
                          )}
                          {prediction.outcome && (
                            <span
                              className="text-[10px] font-extrabold uppercase tracking-widest px-2.5 py-0.5 rounded-md"
                              style={{
                                background: isCorrect ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                color: isCorrect ? '#34d399' : '#f87171',
                              }}
                            >
                              {prediction.outcome}
                            </span>
                          )}
                        </div>

                        {prediction.suggested_action && (
                          <div
                            className="relative p-4 rounded-xl"
                            style={{
                              background: 'rgba(245,158,11,0.04)',
                              border: '1px solid rgba(245,158,11,0.15)',
                              borderLeft: '3px solid #f59e0b',
                              animation: 'fadeInUp 0.5s cubic-bezier(0.16, 1, 0.3, 1) 0.8s both',
                            }}
                          >
                            <div className="flex items-center gap-2 mb-2">
                              <Zap size={11} style={{ color: '#fbbf24' }} />
                              <span className="text-[9px] font-bold uppercase tracking-widest" style={{ color: '#fbbf24' }}>Recommended Action</span>
                            </div>
                            <p className="text-[12px] font-medium leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                              {prediction.suggested_action}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Fallback when no chain */}
            {chain.length === 0 && showPrediction && (
              <div className="relative p-5 rounded-2xl overflow-hidden mt-2" style={{ animation: 'fadeInUp 0.5s forwards' }}>
                <div className="relative z-10 flex items-start gap-4">
                  <ConfidenceRing confidence={confidence} visible={showPrediction} />
                  <div className="flex-1 min-w-0 pt-1">
                    <h3 className="text-[15px] font-bold leading-snug mb-3">
                      <TypewriterText text={prediction.predicted_failure} delay={200} speed={18} />
                    </h3>
                    <div className="flex flex-wrap items-center gap-3 mb-4">
                      <span className="tag tag-warning">{Math.round(confidence * 100)}% confidence</span>
                      {prediction.time_to_failure_minutes !== null && (
                        <span className="flex items-center gap-1 text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                          <Clock size={10} /> ~{prediction.time_to_failure_minutes} min
                        </span>
                      )}
                    </div>
                    {prediction.suggested_action && (
                      <div className="p-4 rounded-xl" style={{ background: 'rgba(245,158,11,0.04)', border: '1px solid rgba(245,158,11,0.15)', borderLeft: '3px solid #f59e0b' }}>
                        <p className="text-[12px] font-medium" style={{ color: 'var(--text-secondary)' }}>{prediction.suggested_action}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        {incidentTitle && (
          <div
            className="px-6 py-3 flex-shrink-0 text-center font-mono text-[11px] font-medium"
            style={{
              color: 'var(--text-muted)',
              borderTop: '1px solid rgba(255,255,255,0.04)',
              background: 'rgba(6,8,12,0.5)',
            }}
          >
            {incidentTitle}
          </div>
        )}
      </div>
    </div>
  );
}
