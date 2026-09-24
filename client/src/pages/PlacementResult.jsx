import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import LevelBadge from '../components/LevelBadge.jsx';
import { ArrowIcon } from '../components/Icons.jsx';

const SKILL_LABEL = { grammar: 'Grammar', vocabulary: 'Vocabulary', reading: 'Reading', listening: 'Listening', functional: 'Everyday language' };
const CRITERIA = ['range', 'accuracy', 'fluency', 'coherence', 'interaction'];

export default function PlacementResult() {
  const { user, setUser, meta } = useAuth();
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(user.currentLevel || null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api('/placement/result')
      .then((d) => { setData(d); if (!user.currentLevel) setSelected(d.result.recommendedLevel); })
      .catch((e) => (e.status === 404 ? navigate('/placement', { replace: true }) : setError(e.message)));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!data || !meta) return <main className="app-main"><div className="spinner" /></main>;
  const { result } = data;
  const rec = result.recommendedLevel;
  const info = meta.levelInfo[rec];
  const kid = user.audience === 'children';
  const allowed = meta.audiences[user.audience].levels;
  const recIdx = meta.levels.indexOf(rec);
  const pf = result.productiveFeedback;

  async function confirm() {
    setBusy(true); setError('');
    try {
      const { user: u } = await api('/level', { method: 'POST', body: { level: selected } });
      setUser(u);
      navigate('/dashboard');
    } catch (e) { setError(e.message); setBusy(false); }
  }

  return (
    <main className="app-main">
      <div className="container">
        <div className="card card-dark fade-in" style={{ padding: 44, marginBottom: 28 }}>
          <div className="result-hero">
            <LevelBadge level={rec} size="xl" />
            <div>
              <div className="eyebrow" style={{ color: '#d4a24c' }}>{kid ? 'Amazing work! 🎉' : 'Your recommended CEFR level'}</div>
              <h1 style={{ color: '#fff', marginBottom: 8 }}>{rec} · {info.name}</h1>
              <p style={{ color: '#c5cfdf', fontSize: '1.08rem', maxWidth: 680, marginBottom: 12 }}>{kid ? info.kidSummary : info.summary}</p>
              <div className="row small" style={{ color: '#aab6cc' }}>
                <span>{info.band}</span><span>·</span>
                <span>Understanding: <b style={{ color: '#fff' }}>{result.receptiveLevel}</b></span>
                {result.productiveLevel && <><span>·</span><span>Speaking/Writing: <b style={{ color: '#fff' }}>{result.productiveLevel}</b></span></>}
              </div>
            </div>
          </div>
        </div>

        <div className="grid grid-2" style={{ marginBottom: 28 }}>
          <div className="card">
            <h3>Skill profile</h3>
            <p className="muted small">Accuracy across the adaptive questions you answered.</p>
            {Object.entries(result.skills).map(([k, v]) => (
              <div className="bar-row" key={k}>
                <span>{SKILL_LABEL[k] || k}</span>
                <div className="progress"><div style={{ width: `${v}%`, background: v >= 70 ? 'var(--sage)' : v >= 45 ? 'var(--gold)' : 'var(--rose)' }} /></div>
                <b>{v}%</b>
              </div>
            ))}
            <h4 style={{ marginTop: 20, fontFamily: 'var(--font)', fontSize: '.9rem' }}>Adaptive path</h4>
            <div className="row">
              {result.path.map((p, i) => (
                <span key={i} className={`pill ${p.correct / p.total >= 0.66 ? 'pill-sage' : 'pill-rose'}`}>{p.level}: {p.correct}/{p.total}</span>
              ))}
            </div>
          </div>

          <div className="card">
            <h3>Speaking assessment</h3>
            {pf ? (
              <>
                <p className="muted small">{pf.summary}</p>
                {CRITERIA.map((c) => (
                  <div className="bar-row" key={c}>
                    <span style={{ textTransform: 'capitalize' }}>{c}</span>
                    <div className="progress"><div style={{ width: `${pf.scores[c]}%` }} /></div>
                    <b>{pf.scores[c]}</b>
                  </div>
                ))}
                <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 14, marginTop: 12 }}>
                  <div><strong className="small">Strengths</strong><ul className="small muted" style={{ paddingLeft: 18 }}>{pf.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
                  <div><strong className="small">Next steps</strong><ul className="small muted" style={{ paddingLeft: 18 }}>{pf.improvements.map((s, i) => <li key={i}>{s}</li>)}</ul></div>
                </div>
              </>
            ) : (
              <p className="muted">You skipped the speaking part, so your recommendation is based on understanding skills only. You can take a full speaking test any time from the dashboard.</p>
            )}
            <div className="alert alert-info small" style={{ marginTop: 12 }}><b>CEFR speaking at {rec}:</b> {info.speaking}</div>
          </div>
        </div>

        <div className="card">
          <div className="spread">
            <div>
              <h2 style={{ marginBottom: 4 }}>Choose your starting level</h2>
              <p className="muted" style={{ margin: 0 }}>We recommend <b>{rec}</b>. You can pick a level just below to build confidence, or above for a challenge.</p>
            </div>
            <Link to="/placement" className="btn btn-ghost btn-sm">Retake test</Link>
          </div>
          {error && <div className="alert alert-error" style={{ marginTop: 16 }}>{error}</div>}
          <div className="grid grid-3" style={{ marginTop: 24, gap: 12 }} role="radiogroup">
            {allowed.map((lv) => {
              const d = meta.levels.indexOf(lv) - recIdx;
              const note = d === 0 ? 'Recommended for you' : d === -1 ? 'Consolidate & build confidence' : d === 1 ? 'Stretch challenge' : d < 0 ? 'Probably too easy' : 'Probably too difficult';
              return (
                <button key={lv} role="radio" aria-checked={selected === lv}
                  className={`level-option ${selected === lv ? 'selected' : ''} ${d === 0 ? 'recommended' : ''}`} onClick={() => setSelected(lv)}>
                  <LevelBadge level={lv} />
                  <div>
                    <strong>{meta.levelInfo[lv].name}</strong>
                    <div className={`small ${d === 0 ? '' : 'muted'}`} style={d === 0 ? { color: 'var(--accent)', fontWeight: 600 } : undefined}>{note}</div>
                  </div>
                </button>
              );
            })}
          </div>
          {selected && Math.abs(meta.levels.indexOf(selected) - recIdx) >= 2 && (
            <div className="alert alert-error small" style={{ marginTop: 16 }}>This level is two or more steps away from your result. You can change it later in your profile.</div>
          )}
          <div className="row" style={{ marginTop: 24, justifyContent: 'flex-end' }}>
            <button className="btn btn-primary btn-lg" disabled={!selected || busy} onClick={confirm}>Start learning at {selected || '…'} <ArrowIcon width={18} /></button>
          </div>
        </div>
      </div>
    </main>
  );
}
