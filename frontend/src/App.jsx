import React, { useState, useEffect, useCallback, useRef } from 'react';
import { format, formatDistanceToNow } from 'date-fns';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Brain, AlertTriangle, CheckCircle, Clock, Zap, Activity, Send, Image, Loader2,
  X, ChevronRight, MessageSquare, Monitor, Lightbulb, Eye, FileText, Download,
  Database, Plus, Sparkles, ArrowRight, TrendingUp, Shield, Users, Play,
  Terminal, Radio, Flame
} from 'lucide-react';
import { incidentService, eventService, postmortemService, demoService, predictionService } from './services/api';
import wsService from './services/websocket';
import ParticleField from './components/ParticleField';
import PredictionBar from './components/PredictionBar';
import PredictionModal from './components/PredictionModal';
import ScreenFlash from './components/ScreenFlash';

const typeConfig = {
  action: { icon: Zap, color: '#60a5fa', glow: 'rgba(59,130,246,0.35)', label: 'Action' },
  hypothesis: { icon: Lightbulb, color: '#c084fc', glow: 'rgba(168,85,247,0.35)', label: 'Hypothesis' },
  observation: { icon: Eye, color: '#fbbf24', glow: 'rgba(245,158,11,0.35)', label: 'Observation' },
  outcome: { icon: CheckCircle, color: '#34d399', glow: 'rgba(16,185,129,0.35)', label: 'Outcome' },
  intervention: { icon: Brain, color: '#f87171', glow: 'rgba(239,68,68,0.35)', label: 'Intervention' },
};

const sourceConfig = {
  slack: { icon: MessageSquare, color: '#a5b4fc', label: 'Slack' },
  screen: { icon: Monitor, color: '#5eead4', label: 'Screen' },
  agent: { icon: Brain, color: '#f87171', label: 'Agent' },
};

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.04, delayChildren: 0.05 } },
};

const itemVariants = {
  hidden: { opacity: 0, y: 14, scale: 0.98 },
  visible: { opacity: 1, y: 0, scale: 1, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] } },
};

const tabContentVariants = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.16, 1, 0.3, 1] } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.18 } },
};

