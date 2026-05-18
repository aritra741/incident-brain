import React from 'react';
import { motion } from 'framer-motion';
import { Brain, TrendingUp, CheckCircle, Clock, Radio } from 'lucide-react';

export default function PredictionBar({ predictions, currentIncident }) {
  if (!currentIncident) return null;

  const total = predictions.length;
  const correct = predictions.filter(p => p.outcome === 'correct').length;
  const latest = predictions[predictions.length - 1];
  const hasActive = predictions.some(p => !p.outcome);

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex items-center gap-4 px-5 py-2.5 rounded-xl"
      style={{
        background: total > 0
          ? 'linear-gradient(135deg, rgba(239,68,68,0.06), rgba(99,102,241,0.03))'
          : 'rgba(12,14,24,0.5)',
        border: `1px solid ${total > 0 ? 'rgba(239,68,68,0.18)' : 'var(--border)'}`,
        backdropFilter: 'blur(12px)',
      }}
    >
      <Brain size={14} style={{ color: total > 0 ? '#ef4444' : 'var(--accent-bright)' }} />
      <span className="text-[12px] font-bold">Cascade Prediction</span>
      {currentIncident.status === 'active' && (
        <span className="live-badge flex items-center gap-1">
          <Radio size={8} /> LIVE
        </span>
      )}
      <div className="flex-1" />
      {total > 0 && (
        <div className="flex items-center gap-4 text-[11px] font-medium" style={{ color: 'var(--text-muted)' }}>
          <span className="flex items-center gap-1.5 font-mono"><TrendingUp size={11} />{total}</span>
          {correct > 0 && <span className="flex items-center gap-1.5 font-mono" style={{ color: '#34d399' }}><CheckCircle size={11} />{correct}</span>}
          {latest?.time_to_failure_minutes && <span className="flex items-center gap-1.5 font-mono"><Clock size={11} />~{latest.time_to_failure_minutes}m</span>}
        </div>
      )}
      {total === 0 && currentIncident.status === 'active' && (
        <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>waiting for events...</span>
      )}
    </motion.div>
  );
}
