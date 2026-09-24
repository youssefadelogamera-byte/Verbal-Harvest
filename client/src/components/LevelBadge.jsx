export default function LevelBadge({ level, size = '' }) {
  return <span className={`level-badge ${size}`} style={{ '--c': `var(--lv-${level})` }}>{level}</span>;
}