export default function App() {
  const [incidents, setIncidents] = useState([]);
  const [currentIncident, setCurrentIncident] = useState(null);
  const [events, setEvents] = useState([]);
  const [predictions, setPredictions] = useState([]);
  const [postmortem, setPostmortem] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('timeline');
  const [showNewModal, setShowNewModal] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [replaying, setReplaying] = useState(false);
  const [toast, setToast] = useState(null);
  const [predictionModal, setPredictionModal] = useState(null);
  const [aiAnalysis, setAiAnalysis] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [flashTrigger, setFlashTrigger] = useState(0);
  const contentRef = useRef(null);
  const seenPredictionIds = useRef(new Set());
  const dismissedPredictionIds = useRef(new Set());
  const lastModalCloseTime = useRef(0);
  const hasAutoShownPredictionModal = useRef(false);
  const parseSafeDate = useCallback((value) => {
    if (!value) return null;
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? null : d;
  }, []);

  const fetchIncidents = useCallback(async () => {
    try {
      const data = await incidentService.list();
      const normalized = Array.isArray(data) ? data : [];
      setIncidents(normalized);
    } catch (e) { console.error(e); }
  }, []);

  // Reset seen/dismissed predictions when switching incidents
  useEffect(() => {
    seenPredictionIds.current = new Set();
    dismissedPredictionIds.current = new Set();
    hasAutoShownPredictionModal.current = false;
    setPredictionModal(null);
  }, [currentIncident?.id]);

  const mergePredictions = useCallback((prev, incoming) => {
    const list = Array.isArray(incoming) ? incoming : [incoming];
    const map = new Map((prev || []).map(p => [p.id, p]));
    for (const p of list) {
      if (!p?.id) continue;
      map.set(p.id, { ...(map.get(p.id) || {}), ...p });
    }
    return Array.from(map.values()).sort((a, b) => {
      const ta = new Date(a.created_at || 0).getTime();
      const tb = new Date(b.created_at || 0).getTime();
      return ta - tb;
    });
  }, []);

  const openPredictionModal = useCallback((p) => {
    if (!p?.id) return;
    if (hasAutoShownPredictionModal.current) return;
    // Don't reopen dismissed predictions
    if (dismissedPredictionIds.current.has(p.id)) return;
    // Don't reopen within 2s of closing (prevents flicker)
    if (Date.now() - lastModalCloseTime.current < 2000) return;
    // Don't reopen already-seen predictions
    if (seenPredictionIds.current.has(p.id)) return;

    seenPredictionIds.current.add(p.id);
    hasAutoShownPredictionModal.current = true;
    setPredictionModal(p);
    setFlashTrigger(prev => prev + 1);
  }, []);

  const closePredictionModal = useCallback(() => {
    if (predictionModal?.id) {
      dismissedPredictionIds.current.add(predictionModal.id);
    }
    lastModalCloseTime.current = Date.now();
    setPredictionModal(null);
  }, [predictionModal]);

  // Polling for predictions — only open modal for the newest unseen prediction
  useEffect(() => {
    if (!currentIncident) return;

    const poll = async () => {
      try {
        const preds = await predictionService.getByIncident(currentIncident.id);
        setPredictions(prev => mergePredictions(prev, preds));
        // Find the last (newest) prediction that hasn't been seen or dismissed
        const unseen = preds.filter(p => p.id && !seenPredictionIds.current.has(p.id) && !dismissedPredictionIds.current.has(p.id));
        if (unseen.length > 0) {
          openPredictionModal(unseen[unseen.length - 1]);
        }
      } catch (e) { /* ignore */ }
    };

    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, [currentIncident?.id, openPredictionModal, mergePredictions]);

  // WebSocket listeners (global, runs once)
  useEffect(() => {
    fetchIncidents();
    wsService.connect().catch(() => {});
    const unsubEvent = wsService.on('event', (d) => setEvents(prev => [...prev, d.data]));
    const unsubPrediction = wsService.on('prediction', (d) => {
      setPredictions(prev => mergePredictions(prev, d.data));
      openPredictionModal(d.data);
    });
    const unsubWarning = wsService.on('warning', (d) => {
      if (d?.data?.warning_message) {
        setToast({ message: d.data.warning_message, type: 'error' });
        setTimeout(() => setToast(null), 6000);
      }
    });
    const unsubIntervention = wsService.on('intervention', (d) => {
      if (d?.data?.event) {
        setEvents(prev => [...prev, d.data.event]);
      }
      if (d?.data?.message) {
        setToast({ message: 'Incident Brain posted a co-responder recommendation.', type: 'info' });
        setTimeout(() => setToast(null), 5000);
      }
    });
    const unsubPm = wsService.on('postmortem', (d) => setPostmortem(d.data));
    const unsubStatus = wsService.on('status_update', (d) => {
      if (d.data?.status === 'resolved') {
        setCurrentIncident(prev => prev ? { ...prev, status: 'resolved' } : prev);
      }
    });
    return () => { unsubEvent(); unsubPrediction(); unsubWarning(); unsubIntervention(); unsubPm(); unsubStatus(); wsService.disconnect(); };
  }, [fetchIncidents, openPredictionModal, mergePredictions]);

  const selectIncident = useCallback(async (id) => {
    setLoading(true);
    try {
      const incident = await incidentService.get(id);
      setCurrentIncident(incident);
      wsService.subscribeToIncident(id);
      const evts = await eventService.getByIncident(id);
      setEvents(evts);
      try { const pm = await postmortemService.get(id); setPostmortem(pm); } catch { setPostmortem(null); }
      setActiveTab('timeline');
      setAiAnalysis(null);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const createIncident = async (title) => {
    setLoading(true);
    try {
      const incident = await incidentService.create({ title });
      setIncidents(prev => [incident, ...prev]);
      setCurrentIncident(incident);
      setEvents([]); setPredictions([]); setPostmortem(null);
      setShowNewModal(false);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const seedDemo = async () => {
    setSeeding(true);
    try {
      await demoService.seed();
      await fetchIncidents();
    } catch (e) { console.error(e); }
    finally { setSeeding(false); }
  };

  const startReplay = async () => {
    setReplaying(true);
    try {
      const result = await demoService.replay();
      if (result.incident_id) {
        await fetchIncidents();
        setToast({
          message: 'Demo replay started. Click the new incident in the sidebar.',
          type: 'info',
        });
        setTimeout(() => setToast(null), 5000);
      }
    } catch (e) { console.error(e); }
    finally { setReplaying(false); }
  };

  const deleteIncident = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm('Delete this incident and all its events?')) return;
    try {
      await incidentService.delete(id);
      setIncidents(prev => prev.filter(i => i.id !== id));
      if (currentIncident?.id === id) {
        setCurrentIncident(null);
        setEvents([]);
        setPredictions([]);
        setPostmortem(null);
      }
    } catch (e) { console.error(e); }
  };

  const submitEvent = async (text) => {
    if (!currentIncident) return;
    try {
      const result = await eventService.createText(currentIncident.id, text);
      if (result.events) {
        setEvents(prev => [...prev, ...result.events]);
      }
    } catch (e) { console.error(e); }
  };

  const submitImage = async (file) => {
    if (!currentIncident) return;
    try { await eventService.createImage(currentIncident.id, file); } catch (e) { console.error(e); }
  };

  const resolveIncident = async () => {
    if (!currentIncident) return;
    setLoading(true);
    try {
      await incidentService.resolve(currentIncident.id);
      setCurrentIncident(prev => ({ ...prev, status: 'resolved' }));
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const generatePostmortem = async () => {
    if (!currentIncident) return;
    setLoading(true);
    try {
      const pm = await postmortemService.generate(currentIncident.id);
      setPostmortem(pm);
      setActiveTab('postmortem');
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const exportMarkdown = async () => {
    if (!currentIncident) return;
    try {
      const md = await postmortemService.exportMarkdown(currentIncident.id);
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a'); a.href = url; a.download = `postmortem.md`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { console.error(e); }
  };

  const stats = {
    total: events.length,
    actions: events.filter(e => e.type === 'action').length,
    observations: events.filter(e => e.type === 'observation').length,
    predictions: predictions.length,
  };

  const runAiAnalysis = async () => {
    if (!currentIncident) return;
    setAnalyzing(true);
    try {
      const result = await eventService.getAnalysis(currentIncident.id);
      setAiAnalysis(result.analysis);
      setActiveTab('analysis');
    } catch (e) { console.error(e); }
    finally { setAnalyzing(false); }
  };

  return (
    <div className="h-screen flex flex-col relative" style={{ background: 'var(--bg-primary)' }}>
      <ParticleField />
      <ScreenFlash trigger={flashTrigger} />
      <div className="scanlines" />

      {/* Ambient gradient blobs */}
      <div className="gradient-blob" style={{ width: 500, height: 500, background: '#6366f1', top: '-10%', left: '-5%' }} />
      <div className="gradient-blob" style={{ width: 400, height: 400, background: '#a855f7', bottom: '-5%', right: '-5%', opacity: 0.1 }} />

      {/* Header */}
      <motion.header
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="px-6 py-3.5 flex items-center justify-between relative z-10"
        style={{ background: 'linear-gradient(180deg, rgba(10,12,20,0.95) 0%, rgba(10,12,20,0.7) 100%)', borderBottom: '1px solid var(--border)', backdropFilter: 'blur(20px)' }}
      >
        <div className="flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-xl flex items-center justify-center relative" style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 4px 20px rgba(99,102,241,0.35)' }}>
            <Brain size={20} className="text-white" />
            <div className="absolute inset-0 rounded-xl" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.2)' }} />
          </div>
          <div>
            <h1 className="text-[15px] font-bold tracking-tight font-display">Incident Brain</h1>
            <div className="flex items-center gap-1.5 mt-0.5">
              <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" style={{ boxShadow: '0 0 6px rgba(52,211,153,0.6)' }} />
              <p className="text-[11px] font-medium" style={{ color: 'var(--text-muted)' }}>Cascade Prediction Engine Online</p>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {incidents.length === 0 && (
            <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={seedDemo} disabled={seeding} className="btn btn-ghost text-[12px]">
              {seeding ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
              Load Demo Data
            </motion.button>
          )}
          {currentIncident && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="flex items-center gap-2.5 px-4 py-2 rounded-xl"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', backdropFilter: 'blur(12px)' }}
            >
              <span className={`status-dot ${currentIncident.status}`} />
              <span className="text-[12px] font-semibold max-w-[220px] truncate">{currentIncident.title}</span>
              {currentIncident.status === 'active' && <span className="live-badge">LIVE</span>}
            </motion.div>
          )}
        </div>
      </motion.header>

      <div className="flex-1 flex overflow-hidden relative z-10">
        {/* Sidebar */}
        <motion.aside
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: [0.16, 1, 0.3, 1] }}
          className="w-72 flex flex-col overflow-hidden"
          style={{ borderRight: '1px solid var(--border)', background: 'linear-gradient(180deg, rgba(10,12,20,0.9) 0%, rgba(6,8,14,0.8) 100%)', backdropFilter: 'blur(20px)' }}
        >
          <div className="p-4 flex items-center justify-between" style={{ borderBottom: '1px solid var(--border)' }}>
            <span className="text-[11px] font-bold uppercase tracking-widest font-display" style={{ color: 'var(--text-muted)' }}>Incidents</span>
            <motion.button whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }} onClick={() => setShowNewModal(true)} className="btn btn-primary text-[11px] py-1.5 px-3">
              <Plus size={13} /> New
            </motion.button>
          </div>
          <div className="flex-1 overflow-y-auto p-2.5 space-y-1.5">
            {incidents.length === 0 ? (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-14 px-4">
                <div className="w-14 h-14 rounded-2xl flex items-center justify-center mx-auto mb-4" style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.12)' }}>
                  <Database size={24} style={{ color: 'var(--text-muted)' }} />
                </div>
                <p className="text-[12px] font-medium" style={{ color: 'var(--text-muted)' }}>No incidents yet</p>
                <button onClick={seedDemo} disabled={seeding} className="btn btn-ghost text-[11px] mt-4 w-full">
                  {seeding ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
                  Load Demo
                </button>
              </motion.div>
            ) : (
              <div className="space-y-1.5">
                {incidents.map((inc) => (
                  <button
                    key={inc.id}
                    onClick={() => selectIncident(inc.id)}
                    className={`w-full text-left p-3.5 rounded-xl transition-all group relative ${currentIncident?.id === inc.id ? '' : 'hover:opacity-90'}`}
                    style={{
                      background: currentIncident?.id === inc.id ? 'linear-gradient(135deg, rgba(99,102,241,0.12), rgba(168,85,247,0.06))' : 'transparent',
                      border: currentIncident?.id === inc.id ? '1px solid rgba(99,102,241,0.25)' : '1px solid transparent',
                      boxShadow: currentIncident?.id === inc.id ? '0 4px 20px rgba(99,102,241,0.1)' : 'none',
                    }}
                  >
                    <div className="flex items-center gap-2.5 mb-2">
                      <span className={`status-dot ${inc.status}`} />
                      <span className="text-[13px] font-semibold truncate pr-6" style={{ color: 'var(--text-primary)' }}>{inc.title || 'Untitled incident'}</span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      <span className="flex items-center gap-1 font-mono">
                        <Clock size={10} />
                        {(() => {
                          const d = parseSafeDate(inc.started_at);
                          return d ? format(d, 'MMM d, HH:mm') : 'Unknown start';
                        })()}
                      </span>
                      <span className={`tag ${inc.status === 'active' ? 'tag-warning' : 'tag-outcome'}`} style={{ fontSize: 9, padding: '1px 7px' }}>{inc.status || 'unknown'}</span>
                    </div>
                    <button onClick={(e) => deleteIncident(inc.id, e)}
                      className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-red-900/30"
                      title="Delete incident">
                      <X size={12} style={{ color: '#ef4444' }} />
                    </button>
                  </button>
                ))}
              </div>
            )}
          </div>
        </motion.aside>

        {/* Main */}
        <main className="flex-1 flex flex-col overflow-hidden relative">
          {currentIncident ? (
            <>
              {/* Stats bar */}
              <motion.div
                initial={{ opacity: 0, y: -8 }}
                animate={{ opacity: 1, y: 0 }}
                className="px-6 py-4 flex items-center gap-4"
                style={{ borderBottom: '1px solid var(--border)' }}
              >
                <div className="flex-1">
                  <h2 className="text-[18px] font-bold font-display tracking-tight">{currentIncident.title}</h2>
                  <p className="text-[11px] mt-1 font-mono" style={{ color: 'var(--text-muted)' }}>
                    <span style={{ color: 'var(--accent-bright)' }}>#</span>{currentIncident.id?.slice(0, 8)}
                    {(() => {
                      const started = parseSafeDate(currentIncident.started_at);
                      const resolved = parseSafeDate(currentIncident.resolved_at);
                      const startedTxt = started ? ` · Started ${formatDistanceToNow(started)} ago` : '';
                      const resolvedTxt = resolved ? ` · Resolved ${formatDistanceToNow(resolved)} ago` : '';
                      return `${startedTxt}${resolvedTxt}`;
                    })()}
                  </p>
                </div>
                <div className="flex gap-3">
                  {[
                    { label: 'Events', value: stats.total, icon: Activity, color: '#818cf8', glow: 'rgba(129,140,248,0.2)' },
                    { label: 'Actions', value: stats.actions, icon: Zap, color: '#60a5fa', glow: 'rgba(96,165,250,0.2)' },
                    { label: 'Predictions', value: stats.predictions, icon: Brain, color: '#a78bfa', glow: 'rgba(167,139,250,0.2)' },
                  ].map((s, i) => (
                    <motion.div
                      key={s.label}
                      initial={{ opacity: 0, y: -10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.1 + i * 0.06 }}
                      className="stat-hud flex items-center gap-3"
                      style={{ minWidth: '110px' }}
                    >
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center" style={{ background: `${s.color}12` }}>
                        <s.icon size={16} style={{ color: s.color }} />
                      </div>
                      <div>
                        <div className="stat-value" style={{ color: s.color, textShadow: `0 0 20px ${s.glow}` }}>{s.value}</div>
                        <div className="stat-label">{s.label}</div>
                      </div>
                    </motion.div>
                  ))}
                </div>
              </motion.div>

              {/* Prediction Bar */}
              <div className="px-6 pt-4">
                <PredictionBar predictions={predictions} currentIncident={currentIncident} />
              </div>

              {/* Tabs */}
              <div className="px-6 flex gap-1 mt-4" style={{ borderBottom: '1px solid var(--border)' }}>
                {[
                  { id: 'timeline', label: 'Live Timeline', icon: Activity },
                  { id: 'analysis', label: 'AI Analysis', icon: Brain },
                  { id: 'postmortem', label: 'Post-Mortem', icon: FileText },
                ].map((tab, i) => (
                  <motion.button
                    key={tab.id}
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 + i * 0.05 }}
                    onClick={() => setActiveTab(tab.id)}
                    className="flex items-center gap-2 px-5 py-3 text-[13px] font-semibold transition-colors relative"
                    style={{ color: activeTab === tab.id ? 'var(--accent-bright)' : 'var(--text-muted)' }}
                  >
                    <tab.icon size={14} />
                    {tab.label}
                    {activeTab === tab.id && (
                      <motion.div layoutId="activeTab" className="absolute bottom-0 left-2 right-2 h-[2px] rounded-full" style={{ background: 'linear-gradient(90deg, var(--accent), var(--purple))' }} />
                    )}
                  </motion.button>
                ))}
              </div>

              {/* Content */}
              <div className="flex-1 overflow-y-auto p-6 relative" ref={contentRef}>
                <AnimatePresence mode="wait">
                  {loading ? (
                    <motion.div key="loader" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex items-center justify-center h-full">
                      <div className="flex flex-col items-center gap-4">
                        <div className="pulse-node">
                          <Brain size={24} style={{ color: 'var(--accent-bright)' }} />
                        </div>
                        <span className="text-[12px] font-mono" style={{ color: 'var(--text-muted)' }}>Processing...</span>
                      </div>
                    </motion.div>
                  ) : (
                    <motion.div
                      key={activeTab}
                      variants={tabContentVariants}
                      initial="hidden"
                      animate="visible"
                      exit="exit"
                    >
                      {activeTab === 'timeline' ? (
                        <TimelineView events={events} predictions={predictions} />
                      ) : activeTab === 'analysis' ? (
                        <AiAnalysisView analysis={aiAnalysis} onAnalyze={runAiAnalysis} analyzing={analyzing} />
                      ) : (
                        <PostMortemView postmortem={postmortem} onExport={exportMarkdown} />
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Bottom bar */}
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="px-6 py-4 relative z-10"
                style={{ borderTop: '1px solid var(--border)', background: 'linear-gradient(180deg, rgba(10,12,20,0.6) 0%, rgba(6,8,14,0.9) 100%)', backdropFilter: 'blur(20px)' }}
              >
                {currentIncident.status === 'active' ? (
                  <div className="max-w-3xl mx-auto space-y-3">
                    <EventInput onSubmit={submitEvent} onSubmitImage={submitImage} disabled={loading} />
                    <div className="flex justify-end gap-2">
                      <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={resolveIncident} className="btn btn-danger text-[12px]" disabled={loading}>
                        <CheckCircle size={14} /> Resolve Incident
                      </motion.button>
                    </div>
                  </div>
                ) : (
                  <div className="max-w-3xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <div className="w-8 h-8 rounded-lg flex items-center justify-center" style={{ background: 'rgba(16,185,129,0.12)' }}>
                        <CheckCircle size={16} style={{ color: '#34d399' }} />
                      </div>
                      <span className="text-[13px] font-medium" style={{ color: 'var(--text-secondary)' }}>Incident resolved</span>
                    </div>
                    <div className="flex gap-2">
                      {postmortem && (
                        <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={exportMarkdown} className="btn btn-ghost text-[12px]">
                          <Download size={14} /> Export
                        </motion.button>
                      )}
                      <motion.button whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} onClick={generatePostmortem} className="btn btn-primary text-[12px]" disabled={loading || !!postmortem}>
                        {postmortem ? <><Sparkles size={14} /> Generated</> : <><Sparkles size={14} /> Generate Post-Mortem</>}
                      </motion.button>
                    </div>
                  </div>
                )}
              </motion.div>
            </>
          ) : (
            <EmptyState onNew={() => setShowNewModal(true)} onSeed={seedDemo} onReplay={startReplay} seeding={seeding} replaying={replaying} />
          )}
        </main>
      </div>

      <AnimatePresence>
        {showNewModal && <NewIncidentModal onClose={() => setShowNewModal(false)} onCreate={createIncident} />}
      </AnimatePresence>

      <PredictionModal
        prediction={predictionModal}
        incidentTitle={currentIncident?.title}
        onClose={closePredictionModal}
        isOpen={!!predictionModal}
      />

      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 10, scale: 0.98 }}
            className="fixed bottom-6 right-6 z-50"
          >
            <div className="glass-panel px-5 py-3.5 flex items-center gap-3" style={{
              borderColor: toast.type === 'prediction' ? 'rgba(239,68,68,0.35)' : toast.type === 'error' ? 'rgba(245,158,11,0.35)' : 'rgba(99,102,241,0.25)',
              background: 'rgba(10,12,20,0.95)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
            }}>
              {toast.type === 'prediction' ? <AlertTriangle size={16} style={{ color: '#ef4444' }} /> : toast.type === 'error' ? <AlertTriangle size={16} style={{ color: '#fbbf24' }} /> : <Brain size={16} style={{ color: 'var(--accent-bright)' }} />}
              <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>{toast.message}</span>
              <button onClick={() => setToast(null)} className="ml-2 hover:opacity-70 transition-opacity" style={{ color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function TimelineView({ events, predictions }) {
  const scrollRef = useRef(null);
  const activePredictions = (predictions || []).filter(p => !p.outcome);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events.length, predictions.length]);

  return (
    <div className="max-w-3xl mx-auto" ref={scrollRef}>
      {/* Active Prediction Warnings */}
      <AnimatePresence>
        {activePredictions.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="mb-6 relative overflow-hidden rounded-2xl p-5"
            style={{
              background: 'linear-gradient(135deg, rgba(239,68,68,0.08), rgba(12,14,24,0.9))',
              border: '1px solid rgba(239,68,68,0.2)',
              boxShadow: '0 8px 32px rgba(239,68,68,0.1), inset 0 1px 0 rgba(255,255,255,0.03)',
            }}
          >
            <div className="absolute top-0 left-0 right-0 h-[1px]" style={{ background: 'linear-gradient(90deg, transparent, rgba(239,68,68,0.5), transparent)' }} />
            <div className="flex items-start gap-4 relative z-10">
              <motion.div
                animate={{ rotate: [0, -10, 10, -5, 0] }}
                transition={{ duration: 0.6, repeat: Infinity, repeatDelay: 3 }}
                className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                style={{ background: 'rgba(239,68,68,0.12)', border: '1px solid rgba(239,68,68,0.2)' }}
              >
                <AlertTriangle size={18} style={{ color: '#ef4444' }} />
              </motion.div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-[11px] font-bold uppercase tracking-widest" style={{ color: '#f87171' }}>Cascade Warning</span>
                  <span className="live-badge">ACTIVE</span>
                </div>
                <p className="text-[13px] font-bold leading-snug mb-2" style={{ color: 'var(--text-primary)' }}>
                  {activePredictions[activePredictions.length - 1].predicted_failure}
                </p>
                <div className="flex items-center gap-3 flex-wrap">
                  <span className="tag tag-warning">
                    {Math.round(activePredictions[activePredictions.length - 1].confidence * 100)}% confidence
                  </span>
                  {activePredictions[activePredictions.length - 1].time_to_failure_minutes !== null && (
                    <span className="text-[11px] font-mono flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                      <Clock size={10} /> ~{activePredictions[activePredictions.length - 1].time_to_failure_minutes} min
                    </span>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {events.length === 0 ? (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="text-center py-24">
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.1)' }}>
            <Activity size={28} style={{ color: 'var(--text-muted)' }} />
          </div>
          <p className="text-[14px] font-medium" style={{ color: 'var(--text-muted)' }}>No events yet</p>
          <p className="text-[12px] mt-1.5" style={{ color: 'var(--text-muted)' }}>Submit an event below to get started</p>
        </motion.div>
      ) : (
        <div className="timeline-container">
          <div className="timeline-axis" />
          <motion.div variants={containerVariants} initial="hidden" animate="visible" className="space-y-5">
            {events.map((evt, i) => {
              const tc = typeConfig[evt.type] || typeConfig.action;
              const sc = sourceConfig[evt.source] || sourceConfig.slack;
              const TypeIcon = tc.icon;
              const SourceIcon = sc.icon;
              return (
                <motion.div
                  key={evt.id || i}
                  variants={itemVariants}
                  className="relative"
                >
                  <div className={`timeline-node ${evt.type}`} />
                  <div className="glass-card p-4" style={{ marginLeft: 12 }}>
                    <div className="flex items-start gap-3.5">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                        style={{ background: tc.bg || `${tc.color}12`, boxShadow: `0 0 16px ${tc.glow}` }}
                      >
                        <TypeIcon size={18} style={{ color: tc.color }} />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2.5 mb-2 flex-wrap">
                          <span className={`tag tag-${evt.type}`}>{tc.label}</span>
                          <span className={`tag tag-${evt.source}`}>
                            <SourceIcon size={10} /> {sc.label}
                          </span>
                          <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                            {format(new Date(evt.timestamp), 'HH:mm:ss')}
                          </span>
                        </div>
                        <p className="text-[13px] leading-relaxed font-medium" style={{ color: 'var(--text-primary)' }}>{evt.content}</p>
                        <div className="flex items-center gap-4 mt-2.5">
                          <span className="text-[11px] flex items-center gap-1.5 font-medium" style={{ color: 'var(--text-muted)' }}>
                            <Users size={10} /> {evt.actor}
                          </span>
                          {evt.confidence < 1 && (
                            <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
                              {Math.round(evt.confidence * 100)}% confidence
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      )}
    </div>
  );
}

function EmptyState({ onNew, onSeed, onReplay, seeding, replaying }) {
  return (
    <div className="flex-1 flex items-center justify-center relative">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="text-center max-w-lg px-6"
      >
        {/* Orbital animation */}
        <div className="orbit-container mx-auto mb-8">
          <div className="orbit-ring orbit-ring-1">
            <div className="orbit-dot" style={{ top: -3, left: '50%', transform: 'translateX(-50%)' }} />
          </div>
          <div className="orbit-ring orbit-ring-2">
            <div className="orbit-dot" style={{ bottom: -3, left: '50%', transform: 'translateX(-50%)', background: '#a855f7', boxShadow: '0 0 8px rgba(168,85,247,0.5)' }} />
          </div>
          <div className="orbit-ring orbit-ring-3">
            <div className="orbit-dot" style={{ top: '50%', right: -3, transform: 'translateY(-50%)', background: '#f59e0b', boxShadow: '0 0 8px rgba(245,158,11,0.5)' }} />
          </div>
          <div className="w-16 h-16 rounded-2xl flex items-center justify-center relative z-10" style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 8px 40px rgba(99,102,241,0.4)' }}>
            <Brain size={32} className="text-white" />
            <div className="absolute inset-0 rounded-2xl" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.2)' }} />
          </div>
        </div>

        <h2 className="text-[26px] font-bold mb-3 gradient-text font-display">Welcome to Incident Brain</h2>
        <p className="text-[13px] mb-10 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
          Autonomous incident response with cascade failure prediction. Watch the AI reason across signals in real-time.
        </p>

        <div className="flex gap-3 justify-center flex-wrap">
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onNew} className="btn btn-primary">
            <Plus size={16} /> Create Incident
          </motion.button>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onReplay} disabled={replaying} className="btn btn-glow">
            {replaying ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            Replay Demo
          </motion.button>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onSeed} disabled={seeding} className="btn btn-ghost">
            {seeding ? <Loader2 size={14} className="animate-spin" /> : <Database size={14} />}
            Load Demo
          </motion.button>
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="mt-14 grid grid-cols-3 gap-4"
        >
          {[
            { icon: Brain, label: 'Predictive', desc: 'AI reasons forward across all signals', color: '#818cf8' },
            { icon: Shield, label: 'Privacy First', desc: 'PII redaction before cloud', color: '#34d399' },
            { icon: TrendingUp, label: 'Self-Improving', desc: 'Tracks prediction accuracy', color: '#fbbf24' },
          ].map((f, i) => (
            <motion.div
              key={f.label}
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 + i * 0.1 }}
              whileHover={{ y: -3, transition: { duration: 0.2 } }}
              className="glass-card p-5 text-center group"
            >
              <div className="w-10 h-10 rounded-xl flex items-center justify-center mx-auto mb-3 transition-transform group-hover:scale-110" style={{ background: `${f.color}12` }}>
                <f.icon size={20} style={{ color: f.color }} />
              </div>
              <p className="text-[12px] font-bold mb-1 font-display">{f.label}</p>
              <p className="text-[10px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>{f.desc}</p>
            </motion.div>
          ))}
        </motion.div>
      </motion.div>
    </div>
  );
}

function EventInput({ onSubmit, onSubmitImage, disabled }) {
  const [text, setText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    setSubmitting(true);
    try { await onSubmit(text.trim()); setText(''); }
    finally { setSubmitting(false); }
  };

  const handleImage = async (e) => {
    const file = e.target.files[0];
    if (!file || disabled) return;
    setSubmitting(true);
    try { await onSubmitImage(file); e.target.value = ''; }
    finally { setSubmitting(false); }
  };

  return (
    <form onSubmit={handleSubmit} className="glass-panel p-3">
      <div className="flex gap-2.5">
        <input
          type="text"
          value={text}
          onChange={e => setText(e.target.value)}
          placeholder="Describe what happened... (action, observation, hypothesis)"
          disabled={disabled || submitting}
          className="glass-input flex-1"
        />
        <label className="btn btn-ghost cursor-pointer px-3">
          <Image size={16} />
          <input type="file" accept="image/*" onChange={handleImage} className="hidden" disabled={disabled || submitting} />
        </label>
        <motion.button
          type="submit"
          disabled={!text.trim() || disabled || submitting}
          className="btn btn-primary px-4"
          whileHover={{ scale: 1.03 }}
          whileTap={{ scale: 0.97 }}
        >
          {submitting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </motion.button>
      </div>
    </form>
  );
}

function AiAnalysisView({ analysis, onAnalyze, analyzing }) {
  return (
    <div className="max-w-3xl mx-auto">
      {!analysis ? (
        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="text-center py-20">
          <div className="w-20 h-20 rounded-2xl flex items-center justify-center mx-auto mb-6 relative" style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)', boxShadow: '0 12px 40px rgba(99,102,241,0.35)' }}>
            <Brain size={32} className="text-white" />
            <div className="absolute inset-0 rounded-2xl" style={{ boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.2)' }} />
          </div>
          <h3 className="text-[18px] font-bold mb-2 font-display">AI Incident Analysis</h3>
          <p className="text-[13px] mb-8 max-w-sm mx-auto leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            Let Gemini analyze the incident events and speculate on root cause, patterns, and next steps.
          </p>
          <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onAnalyze} disabled={analyzing} className="btn btn-primary">
            {analyzing ? <><Loader2 size={16} className="animate-spin" /> Analyzing...</> : <><Sparkles size={16} /> Analyze with AI</>}
          </motion.button>
        </motion.div>
      ) : (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-5">
          <div className="flex items-center justify-between mb-2">
            <h2 className="text-[20px] font-bold gradient-text font-display">AI Analysis</h2>
            <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onAnalyze} disabled={analyzing} className="btn btn-glow text-[12px]">
              {analyzing ? <Loader2 size={14} className="animate-spin" /> : <Sparkles size={14} />}
              Re-analyze
            </motion.button>
          </div>
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="glass-panel p-7"
            style={{ background: 'linear-gradient(135deg, rgba(99,102,241,0.06), rgba(168,85,247,0.03))', border: '1px solid rgba(99,102,241,0.15)' }}
          >
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'rgba(99,102,241,0.1)' }}>
                <Brain size={20} style={{ color: '#818cf8' }} />
              </div>
              <div>
                <span className="text-[13px] font-bold" style={{ color: '#818cf8' }}>Gemini Analysis</span>
                <p className="text-[10px] font-mono mt-0.5" style={{ color: 'var(--text-muted)' }}>Generated just now</p>
              </div>
            </div>
            <div className="text-[13px] leading-[1.8] whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>
              {analysis}
            </div>
          </motion.div>
        </motion.div>
      )}
    </div>
  );
}

function PostMortemView({ postmortem, onExport }) {
  if (!postmortem) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center py-24">
        <div className="w-16 h-16 rounded-2xl flex items-center justify-center mx-auto mb-5" style={{ background: 'rgba(99,102,241,0.06)', border: '1px solid rgba(99,102,241,0.1)' }}>
          <FileText size={28} style={{ color: 'var(--text-muted)' }} />
        </div>
        <p className="text-[14px] font-medium" style={{ color: 'var(--text-muted)' }}>No post-mortem generated yet</p>
        <p className="text-[12px] mt-1.5" style={{ color: 'var(--text-muted)' }}>Resolve the incident first, then generate one</p>
      </motion.div>
    );
  }

  const sections = [
    { title: 'Summary', icon: FileText, content: <p className="text-[13px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{postmortem.summary}</p> },
    {
      title: 'Timeline', icon: Clock,
      content: (
        <div className="space-y-4">
          {(postmortem.timeline || []).map((item, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
              className="flex gap-4 items-start"
            >
              <div className="w-2.5 h-2.5 rounded-full mt-1.5 flex-shrink-0" style={{ background: 'var(--accent)', boxShadow: '0 0 8px var(--accent-glow)' }} />
              <div>
                <span className="text-[11px] font-mono font-semibold" style={{ color: 'var(--accent-bright)' }}>{item.time}</span>
                <p className="text-[12px] mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{item.event}</p>
              </div>
            </motion.div>
          ))}
        </div>
      )
    },
    { title: 'Root Cause Hypothesis', icon: Flame, content: <p className="text-[13px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>{postmortem.root_cause_hypothesis}</p> },
    {
      title: 'Actions & Outcomes', icon: Zap,
      content: (
        <div className="space-y-4">
          {(postmortem.actions_and_outcomes || []).map((item, i) => (
            <motion.div key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="flex gap-3">
              <ArrowRight size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
              <div>
                <p className="text-[12px] font-semibold">{item.action}</p>
                <p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>Outcome: {item.outcome}</p>
              </div>
            </motion.div>
          ))}
        </div>
      )
    },
    {
      title: 'Contributing Factors', icon: TrendingUp,
      content: (
        <ul className="space-y-2.5">
          {(postmortem.contributing_factors || []).map((f, i) => (
            <motion.li key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="flex items-start gap-2.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
              <ChevronRight size={12} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} /> {f}
            </motion.li>
          ))}
        </ul>
      )
    },
    {
      title: 'Follow-up Action Items', icon: CheckCircle,
      content: (
        <ul className="space-y-2.5">
          {(postmortem.follow_up_items || []).map((item, i) => (
            <motion.li key={i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="flex items-start gap-2.5 text-[12px]">
              <input type="checkbox" className="mt-1 rounded" style={{ accentColor: 'var(--accent)' }} />
              <span style={{ color: 'var(--text-secondary)' }}>{item}</span>
            </motion.li>
          ))}
        </ul>
      )
    },
  ];

  if (postmortem.prediction_retrospective) {
    const pr = postmortem.prediction_retrospective;
    sections.push({
      title: 'Prediction Retrospective',
      icon: Brain,
      content: (
        <div className="space-y-5">
          {pr.most_predictive_signals && pr.most_predictive_signals.length > 0 && (
            <div>
              <p className="text-[12px] font-bold mb-2.5" style={{ color: 'var(--text-primary)' }}>Most Predictive Signals</p>
              <ul className="space-y-1.5">
                {pr.most_predictive_signals.map((s, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
                    <ChevronRight size={12} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} /> {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {pr.most_accurate_prediction && (
            <div>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: 'var(--text-primary)' }}>Most Accurate Prediction</p>
              <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{pr.most_accurate_prediction}</p>
            </div>
          )}
          {pr.earlier_prediction_opportunity && (
            <div>
              <p className="text-[12px] font-bold mb-1.5" style={{ color: 'var(--text-primary)' }}>Earlier Prediction Opportunity</p>
              <p className="text-[12px]" style={{ color: 'var(--text-secondary)' }}>{pr.earlier_prediction_opportunity}</p>
            </div>
          )}
          {pr.missed_signals && pr.missed_signals.length > 0 && (
            <div>
              <p className="text-[12px] font-bold mb-2.5" style={{ color: 'var(--text-primary)' }}>Missed Signals</p>
              <ul className="space-y-1.5">
                {pr.missed_signals.map((s, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-[12px]" style={{ color: 'var(--text-secondary)' }}>
                    <ChevronRight size={12} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--warning)' }} /> {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )
    });
  }

  return (
    <motion.div variants={containerVariants} initial="hidden" animate="visible" className="max-w-3xl mx-auto space-y-5">
      <motion.div variants={itemVariants} className="flex items-center justify-between mb-2">
        <h2 className="text-[20px] font-bold gradient-text font-display">Post-Mortem Report</h2>
        <motion.button whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} onClick={onExport} className="btn btn-glow text-[12px]">
          <Download size={14} /> Export Markdown
        </motion.button>
      </motion.div>
      {sections.map((section, i) => (
        <motion.div
          key={i}
          variants={itemVariants}
          className="pm-section"
        >
          <h3><section.icon size={16} style={{ color: 'var(--accent-bright)' }} /> {section.title}</h3>
          {section.content}
        </motion.div>
      ))}
    </motion.div>
  );
}

function NewIncidentModal({ onClose, onCreate }) {
  const [title, setTitle] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!title.trim()) return;
    setLoading(true);
    try { await onCreate(title.trim()); }
    finally { setLoading(false); }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="modal-overlay"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.92, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.96, y: 8 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className="glass-panel p-7 w-full max-w-md"
        style={{ background: 'linear-gradient(180deg, rgba(12,14,24,0.98) 0%, rgba(8,10,16,0.98) 100%)', boxShadow: '0 24px 80px rgba(0,0,0,0.6)' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-7">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl flex items-center justify-center" style={{ background: 'linear-gradient(135deg, #6366f1, #a855f7)' }}>
              <Terminal size={16} className="text-white" />
            </div>
            <h2 className="text-[16px] font-bold font-display">New Incident</h2>
          </div>
          <button onClick={onClose} style={{ color: 'var(--text-muted)' }} className="hover:text-white transition-colors p-1 rounded-lg hover:bg-white/5"><X size={18} /></button>
        </div>
        <form onSubmit={handleSubmit}>
          <label className="text-[11px] font-bold uppercase tracking-widest mb-2 block" style={{ color: 'var(--text-muted)' }}>Incident Title</label>
          <input
            type="text"
            value={title}
            onChange={e => setTitle(e.target.value)}
            placeholder="Payment API returning 500 errors..."
            className="glass-input mb-6"
            autoFocus
          />
          <div className="flex justify-end gap-2.5">
            <button type="button" onClick={onClose} className="btn btn-ghost">Cancel</button>
            <motion.button
              type="submit"
              disabled={!title.trim() || loading}
              className="btn btn-primary"
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
            >
              {loading ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
              Create
            </motion.button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
