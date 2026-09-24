import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { speak, useSpeechRecognition, speechSupported } from '../speech.js';
import Mic from '../components/Mic.jsx';
import { SpeakerIcon, ArrowIcon } from '../components/Icons.jsx';

const KEYS = ['A', 'B', 'C', 'D'];
const MAX_PLAYS = 2;

function Intro({ onStart, resuming, kid, busy }) {
  return (
    <div className="narrow fade-in">
      <div className="card" style={{ padding: 44 }}>
        <div className="eyebrow">Placement test</div>
        <h1 style={{ fontSize: '2.4rem' }}>{kid ? "Let's find your English level! 🌟" : "Let's find your CEFR level"}</h1>
        <p className="muted" style={{ fontSize: '1.08rem' }}>
          {kid
            ? 'Answer some fun questions, listen to short sentences, and then tell us about something you love. There are no wrong answers — just do your best!'
            : 'This adaptive test adjusts to every answer, so it stays short and accurate. It takes about 10–15 minutes.'}
        </p>
        <div className="grid grid-2" style={{ margin: '28px 0', gap: 14 }}>
          <div className="card card-tight"><strong>Part 1 · Understanding</strong><p className="muted small" style={{ margin: '6px 0 0' }}>Grammar, vocabulary, reading and listening questions that get harder or easier as you go.</p></div>
          <div className="card card-tight"><strong>Part 2 · Speaking</strong><p className="muted small" style={{ margin: '6px 0 0' }}>A short spoken (or typed) answer, assessed against the CEFR speaking criteria.</p></div>
        </div>
        <ul className="muted small" style={{ paddingLeft: 18, marginBottom: 28 }}>
          <li>Turn your sound on — listening questions can be played {MAX_PLAYS} times.</li>
          <li>Allow microphone access for the speaking part (you can also type).</li>
          <li>Don't guess wildly — “I'm not sure” answers make the result more accurate.</li>
        </ul>
        <button className="btn btn-primary btn-lg" onClick={onStart} disabled={busy}>{resuming ? 'Continue my test' : 'Begin placement test'} <ArrowIcon width={18} /></button>
      </div>
    </div>
  );
}

function Question({ item, onAnswer, busy }) {
  const [choice, setChoice] = useState(null);
  const [plays, setPlays] = useState(0);
  const [playing, setPlaying] = useState(false);

  function play() {
    if (plays >= MAX_PLAYS) return;
    setPlays((p) => p + 1);
    setPlaying(true);
    speak(item.audio, { rate: 0.92, onEnd: () => setPlaying(false) });
  }

  const pct = Math.min(95, Math.round(((item.number - 1) / item.estimatedTotal) * 100));

  return (
    <div className="narrow fade-in">
      <div className="spread" style={{ marginBottom: 12 }}>
        <span className="muted small">Question {item.number}</span>
        <span className="pill skill-tag">{item.skill}</span>
      </div>
      <div className="progress" style={{ marginBottom: 24 }}><div style={{ width: `${pct}%` }} /></div>
      <div className="card question-card">
        {item.audio && (
          <div className="listen-box">
            <button className="btn btn-primary btn-icon" onClick={play} disabled={plays >= MAX_PLAYS || playing} aria-label="Play audio"><SpeakerIcon width={20} /></button>
            <div>
              <strong>{playing ? 'Playing…' : 'Listen to the recording'}</strong>
              <div className="muted small">{MAX_PLAYS - plays} play{MAX_PLAYS - plays === 1 ? '' : 's'} left</div>
            </div>
          </div>
        )}
        <div className="question-prompt">{item.prompt}</div>
        <div className="options" role="radiogroup">
          {item.options.map((opt, i) => (
            <button key={i} role="radio" aria-checked={choice === i} className={`option ${choice === i ? 'selected' : ''}`} onClick={() => setChoice(i)}>
              <span className="key">{KEYS[i]}</span>{opt}
            </button>
          ))}
          <button role="radio" aria-checked={choice === -1} className={`option ${choice === -1 ? 'selected' : ''}`} onClick={() => setChoice(-1)} style={{ color: 'var(--muted)' }}>
            <span className="key">?</span>I'm not sure
          </button>
        </div>
        <div className="spread" style={{ marginTop: 28 }}>
          <span className="muted small">{item.audio && plays === 0 ? 'Play the audio before answering.' : ''}</span>
          <button className="btn btn-primary" disabled={choice === null || busy || (item.audio && plays === 0)} onClick={() => onAnswer(choice)}>
            Next <ArrowIcon width={16} />
          </button>
        </div>
      </div>
    </div>
  );
}

