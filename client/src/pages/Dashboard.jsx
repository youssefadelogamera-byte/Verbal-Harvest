import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import LevelBadge from '../components/LevelBadge.jsx';
import { ChatIcon, WaveIcon, TargetIcon, ArrowIcon, CheckIcon } from '../components/Icons.jsx';

const SKILL_LABEL = { speaking: 'Role-play units', interaction: 'Conversation', production: 'Speaking tasks', pronunciation: 'Pronunciation' };
const KIND_LABEL = { placement: 'Placement test', unit: 'Completed a unit', conversation: 'Conversation turn', speaking: 'Speaking task', pronunciation: 'Pronunciation drill' };

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

export default function Dashboard() {
  const { user, meta } = useAuth();
  const [data, setData] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => { api('/dashboard').then(setData).catch((e) => setError(e.message)); }, []);

  if (error) return <main className="app-main container"><div className="alert alert-error">{error}</div></main>;
  if (!data || !meta) return <main className="app-main"><div className="spinner" /></main>;

  const kid = user.audience === 'children';
  const level = data.user.currentLevel;
  const info = meta.levelInfo[level];
  const done = data.units.filter((u) => u.completed).length;
  const pct = data.units.length ? Math.round((done / data.units.length) * 100) : 0;
  const next = data.units.find((u) => !u.completed) || data.units[0];
  const levelIdx = meta.levels.indexOf(level);

  return (
    <main className="app-main">
      <div className="container">
        {!meta.aiEnabled && (
          <div className="banner"><span>💡</span><span><b>Practice mode.</b> The AI coach is using built-in feedback. Add an Anthropic API key on the server to unlock full Claude-powered conversations and assessments.</span></div>
        )}
        <div className="page-head spread">
          <div>
            <div className="eyebrow">{meta.audiences[user.audience].label} track</div>
            <h1>{greeting()}, {data.user.name.split(' ')[0]}{kid ? ' 👋' : '.'}</h1>
            <p className="muted" style={{ margin: 0 }}>{kid ? 'Ready for another English adventure?' : 'Consistency beats intensity. A little speaking every day adds up.'}</p>
          </div>
          <Link to={`/unit/${next.id}`} className="btn btn-primary btn-lg">{done ? 'Continue learning' : 'Start first unit'} <ArrowIcon width={18} /></Link>
        </div>

        <div className="grid stats-grid" style={{ marginBottom: 20 }}>
          <div className="card card-tight stat"><div className="stat-icon">🔥</div><div><b>{data.user.streak}</b><span className="muted small">day streak</span></div></div>
          <div className="card card-tight stat"><div className="stat-icon">⭐</div><div><b>{data.user.xp}</b><span className="muted small">experience points</span></div></div>
          <div className="card card-tight stat"><div className="stat-icon">✅</div><div><b>{done}/{data.units.length}</b><span className="muted small">units at {level}</span></div></div>
          <div className="card card-tight stat"><div className="stat-icon">🎯</div><div><b>{data.user.placementLevel}</b><span className="muted small">placement result</span></div></div>
        </div>

        <div className="split split-2-1">
          <div className="stack">
            <div className="card">
              <div className="row" style={{ gap: 20, alignItems: 'flex-start' }}>
                <LevelBadge level={level} />
                <div style={{ flex: 1, minWidth: 220 }}>
                  <div className="spread"><h3 style={{ margin: 0 }}>{level} · {info.name}</h3><span className="muted small">{pct}% complete</span></div>
                  <p className="muted small" style={{ margin: '6px 0 12px' }}>{kid ? info.kidSummary : info.speaking}</p>
                  <div className="progress"><div style={{ width: `${pct}%` }} /></div>
                </div>
              </div>
              <h4 style={{ margin: '26px 0 12px', fontFamily: 'var(--font)', fontSize: '.95rem' }}>Your pathway</h4>
              <div className="path">
                {data.path.map((p) => {
                  const i = meta.levels.indexOf(p.level);
                  const cls = p.level === level ? 'current' : i < levelIdx ? 'done' : '';
                  return <div key={p.level} className={`path-step ${cls}`}><b>{p.level}</b><small>{p.completed}/{p.total} units</small></div>;
                })}
              </div>
            </div>

            <div className="card">
              <div className="spread" style={{ marginBottom: 16 }}>
                <h3 style={{ margin: 0 }}>{level} units · can-do goals</h3>
                <Link to="/learn" className="link small">See all</Link>
              </div>
              <div className="grid grid-2" style={{ gap: 12 }}>
                {data.units.map((u) => (
                  <Link key={u.id} to={`/unit/${u.id}`} className="card card-tight card-hover unit-card">
                    <div className="spread"><strong>{u.title}</strong>{u.completed ? <span className="check"><CheckIcon width={14} /></span> : <span className="pill">{u.focus.split('·')[0].trim()}</span>}</div>
                    <span className="muted small">“{u.canDo}”</span>
                  </Link>
                ))}
              </div>
            </div>
          </div>

          <div className="stack">
            <div className="card card-dark">
              <h3 style={{ color: '#fff' }}>Practise now</h3>
              <div className="stack" style={{ marginTop: 12 }}>
                <Link to="/coach" className="btn btn-accent" style={{ width: '100%', justifyContent: 'flex-start' }}><ChatIcon width={18} /> Talk with the AI coach</Link>
                <Link to="/pronunciation" className="btn btn-light" style={{ width: '100%', justifyContent: 'flex-start' }}><WaveIcon width={18} /> Pronunciation lab</Link>
                <Link to="/speaking" className="btn btn-light" style={{ width: '100%', justifyContent: 'flex-start' }}><TargetIcon width={18} /> Speaking test</Link>
              </div>
              <p className="muted small" style={{ margin: '16px 0 0' }}>Free-talk topics: {data.topics.slice(0, 3).join(' · ')}</p>
            </div>

            <div className="card">
              <h3>Skills</h3>
              {Object.keys(data.skills).length === 0 && <p className="muted small">Complete an activity to see your skill averages here.</p>}
              {Object.entries(data.skills).map(([k, v]) => (
                <div className="bar-row" key={k} style={{ gridTemplateColumns: '110px 1fr 36px' }}>
                  <span className="small">{SKILL_LABEL[k] || k}</span>
                  <div className="progress"><div style={{ width: `${v.average}%` }} /></div>
                  <b className="small">{v.average}</b>
                </div>
              ))}
            </div>

            <div className="card">
              <h3>Recent activity</h3>
              {data.recent.length === 0 && <p className="muted small">No activity yet.</p>}
              {data.recent.map((r, i) => (
                <div className="activity-item" key={i}>
                  <span>{KIND_LABEL[r.kind] || r.kind}{r.detail?.unit ? ` · ${r.detail.unit}` : ''}{r.detail?.level ? ` · ${r.detail.level}` : ''}</span>
                  <span className="muted">{new Date(r.created_at + 'Z').toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
