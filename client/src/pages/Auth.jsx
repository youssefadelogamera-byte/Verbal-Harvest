import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { api } from '../api.js';
import { useAuth } from '../auth.jsx';

function AuthShell({ children, quote, cite }) {
  return (
    <main className="auth-wrap">
      <aside className="auth-side">
        <div className="eyebrow" style={{ color: '#d4a24c' }}>Verbal Harvest</div>
        <div style={{ position: 'relative', zIndex: 1 }}>
          <blockquote>{quote}</blockquote>
          <p style={{ color: '#aab6cc', marginTop: 16 }}>{cite}</p>
        </div>
        <div className="small" style={{ color: '#aab6cc', position: 'relative', zIndex: 1 }}>Aligned to the Common European Framework of Reference — Pre-A1 to C2.</div>
      </aside>
      <section className="auth-main">
        <div className="auth-form fade-in">{children}</div>
      </section>
    </main>
  );
}

export function Login() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ email: '', password: '' });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const { user } = await api('/auth/login', { method: 'POST', body: form });
      setUser(user);
      navigate(location.state?.from || (user.currentLevel ? '/dashboard' : '/placement'), { replace: true });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <AuthShell quote="“The limits of my language mean the limits of my world.”" cite="— Ludwig Wittgenstein">
      <h1 style={{ fontSize: '2.2rem' }}>Welcome back</h1>
      <p className="muted">Sign in to continue your speaking journey.</p>
      <form onSubmit={submit} className="stack" style={{ marginTop: 28 }}>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="email">Email</label>
          <input id="email" className="input" type="email" autoComplete="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="password">Password</label>
          <input id="password" className="input" type="password" autoComplete="current-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </div>
        <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
        <p className="center muted small">New to Verbal Harvest? <Link to="/register" className="link">Create an account</Link></p>
      </form>
    </AuthShell>
  );
}

const PROFILES = [
  ['children', '🧸', 'Children', 'Ages 6–11'],
  ['teens', '🎧', 'Young Learners', 'Ages 12–17'],
  ['adults', '🌍', 'Adults', '18+'],
  ['business', '💼', 'Business', 'Professionals'],
];

export function Register() {
  const { setUser } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    audience: '', name: '', email: '', password: '', nativeLanguage: '', goal: '', guardianEmail: '', guardianConsent: false, terms: false,
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === 'checkbox' ? e.target.checked : e.target.value });
  const kid = form.audience === 'children';

  async function submit(e) {
    e.preventDefault();
    if (!form.terms) { setError('Please accept the terms to continue.'); return; }
    setBusy(true); setError('');
    try {
      const { user } = await api('/auth/register', { method: 'POST', body: form });
      setUser(user);
      navigate('/placement', { replace: true });
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  return (
    <AuthShell quote="“To have another language is to possess a second soul.”" cite="— attributed to Charlemagne">
      <div className="spread">
        <span className="pill">Step {step} of 2</span>
        <span className="muted small">Already registered? <Link to="/login" className="link">Sign in</Link></span>
      </div>

      {step === 1 && (
        <div className="fade-in" style={{ marginTop: 20 }}>
          <h1 style={{ fontSize: '2.1rem' }}>Who is learning?</h1>
          <p className="muted">We tailor the placement test, lessons and AI coach to each learner profile.</p>
          <div className="choice-grid" style={{ margin: '24px 0' }} role="radiogroup">
            {PROFILES.map(([id, emoji, title, sub]) => (
              <button key={id} type="button" role="radio" aria-checked={form.audience === id}
                className={`choice ${form.audience === id ? 'selected' : ''}`} onClick={() => setForm({ ...form, audience: id })}>
                <span className="emoji">{emoji}</span><strong>{title}</strong><span>{sub}</span>
              </button>
            ))}
          </div>
          <button className="btn btn-primary btn-lg" style={{ width: '100%' }} disabled={!form.audience} onClick={() => setStep(2)}>Continue</button>
        </div>
      )}

      {step === 2 && (
        <form onSubmit={submit} className="stack fade-in" style={{ marginTop: 20 }}>
          <h1 style={{ fontSize: '2.1rem', marginBottom: 0 }}>{kid ? 'Create a child account' : 'Create your account'}</h1>
          {kid && <div className="alert alert-info">A parent or guardian should complete this form. We only ask for a first name for children.</div>}
          {error && <div className="alert alert-error" role="alert">{error}</div>}
          <div className="field">
            <label htmlFor="name">{kid ? "Child's first name" : 'Full name'}</label>
            <input id="name" className="input" required autoComplete={kid ? 'off' : 'name'} value={form.name} onChange={set('name')} />
          </div>
          <div className="field">
            <label htmlFor="email">{kid ? 'Login email (can be the parent\'s)' : 'Email'}</label>
            <input id="email" className="input" type="email" required autoComplete="email" value={form.email} onChange={set('email')} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input id="password" className="input" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set('password')} />
            <span className="muted small">At least 8 characters, with a letter and a number.</span>
          </div>
          {kid && (
            <>
              <div className="field">
                <label htmlFor="gEmail">Parent / guardian email</label>
                <input id="gEmail" className="input" type="email" required value={form.guardianEmail} onChange={set('guardianEmail')} />
              </div>
              <label className="checkbox"><input type="checkbox" checked={form.guardianConsent} onChange={set('guardianConsent')} />
                I am this child's parent or legal guardian and I consent to them using Verbal Harvest, including speaking with the AI coach.</label>
            </>
          )}
          {!kid && (
            <div className="grid" style={{ gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <div className="field">
                <label htmlFor="native">First language <span className="muted">(optional)</span></label>
                <input id="native" className="input" value={form.nativeLanguage} onChange={set('nativeLanguage')} placeholder="e.g. Arabic" />
              </div>
              <div className="field">
                <label htmlFor="goal">Main goal <span className="muted">(optional)</span></label>
                <select id="goal" className="input" value={form.goal} onChange={set('goal')}>
                  <option value="">Choose…</option>
                  <option>Everyday conversation</option>
                  <option>Travel</option>
                  <option>Study / exams</option>
                  <option>Career & work</option>
                  <option>Moving abroad</option>
                </select>
              </div>
            </div>
          )}
          <label className="checkbox"><input type="checkbox" checked={form.terms} onChange={set('terms')} />
            I agree to the Terms of Use and Privacy Policy. Your browser turns speech into text; only the text is sent to our AI coach for feedback — we never store audio.</label>
          <div className="row">
            <button type="button" className="btn btn-ghost" onClick={() => setStep(1)}>Back</button>
            <button className="btn btn-primary btn-lg" style={{ flex: 1 }} disabled={busy}>{busy ? 'Creating account…' : 'Create account & start placement'}</button>
          </div>
        </form>
      )}
    </AuthShell>
  );
}
