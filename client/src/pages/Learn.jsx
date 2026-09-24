import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import LevelBadge from '../components/LevelBadge.jsx';
import { CheckIcon, ArrowIcon } from '../components/Icons.jsx';

export default function Learn() {
  const { user, meta } = useAuth();
  const [level, setLevel] = useState(user.currentLevel);
  const [units, setUnits] = useState(null);

  useEffect(() => {
    setUnits(null);
    api(`/units?level=${encodeURIComponent(level)}`).then((d) => setUnits(d.units));
  }, [level]);

  if (!meta) return null;
  const levels = meta.audiences[user.audience].levels;

  return (
    <main className="app-main">
      <div className="container">
        <div className="page-head spread">
          <div>
            <div className="eyebrow">Curriculum</div>
            <h1>Learning path</h1>
            <p className="muted" style={{ margin: 0 }}>Each unit targets a CEFR can-do goal with key language, pronunciation practice and an AI role-play.</p>
          </div>
          <div className="tabs" role="tablist">
            {levels.map((lv) => <button key={lv} role="tab" aria-selected={lv === level} className={lv === level ? 'active' : ''} onClick={() => setLevel(lv)}>{lv}{lv === user.currentLevel ? ' •' : ''}</button>)}
          </div>
        </div>

        <div className="card" style={{ marginBottom: 24 }}>
          <div className="row" style={{ gap: 20 }}>
            <LevelBadge level={level} />
            <div style={{ flex: 1 }}>
              <h3 style={{ margin: 0 }}>{level} · {meta.levelInfo[level].name}</h3>
              <p className="muted small" style={{ margin: '4px 0 0' }}>{meta.levelInfo[level].summary}</p>
            </div>
          </div>
        </div>

        {!units ? <div className="spinner" /> : (
          <div className="grid grid-2">
            {units.map((u, i) => (
              <Link key={u.id} to={`/unit/${u.id}`} className="card card-hover unit-card fade-in">
                <div className="spread">
                  <span className="pill">Unit {i + 1}</span>
                  {u.completed ? <span className="pill pill-sage"><CheckIcon width={12} /> Completed{u.score != null ? ` · ${u.score}%` : ''}</span> : <span className="pill pill-accent">{u.focus}</span>}
                </div>
                <h3 style={{ margin: '6px 0 0' }}>{u.title}</h3>
                <p className="muted" style={{ margin: 0 }}>“{u.canDo}”</p>
                <div className="spread small" style={{ marginTop: 8 }}>
                  <span className="muted">Role-play: {u.scenario[1]}</span>
                  <ArrowIcon width={18} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
