import { Link } from 'react-router-dom';

export function LogoMark() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <rect width="64" height="64" rx="16" fill="#10213a" />
      <path d="M14 18h36a4 4 0 0 1 4 4v18a4 4 0 0 1-4 4H30l-10 8v-8h-6a4 4 0 0 1-4-4V22a4 4 0 0 1 4-4z" fill="#d4a24c" />
      <path d="M32 40V24m0 6c-4 0-6-3-6-6 4 0 6 3 6 6zm0 0c4 0 6-3 6-6-4 0-6 3-6 6zm0 6c-4 0-6-3-6-6 4 0 6 3 6 6zm0 0c4 0 6-3 6-6-4 0-6 3-6 6z"
        stroke="#10213a" strokeWidth="2.2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function Logo({ to = '/' }) {
  return <Link to={to} className="brand"><LogoMark /> Verbal Harvest</Link>;
}
