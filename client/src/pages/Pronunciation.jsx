import { useEffect, useMemo, useState } from 'react';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import { PhraseDrill } from './Unit.jsx';
import { speechSupported } from '../speech.js';

export default function Pronunciation() {
  const { user } = useAuth();
  const [units, setUnits] = useState(null);
  const [unitId, setUnitId] = useState('all');
  const [scores, setScores] = useState([]);

  useEffect(() => { api('/units').then((d) => setUnits(d.units)); }, []);

  const phrases = useMemo(() => {
    if (!units) return [];
    const list = unitId === 'all' ? units : units.filter((u) => u.id === unitId);
    return list.flatMap((u) => u.phrases);
  }, [units, unitId]);

  function logScore(score) {
    setScores((s) => [...s, score]);
    api('/pronunciation/log', { method: 'POST', body: { score } }).catch(() => {});
  }

  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : 0;

  return (
    <main className="app-main">
      <div className="container">
        <div className="page-head spread">
          <div>
            <div className="eyebrow">Pronunciation lab · {user.currentLevel}</div>
            <h1>Say it clearly</h1>
            <p className="muted" style={{ margin: 0, maxWidth: 620 }}>Listen to the model, then record yourself. We compare what was recognised with the target phrase, word by word — red words need another try.</p>
          </div>
          <div className="row" style={{ gap: 20 }}>
            <div className="score-ring" style={{ '--p': avg }}><div>{scores.length ? avg : '–'}</div></div>
            <div className="small muted">{scores.length} attempt{scores.length === 1 ? '' : 's'}<br />session average</div>
          </div>
        </div>
        {!speechSupported && <div className="alert alert-error" style={{ marginBottom: 20 }}>Your browser doesn't support speech recognition. Please use Chrome, Edge or Safari for the pronunciation lab.</div>}
        <div className="card">
          <div className="spread" style={{ marginBottom: 18 }}>
            <h3 style={{ margin: 0 }}>Practice phrases</h3>
            {units && (
              <select className="input" style={{ width: 'auto' }} value={unitId} onChange={(e) => setUnitId(e.target.value)} aria-label="Choose unit">
                <option value="all">All {user.currentLevel} units</option>
                {units.map((u) => <option key={u.id} value={u.id}>{u.title}</option>)}
              </select>
            )}
          </div>
          {!units ? <div className="spinner" /> : (
            <div className="stack">{phrases.map((p) => <PhraseDrill key={p} phrase={p} level={user.currentLevel} onScore={logScore} />)}</div>
          )}
        </div>
      </div>
    </main>
  );
}
