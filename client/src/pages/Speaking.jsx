import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import Mic from '../components/Mic.jsx';
import LevelBadge from '../components/LevelBadge.jsx';
import { useSpeechRecognition, speechSupported } from '../speech.js';

// Speaking tasks per CEFR band, modelled on standard oral-exam task types.
const TASKS = {
  low: [
    'Describe your home. What rooms are there, and which is your favourite?',
    'Talk about your best friend. What do they look like and what do you do together?',
    'Describe what you do on a typical weekend.',
  ],
  mid: [
    'Describe a person who has influenced you. How did they change your life?',
    'Talk about a time something went wrong on a trip. What happened and how did you deal with it?',
    'What are the advantages and disadvantages of living in a big city?',
  ],
  high: [
    'To what extent should governments regulate artificial intelligence? Present a reasoned argument.',
    '“Success is more about luck than hard work.” Discuss, considering different perspectives.',
    'Evaluate how remote work has changed the relationship between employers and employees.',
  ],
  business: [
    'Pitch a new product or service idea to your manager in about a minute.',
    'Describe your current role and explain one process you would improve, and why.',
    'Your client is unhappy with a delayed delivery. Explain the situation and propose a solution.',
  ],
  kids: [
    'Tell me about your favourite toy or game. Why do you like it?',
    'What did you do yesterday? Tell me everything!',
    'If you could have any pet in the world, what would it be and why?',
  ],
};

function tasksFor(user, levels) {
  if (user.audience === 'children') return TASKS.kids;
  if (user.audience === 'business') return TASKS.business;
  const i = levels.indexOf(user.currentLevel);
  return i <= 2 ? TASKS.low : i <= 4 ? TASKS.mid : TASKS.high;
}

const CRITERIA = ['range', 'accuracy', 'fluency', 'coherence', 'interaction'];

export default function Speaking() {
  const { user, meta } = useAuth();
  const rec = useSpeechRecognition();
  const [taskIdx, setTaskIdx] = useState(0);
  const [text, setText] = useState('');
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [seconds, setSeconds] = useState(0);

  useEffect(() => { if (rec.transcript) setText(rec.transcript); }, [rec.transcript]);
  useEffect(() => {
    if (!rec.listening) return undefined;
    setSeconds(0);
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [rec.listening]);

  if (!meta) return null;
  const tasks = tasksFor(user, meta.levels);
  const task = tasks[taskIdx % tasks.length];
  const words = text.trim().split(/\s+/).filter(Boolean).length;

  async function assess() {
    setBusy(true); setError('');
    try {
      const d = await api('/speaking/assess', { method: 'POST', body: { task, transcript: text } });
      setResult(d.result);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  function nextTask() {
    setTaskIdx((i) => i + 1); setText(''); setResult(null); rec.reset();
  }

  return (
    <main className="app-main">
      <div className="container">
        <div className="page-head">
          <div className="eyebrow">Speaking test</div>
          <h1>Show what you can say</h1>
          <p className="muted" style={{ margin: 0, maxWidth: 640 }}>Respond to the task, then get examiner-style feedback on the five CEFR speaking criteria and an estimated CEFR level for this performance.</p>
        </div>

        <div className="grid grid-2" style={{ alignItems: 'start' }}>
          <div className="card">
            <div className="spread"><span className="pill pill-accent">Task {taskIdx % tasks.length + 1} of {tasks.length}</span><button className="link small" onClick={nextTask}>Try another task</button></div>
            <div className="question-prompt" style={{ marginTop: 16 }}>{task}</div>
            <div className="row" style={{ marginBottom: 16 }}>
              {speechSupported && <Mic listening={rec.listening} onStart={() => { setResult(null); rec.start(); }} onStop={rec.stop} label="Record answer" />}
              <div className="small muted">
                {rec.listening ? <><b style={{ color: 'var(--rose)' }}>● Recording</b> · {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</> : speechSupported ? 'Tap to record. Aim for 1–2 minutes.' : 'Type your answer below.'}
              </div>
            </div>
            {rec.error && <div className="alert alert-error small" style={{ marginBottom: 12 }}>{rec.error}</div>}
            <textarea className="input" value={rec.listening ? `${text} ${rec.interim}`.trim() : text} readOnly={rec.listening} onChange={(e) => setText(e.target.value)} placeholder="Your transcript appears here — you can also type or edit it." />
            <div className="spread" style={{ marginTop: 16 }}>
              <span className="muted small">{words} words</span>
              <button className="btn btn-primary" disabled={busy || words < 3 || rec.listening} onClick={assess}>{busy ? 'Assessing…' : 'Get feedback'}</button>
            </div>
            {error && <div className="alert alert-error small" style={{ marginTop: 12 }}>{error}</div>}
          </div>

          <div className="card">
            {!result && !busy && (
              <div className="center" style={{ padding: '40px 10px' }}>
                <div style={{ fontSize: '2.4rem' }}>🎙️</div>
                <h3>Your report will appear here</h3>
                <p className="muted small">Scored on range, accuracy, fluency, coherence and interaction — the qualitative aspects of spoken language in the CEFR.</p>
              </div>
            )}
            {busy && <div style={{ padding: 60 }}><div className="spinner" /><p className="center muted small" style={{ marginTop: 16 }}>Your examiner is listening back…</p></div>}
            {result && (
              <div className="fade-in">
                <div className="row" style={{ gap: 18, marginBottom: 16 }}>
                  <LevelBadge level={result.level} />
                  <div>
                    <strong>Estimated performance: {result.level} · {meta.levelInfo[result.level].name}</strong>
                    <div className="muted small">Working level: {user.currentLevel}</div>
                  </div>
                </div>
                <p className="small">{result.summary}</p>
                {CRITERIA.map((c) => (
                  <div className="bar-row" key={c}>
                    <span style={{ textTransform: 'capitalize' }}>{c}</span>
                    <div className="progress"><div style={{ width: `${result.scores[c]}%` }} /></div>
                    <b>{result.scores[c]}</b>
                  </div>
                ))}
                <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div><strong className="small">Strengths</strong><ul className="small muted" style={{ paddingLeft: 18 }}>{result.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
                  <div><strong className="small">To improve</strong><ul className="small muted" style={{ paddingLeft: 18 }}>{result.improvements.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
                </div>
                {result.improvedVersion && (
                  <div className="alert alert-success small"><b>A stronger version:</b><br />{result.improvedVersion}</div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
