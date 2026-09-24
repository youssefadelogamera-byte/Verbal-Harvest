import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import LevelBadge from '../components/LevelBadge.jsx';
import Mic from '../components/Mic.jsx';
import { SpeakerIcon, ChatIcon, CheckIcon } from '../components/Icons.jsx';
import { speak, rateFor, useSpeechRecognition, compareSpeech } from '../speech.js';

export function PhraseDrill({ phrase, level, onScore }) {
  const rec = useSpeechRecognition();
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!rec.listening && rec.transcript) {
      const r = compareSpeech(phrase, rec.transcript);
      setResult(r);
      onScore?.(r.score);
    }
  }, [rec.listening]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="phrase">
      <button className="btn btn-ghost btn-icon" onClick={() => speak(phrase, { rate: rateFor(level) })} aria-label={`Listen: ${phrase}`}><SpeakerIcon width={18} /></button>
      <div className="phrase-text">
        {result ? result.words.map((w, i) => <span key={i} className={w.ok ? 'word-ok' : 'word-miss'}>{w.word} </span>) : phrase}
        {rec.listening && <div className="muted small">{rec.transcript} {rec.interim}</div>}
        {rec.error && <div className="small" style={{ color: 'var(--rose)' }}>{rec.error}</div>}
      </div>
      {result && <span className={`pill ${result.score >= 80 ? 'pill-sage' : result.score >= 50 ? 'pill-accent' : 'pill-rose'}`}>{result.score}%</span>}
      <Mic size="sm" listening={rec.listening} onStart={() => { setResult(null); rec.start(); }} onStop={rec.stop} label="Say this phrase" />
    </div>
  );
}

export default function Unit() {
  const { id } = useParams();
  const { user } = useAuth();
  const [unit, setUnit] = useState(null);
  const [scores, setScores] = useState({});
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setUnit(null); setScores({}); setSaved(false);
    api(`/units/${id}`).then((d) => setUnit(d.unit)).catch((e) => setError(e.message));
  }, [id]);

  if (error) return <main className="app-main container"><div className="alert alert-error">{error}</div></main>;
  if (!unit) return <main className="app-main"><div className="spinner" /></main>;

  const values = Object.values(scores);
  const avg = values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : null;
  const kid = user.audience === 'children';

  async function complete() {
    await api(`/units/${unit.id}/complete`, { method: 'POST', body: { score: avg ?? 70 } });
    if (avg != null) api('/pronunciation/log', { method: 'POST', body: { score: avg } }).catch(() => {});
    setSaved(true);
  }

  return (
    <main className="app-main">
      <div className="container">
        <Link to="/learn" className="link small">← Learning path</Link>
        <div className="page-head row" style={{ marginTop: 16, gap: 20, alignItems: 'flex-start' }}>
          <LevelBadge level={unit.level} />
          <div style={{ flex: 1 }}>
            <div className="eyebrow">{unit.focus}</div>
            <h1>{unit.title}</h1>
            <p className="muted" style={{ fontSize: '1.1rem', margin: 0 }}>🎯 <i>“{unit.canDo}”</i></p>
          </div>
          {unit.completed && <span className="pill pill-sage"><CheckIcon width={12} /> Completed</span>}
        </div>

        <div className="split split-3-2">
          <div className="card">
            <div className="spread"><h3 style={{ margin: 0 }}>1 · Key language</h3>{avg != null && <span className="pill pill-accent">Average {avg}%</span>}</div>
            <p className="muted small">{kid ? 'Listen 🔊, then press the microphone and say it!' : 'Listen to the model, then record yourself. Words in red were not recognised — try again, focusing on those sounds.'}</p>
            <div className="stack">
              {unit.phrases.map((p) => <PhraseDrill key={p} phrase={p} level={unit.level} onScore={(s) => setScores((prev) => ({ ...prev, [p]: Math.max(prev[p] || 0, s) }))} />)}
            </div>
          </div>

          <div className="stack">
            <div className="card card-dark">
              <h3 style={{ color: '#fff' }}>2 · Role-play</h3>
              <p className="muted small">With: <b style={{ color: '#fff' }}>{unit.scenario[0]}</b><br />Where: {unit.scenario[1]}</p>
              <div className="alert" style={{ background: 'rgba(255,255,255,.08)', color: '#fff', marginBottom: 16 }}><b>Your goal:</b> {unit.scenario[2]}</div>
              <Link to={`/coach?unit=${unit.id}`} className="btn btn-accent" style={{ width: '100%' }}><ChatIcon width={18} /> Start role-play</Link>
            </div>
            <div className="card">
              <h3>3 · Complete the unit</h3>
              <p className="muted small">Practise the phrases and try the role-play, then mark the unit complete to earn XP.</p>
              {saved ? <div className="alert alert-success">Unit completed — great work! <Link to="/learn" className="link">Next unit →</Link></div>
                : <button className="btn btn-primary" style={{ width: '100%' }} onClick={complete}>Mark as complete</button>}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
