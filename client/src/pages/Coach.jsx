import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import Mic from '../components/Mic.jsx';
import { SpeakerIcon, SendIcon } from '../components/Icons.jsx';
import { speak, stopSpeaking, rateFor, useSpeechRecognition, speechSupported } from '../speech.js';

function TopicPicker({ topics, onPick, kid }) {
  const [custom, setCustom] = useState('');
  return (
    <div className="narrow fade-in">
      <div className="card" style={{ padding: 40 }}>
        <div className="eyebrow">AI conversation coach</div>
        <h1 style={{ fontSize: '2.2rem' }}>{kid ? 'What shall we talk about? 💬' : 'What would you like to talk about?'}</h1>
        <p className="muted">Harvey adapts to your CEFR level, keeps the conversation flowing and shows corrections after each turn. For guided role-plays, open a unit from your learning path.</p>
        <div className="grid grid-2" style={{ gap: 12, margin: '24px 0' }}>
          {topics.map((t) => <button key={t} className="choice" onClick={() => onPick(t)}><strong style={{ marginTop: 0 }}>{t}</strong><span>Free conversation</span></button>)}
        </div>
        <form className="row" onSubmit={(e) => { e.preventDefault(); if (custom.trim()) onPick(custom.trim()); }}>
          <input className="input" style={{ flex: 1 }} placeholder="…or suggest your own topic" value={custom} onChange={(e) => setCustom(e.target.value)} maxLength={120} />
          <button className="btn btn-primary" disabled={!custom.trim()}>Start</button>
        </form>
      </div>
    </div>
  );
}

