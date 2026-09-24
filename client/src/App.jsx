import { Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import Layout from './components/Layout.jsx';
import { useAuth } from './auth.jsx';
import Landing from './pages/Landing.jsx';
import { Login, Register } from './pages/Auth.jsx';
import Placement from './pages/Placement.jsx';
import PlacementResult from './pages/PlacementResult.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Learn from './pages/Learn.jsx';
import Unit from './pages/Unit.jsx';
import Coach from './pages/Coach.jsx';
import Pronunciation from './pages/Pronunciation.jsx';
import Speaking from './pages/Speaking.jsx';
import Profile from './pages/Profile.jsx';

function Loading() {
  return <div style={{ padding: 120 }}><div className="spinner" /></div>;
}

// Guards: signed in → placement done → level chosen.
function Protected({ children, needLevel = false }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <Loading />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  if (needLevel && !user.currentLevel) return <Navigate to={user.placementLevel ? '/placement/result' : '/placement'} replace />;
  return children;
}

function GuestOnly({ children }) {
  const { user } = useAuth();
  if (user === undefined) return <Loading />;
  if (user) return <Navigate to={user.currentLevel ? '/dashboard' : '/placement'} replace />;
  return children;
}

export default function App() {
  const { pathname } = useLocation();
  useEffect(() => window.scrollTo(0, 0), [pathname]);
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<GuestOnly><Landing /></GuestOnly>} />
        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
        <Route path="/placement" element={<Protected><Placement /></Protected>} />
        <Route path="/placement/result" element={<Protected><PlacementResult /></Protected>} />
        <Route path="/dashboard" element={<Protected needLevel><Dashboard /></Protected>} />
        <Route path="/learn" element={<Protected needLevel><Learn /></Protected>} />
        <Route path="/unit/:id" element={<Protected needLevel><Unit /></Protected>} />
        <Route path="/coach" element={<Protected needLevel><Coach /></Protected>} />
        <Route path="/pronunciation" element={<Protected needLevel><Pronunciation /></Protected>} />
        <Route path="/speaking" element={<Protected needLevel><Speaking /></Protected>} />
        <Route path="/profile" element={<Protected><Profile /></Protected>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