function Productive({ task, onSubmit, busy, kid }) {
  const rec = useSpeechRecognition();
  const [text, setText] = useState('');
  const [mode, setMode] = useState(speechSupported ? 'speak' : 'type');

  useEffect(() => { if (rec.transcript) setText(rec.transcript); }, [rec.transcript]);

  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return (
    <div className="narrow fade-in">
      <div className="spread" style={{ marginBottom: 12 }}>
        <span className="muted small">Final part</span><span className="pill pill-accent">Speaking</span>
      </div>
      <div className="progress" style={{ marginBottom: 24 }}><div style={{ width: '96%' }} /></div>
      <div className="card question-card">
        <div className="eyebrow">Your speaking task</div>
        <div className="question-prompt">{task}</div>
        <p className="muted small">{kid ? 'Talk for about 30 seconds. Say as much as you can!' : 'Aim for 45–90 seconds (or 60+ words). Develop your ideas with reasons and examples.'}</p>

        <div className="tabs" style={{ margin: '12px 0 20px' }}>
          <button className={mode === 'speak' ? 'active' : ''} onClick={() => setMode('speak')} disabled={!speechSupported}>🎙 Speak</button>
          <button className={mode === 'type' ? 'active' : ''} onClick={() => { rec.stop(); setMode('type'); }}>⌨️ Type</button>
        </div>

        {mode === 'speak' ? (
          <div className="stack">
            <div className="row">
              <Mic listening={rec.listening} onStart={rec.start} onStop={rec.stop} label="Record your answer" />
              <div className="muted small">{rec.listening ? 'Recording… tap to stop when you finish.' : 'Tap the microphone and start speaking.'}</div>
            </div>
            {rec.error && <div className="alert alert-error">{rec.error}</div>}
            <div className="transcript" aria-live="polite">{text || <span className="muted">Your words will appear here…</span>} <span className="interim">{rec.interim}</span></div>
          </div>
        ) : (
          <textarea className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Write your answer here…" />
        )}

        <div className="spread" style={{ marginTop: 24 }}>
          <button className="link" onClick={() => onSubmit({ skip: true })} disabled={busy}>Skip this part</button>
          <div className="row">
            <span className="muted small">{words} words</span>
            <button className="btn btn-primary" disabled={busy || words < 3 || rec.listening} onClick={() => onSubmit({ transcript: text })}>
              {busy ? 'Assessing…' : 'Finish & see my level'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Placement() {
  const { user, refresh } = useAuth();
  const navigate = useNavigate();
  const [view, setView] = useState(null);
  const [started, setStarted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const kid = user.audience === 'children';

  async function start() {
    setBusy(true); setError('');
    try {
      // Explicit retake (from menu) restarts; otherwise resume any test in progress.
      setView(await api('/placement/start', { method: 'POST', body: { restart: Boolean(user.placementLevel) && !view } }));
      setStarted(true);
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function answer(choice) {
    setBusy(true); setError('');
    try {
      setView(await api('/placement/answer', { method: 'POST', body: { itemId: view.item.id, choice } }));
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function finish(body) {
    setBusy(true); setError('');
    try {
      await api('/placement/productive', { method: 'POST', body });
      await refresh();
      navigate('/placement/result', { replace: true });
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <main className="app-main">
      <div className="narrow">{error && <div className="alert alert-error" role="alert" style={{ marginBottom: 16 }}>{error}</div>}</div>
      {!started && <Intro onStart={start} resuming={false} kid={kid} busy={busy} />}
      {started && view?.phase === 'receptive' && view.item && <Question key={view.item.id} item={view.item} onAnswer={answer} busy={busy} />}
      {started && view?.phase === 'productive' && <Productive task={view.task} onSubmit={finish} busy={busy} kid={kid} />}
    </main>
  );
}