export default function Coach() {
  const { user } = useAuth();
  const [params] = useSearchParams();
  const unitId = params.get('unit');
  const [unit, setUnit] = useState(null);
  const [topic, setTopic] = useState(null);
  const [topics, setTopics] = useState([]);
  const [messages, setMessages] = useState([]);
  const [feedback, setFeedback] = useState([]); // [{turn, corrections, tip}]
  const [text, setText] = useState('');
  const [thinking, setThinking] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [goal, setGoal] = useState(false);
  const [error, setError] = useState('');
  const bodyRef = useRef(null);
  const rec = useSpeechRecognition();
  const level = unit?.level || user.currentLevel;
  const kid = user.audience === 'children';
  const active = Boolean(unit || topic);

  useEffect(() => {
    if (unitId) api(`/units/${unitId}`).then((d) => setUnit(d.unit)).catch((e) => setError(e.message));
    else api('/dashboard').then((d) => setTopics(d.topics)).catch(() => {});
    return stopSpeaking;
  }, [unitId]);

  // Kick off with the coach's opening line.
  useEffect(() => { if (active && messages.length === 0) send([]); }, [active]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight); }, [messages, thinking]);
  useEffect(() => { if (rec.transcript) setText(rec.transcript); }, [rec.transcript]);

  async function send(history) {
    setThinking(true); setError('');
    try {
      const out = await api('/coach/chat', { method: 'POST', body: { unitId: unit?.id || unitId || undefined, topic: topic || undefined, messages: history } });
      const next = [...history, { role: 'coach', text: out.reply }];
      setMessages(next);
      if (history.length && (out.corrections.length || out.tip)) {
        setFeedback((f) => [{ turn: history.at(-1).text, corrections: out.corrections, tip: out.tip }, ...f]);
      }
      if (out.goalAchieved) setGoal(true);
      if (autoSpeak) speak(out.reply, { rate: rateFor(level) });
    } catch (e) {
      setError(e.message);
      setMessages(history);
    } finally { setThinking(false); }
  }

  function submit(e) {
    e?.preventDefault();
    const t = text.trim();
    if (!t || thinking) return;
    rec.stop();
    rec.reset();
    setText('');
    const history = [...messages, { role: 'user', text: t }];
    setMessages(history);
    send(history);
  }

  if (!active && !unitId) return <main className="app-main"><TopicPicker topics={topics} onPick={setTopic} kid={kid} /></main>;

  return (
    <main className="app-main">
      <div className="container">
        {error && <div className="alert alert-error" style={{ marginBottom: 16 }}>{error}</div>}
        <div className="chat-layout">
          <section className="card chat">
            <div className="chat-head spread">
              <div className="row">
                <span className="msg-avatar">H</span>
                <div>
                  <strong>{unit ? `Role-play · ${unit.title}` : `Free talk · ${topic}`}</strong>
                  <div className="muted small">{unit ? `${unit.scenario[0]} · ${unit.scenario[1]}` : `Harvey, your AI coach`} · {level}</div>
                </div>
              </div>
              <div className="row">
                <label className="checkbox small" style={{ alignItems: 'center' }}><input type="checkbox" checked={autoSpeak} onChange={(e) => { setAutoSpeak(e.target.checked); stopSpeaking(); }} style={{ marginTop: 0 }} /> Read replies aloud</label>
                <Link className="btn btn-ghost btn-sm" to={unit ? `/unit/${unit.id}` : '/dashboard'}>End</Link>
              </div>
            </div>

            <div className="chat-body" ref={bodyRef} aria-live="polite">
              {messages.map((m, i) => (
                <div key={i} className={`msg ${m.role === 'user' ? 'me' : ''} fade-in`}>
                  {m.role === 'coach' && <span className="msg-avatar">H</span>}
                  <div className={`bubble ${m.role === 'user' ? 'me' : 'coach'}`}>{m.text}</div>
                  {m.role === 'coach' && <button className="speak-btn" onClick={() => speak(m.text, { rate: rateFor(level) })} aria-label="Play message"><SpeakerIcon width={16} /></button>}
                </div>
              ))}
              {thinking && <div className="msg"><span className="msg-avatar">H</span><div className="bubble coach typing"><span /><span /><span /></div></div>}
              {goal && <div className="alert alert-success small center">🎉 Goal achieved! Keep chatting or <Link className="link" to={unit ? `/unit/${unit.id}` : '/dashboard'}>finish</Link>.</div>}
            </div>

            <form className="chat-foot" onSubmit={submit}>
              {speechSupported && <Mic size="sm" listening={rec.listening} onStart={rec.start} onStop={rec.stop} />}
              <textarea
                className="input" rows={1} value={rec.listening ? `${text} ${rec.interim}`.trim() : text}
                placeholder={speechSupported ? 'Tap the mic and speak, or type…' : 'Type your reply…'}
                onChange={(e) => setText(e.target.value)} readOnly={rec.listening}
                onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) submit(e); }}
              />
              <button className="btn btn-primary btn-icon" disabled={!text.trim() || thinking} aria-label="Send"><SendIcon width={18} /></button>
            </form>
            {rec.error && <div className="alert alert-error small" style={{ margin: 12 }}>{rec.error}</div>}
          </section>

          <aside className="stack">
            {unit && (
              <div className="card card-tight">
                <strong>Your goal</strong>
                <p className="muted small" style={{ margin: '6px 0 12px' }}>{unit.scenario[2]}</p>
                <strong className="small">Useful language</strong>
                <ul className="small" style={{ paddingLeft: 18, margin: '6px 0 0' }}>{unit.phrases.map((p) => <li key={p}>{p}</li>)}</ul>
              </div>
            )}
            <div className="card card-tight">
              <strong>{kid ? 'Tips from Harvey ✏️' : 'Feedback'}</strong>
              {feedback.length === 0 && <p className="muted small" style={{ margin: '6px 0 0' }}>Corrections and tips will appear here after you speak. {kid ? 'Mistakes help us learn!' : 'Focus on communicating — accuracy follows.'}</p>}
              <div style={{ marginTop: 10 }}>
                {feedback.map((f, i) => (
                  <div key={i} className="fade-in">
                    {f.corrections.map((c, j) => (
                      <div key={j} className="correction"><s>{c.original}</s> → <b>{c.corrected}</b><div className="muted">{c.explanation}</div></div>
                    ))}
                    {f.tip && <div className="alert alert-info small" style={{ marginBottom: 10 }}>💡 {f.tip}</div>}
                  </div>
                ))}
              </div>
            </div>
          </aside>
        </div>
      </div>
    </main>
  );
}
