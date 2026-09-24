import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';
import LevelBadge from '../components/LevelBadge.jsx';

export default function Profile() {
  const { user, setUser, logout, meta } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: user.name, nativeLanguage: user.nativeLanguage || '', goal: user.goal || '' });
  const [msg, setMsg] = useState(null);
  const [delPw, setDelPw] = useState('');
  const [showDelete, setShowDelete] = useState(false);

  async function save(e) {
    e.preventDefault();
    try {
      const { user: u } = await api('/profile', { method: 'PATCH', body: form });
      setUser(u);
      setMsg({ type: 'success', text: 'Profile saved.' });
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  async function remove(e) {
    e.preventDefault();
    try {
      await api('/account', { method: 'DELETE', body: { password: delPw } });
      setUser(null);
      navigate('/');
    } catch (err) { setMsg({ type: 'error', text: err.message }); }
  }

  return (
    <main className="app-main">
      <div className="narrow stack">
        <div className="page-head" style={{ marginBottom: 0 }}>
          <div className="eyebrow">Account</div>
          <h1>Profile & settings</h1>
        </div>
        {msg && <div className={`alert alert-${msg.type}`}>{msg.text}</div>}

        <div className="card">
          <div className="spread">
            <div className="row" style={{ gap: 16 }}>
              {user.currentLevel ? <LevelBadge level={user.currentLevel} /> : <span className="pill">No level yet</span>}
              <div>
                <strong>{meta?.audiences[user.audience].label} track</strong>
                <div className="muted small">Placement result: {user.placementLevel || 'not taken'} · {user.xp} XP</div>
              </div>
            </div>
            <div className="row">
              {user.placementLevel && <Link to="/placement/result" className="btn btn-ghost btn-sm">Change level</Link>}
              <Link to="/placement" className="btn btn-primary btn-sm">Retake placement</Link>
            </div>
          </div>
        </div>

        <form className="card stack" onSubmit={save}>
          <h3 style={{ margin: 0 }}>Personal details</h3>
          <div className="field"><label htmlFor="n">Name</label><input id="n" className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
          <div className="field"><label>Email</label><input className="input" value={user.email} disabled /></div>
          {user.audience !== 'children' && (
            <>
              <div className="field"><label htmlFor="l">First language</label><input id="l" className="input" value={form.nativeLanguage} onChange={(e) => setForm({ ...form, nativeLanguage: e.target.value })} /></div>
              <div className="field"><label htmlFor="g">Learning goal</label><input id="g" className="input" value={form.goal} onChange={(e) => setForm({ ...form, goal: e.target.value })} /></div>
            </>
          )}
          <div className="row" style={{ justifyContent: 'flex-end' }}><button className="btn btn-primary">Save changes</button></div>
        </form>

        <div className="card stack">
          <div className="spread">
            <h3 style={{ margin: 0 }}>Session</h3>
            <button className="btn btn-ghost btn-sm" onClick={async () => { await logout(); navigate('/'); }}>Sign out</button>
          </div>
          <div className="spread">
            <div><strong>Delete account</strong><div className="muted small">Permanently remove your account and all progress.</div></div>
            {!showDelete && <button className="btn btn-danger btn-sm" onClick={() => setShowDelete(true)}>Delete…</button>}
          </div>
          {showDelete && (
            <form className="row" onSubmit={remove}>
              <input className="input" style={{ flex: 1 }} type="password" placeholder="Confirm with your password" value={delPw} onChange={(e) => setDelPw(e.target.value)} required />
              <button className="btn btn-danger">Delete permanently</button>
            </form>
          )}
        </div>
      </div>
    </main>
  );
}
