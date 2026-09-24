import { useEffect, useRef, useState } from 'react';
import { NavLink, Link, Outlet, useNavigate } from 'react-router-dom';
import Logo from './Logo.jsx';
import LevelBadge from './LevelBadge.jsx';
import { useAuth } from '../auth.jsx';
import { HomeIcon, BookIcon, ChatIcon, WaveIcon, TargetIcon } from './Icons.jsx';

const APP_LINKS = [
  ['/dashboard', 'Home', HomeIcon],
  ['/learn', 'Learn', BookIcon],
  ['/coach', 'AI Coach', ChatIcon],
  ['/pronunciation', 'Pronunciation', WaveIcon],
  ['/speaking', 'Speaking Test', TargetIcon],
];

function UserMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();
  useEffect(() => {
    const close = (e) => ref.current && !ref.current.contains(e.target) && setOpen(false);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);
  const initials = user.name.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();
  return (
    <div className="menu" ref={ref}>
      <button className="avatar" onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>{initials}</button>
      {open && (
        <div className="menu-pop fade-in" role="menu">
          <div className="menu-head">
            <strong>{user.name}</strong>
            <div className="muted small">{user.email}</div>
          </div>
          <Link to="/profile" onClick={() => setOpen(false)}>Profile & settings</Link>
          <Link to="/placement" onClick={() => setOpen(false)}>Retake placement test</Link>
          <button onClick={async () => { await logout(); navigate('/'); }}>Sign out</button>
        </div>
      )}
    </div>
  );
}

export default function Layout() {
  const { user } = useAuth();
  const inApp = Boolean(user?.currentLevel);
  return (
    <>
      <header className="nav">
        <div className="container nav-inner">
          <Logo to={user ? (inApp ? '/dashboard' : '/placement') : '/'} />
          {inApp && (
            <nav className="nav-links app-links" aria-label="Main">
              {APP_LINKS.map(([to, label]) => <NavLink key={to} to={to}>{label}</NavLink>)}
            </nav>
          )}
          <div className="row">
            {user ? (
              <>
                {user.currentLevel && <Link to="/placement/result" title="Your CEFR level"><LevelBadge level={user.currentLevel} size="sm" /></Link>}
                <UserMenu />
              </>
            ) : (
              <>
                <Link to="/login" className="btn btn-ghost btn-sm">Sign in</Link>
                <Link to="/register" className="btn btn-primary btn-sm">Get started</Link>
              </>
            )}
          </div>
        </div>
      </header>
      <Outlet />
      {inApp && (
        <nav className="mobile-nav" aria-label="Mobile">
          {APP_LINKS.map(([to, label, Icon]) => <NavLink key={to} to={to}><Icon />{label.split(' ')[0]}</NavLink>)}
        </nav>
      )}
    </>
  );
}
