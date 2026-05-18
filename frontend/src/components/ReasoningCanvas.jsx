import React, { useState, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Brain, Eye, MessageSquare, Monitor, AlertTriangle, CheckCircle, XCircle, Clock, TrendingUp, Zap } from 'lucide-react';

const sourceIcons = {
  screenshot: Monitor,
  slack: MessageSquare,
  log: Eye,
};

const sourceColors = {
  screenshot: '#5eead4',
  slack: '#a5b4fc',
  log: '#fbbf24',
};

function truncate(str, maxLen = 55) {
  if (!str) return '';
  return str.length > maxLen ? str.slice(0, maxLen) + '...' : str;
}

function PredictionNode({ prediction, index }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), index * 300 + 150);
    return () => clearTimeout(t);
  }, [index]);

  const confidence = prediction.confidence || 0;
  const isCorrect = prediction.outcome === 'correct';
  const isIncorrect = prediction.outcome === 'incorrect';

  return (
    <div
      className={`prediction-node ${visible ? 'visible' : ''} ${isCorrect ? 'correct' : ''} ${isIncorrect ? 'incorrect' : ''}`}
    >
      <div className="prediction-node-inner">
        <div className="prediction-icon">
          {isCorrect ? <CheckCircle size={16} /> : isIncorrect ? <XCircle size={16} /> : <AlertTriangle size={16} />}
        </div>
        <div className="prediction-content">
          <div className="prediction-title">{truncate(prediction.predicted_failure, 50)}</div>
          <div className="prediction-meta">
            <span className="confidence">{(confidence * 100).toFixed(0)}% confidence</span>
            {prediction.time_to_failure_minutes !== null && (
              <span className="time-estimate">~{prediction.time_to_failure_minutes} min</span>
            )}
          </div>
          {prediction.suggested_action && (
            <div className="suggested-action" title={prediction.suggested_action}>
              {truncate(prediction.suggested_action, 70)}
            </div>
          )}
          {prediction.outcome && (
            <div className={`outcome-badge ${prediction.outcome}`}>
              {prediction.outcome.toUpperCase()}
              {prediction.actual_time_to_failure_minutes !== null && (
                <span> · actual: {prediction.actual_time_to_failure_minutes}m</span>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SignalNode({ item, index }) {
  const [visible, setVisible] = useState(false);
  const Icon = sourceIcons[item.source] || Eye;
  const color = sourceColors[item.source] || '#818cf8';

  useEffect(() => {
    const t = setTimeout(() => setVisible(true), index * 250);
    return () => clearTimeout(t);
  }, [index]);

  return (
    <div className={`signal-node ${visible ? 'visible' : ''}`}>
      <div className="signal-icon" style={{ background: `${color}20`, color }}>
        <Icon size={12} />
      </div>
      <div className="signal-content">
        <div className="signal-text" title={item.signal}>{truncate(item.signal, 65)}</div>
        <div className="signal-source">
          <span style={{ color }}>{item.source}</span>
          {item.timestamp && item.timestamp !== 'N/A' && <span className="signal-time">{item.timestamp}</span>}
        </div>
      </div>
    </div>
  );
}

function ConnectionArrow({ index }) {
  const [drawn, setDrawn] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDrawn(true), index * 250 + 200);
    return () => clearTimeout(t);
  }, [index]);

  return (
    <div className={`connection-arrow ${drawn ? 'drawn' : ''}`}>
      <svg width="20" height="28" viewBox="0 0 20 28">
        <line x1="10" y1="0" x2="10" y2="28" stroke="rgba(99,102,241,0.35)" strokeWidth="2" strokeDasharray="3 3" />
        <polygon points="10,28 5,20 15,20" fill="rgba(99,102,241,0.35)" />
      </svg>
    </div>
  );
}

export default function ReasoningCanvas({ predictions, currentIncident, onPredictNow }) {
  const contentRef = useRef(null);
  const prevCountRef = useRef(predictions.length);

  useEffect(() => {
    if (predictions.length > prevCountRef.current && contentRef.current) {
      contentRef.current.scrollTop = contentRef.current.scrollHeight;
    }
    prevCountRef.current = predictions.length;
  }, [predictions.length]);

  const activePredictions = predictions.filter(p => !p.outcome);
  const resolvedPredictions = predictions.filter(p => p.outcome);

  const stats = {
    total: predictions.length,
    correct: predictions.filter(p => p.outcome === 'correct').length,
    avgTime: predictions.filter(p => p.outcome === 'correct' && p.actual_time_to_failure_minutes !== null).length > 0
      ? (predictions
          .filter(p => p.outcome === 'correct' && p.actual_time_to_failure_minutes !== null)
          .reduce((acc, p) => acc + Math.abs(p.time_to_failure_minutes - p.actual_time_to_failure_minutes), 0)
        / predictions.filter(p => p.outcome === 'correct' && p.actual_time_to_failure_minutes !== null).length).toFixed(1)
      : null,
  };

  const predictionWord = stats.total === 1 ? 'prediction' : 'predictions';

  if (!currentIncident) {
    return (
      <div className="reasoning-canvas empty">
        <div className="canvas-grid" />
        <div className="empty-state flex flex-col items-center gap-3">
          <Brain size={24} className="pulse" style={{ color: 'var(--accent-bright)' }} />
          <p className="text-[12px] font-medium" style={{ color: 'var(--text-muted)' }}>No active incident</p>
        </div>
      </div>
    );
  }

  return (
    <div className="reasoning-canvas">
      <div className="canvas-grid" />

      <div className="canvas-header">
        <div className="canvas-title">
          <Brain size={14} />
          <span>Cascade Prediction</span>
          {currentIncident.status === 'active' && <span className="live-badge">LIVE</span>}
        </div>
        <div className="flex items-center gap-3">
          {stats.total > 0 && (
            <div className="scorecard">
              <div className="score-item">
                <TrendingUp size={11} />
                <span>{stats.total} {predictionWord}</span>
              </div>
              {stats.correct > 0 && (
                <div className="score-item correct">
                  <CheckCircle size={11} />
                  <span>{stats.correct} correct</span>
                </div>
              )}
              {stats.avgTime !== null && (
                <div className="score-item">
                  <Clock size={11} />
                  <span>±{stats.avgTime}m</span>
                </div>
              )}
            </div>
          )}
          {currentIncident.status === 'active' && onPredictNow && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onPredictNow}
              className="predict-now-btn"
              title="Force a prediction now"
            >
              <Zap size={12} />
              <span>Predict</span>
            </motion.button>
          )}
        </div>
      </div>

      <div className="canvas-content" ref={contentRef}>
        {predictions.length === 0 ? (
          <div className="canvas-waiting">
            <div className="pulse-node">
              <Brain size={20} />
            </div>
            <p className="text-[13px] font-medium">Watching signals...</p>
            <p className="sub">Add events to trigger predictions</p>
          </div>
        ) : (
          <div className="predictions-list">
            {activePredictions.map((p, i) => (
              <div key={p.id || i} className="prediction-block active">
                {p.causal_chain?.map((item, ci) => (
                  <React.Fragment key={ci}>
                    <SignalNode item={item} index={ci} />
                    {ci < p.causal_chain.length - 1 && <ConnectionArrow index={ci} />}
                  </React.Fragment>
                ))}
                {p.causal_chain && p.causal_chain.length > 0 && <ConnectionArrow index={p.causal_chain.length} />}
                <PredictionNode prediction={p} index={0} />
              </div>
            ))}

            {resolvedPredictions.slice(-2).map((p, i) => (
              <div key={p.id || i} className="prediction-block resolved">
                <PredictionNode prediction={p} index={i} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
