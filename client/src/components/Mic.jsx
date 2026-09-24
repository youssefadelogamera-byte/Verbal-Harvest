import { MicIcon, StopIcon } from './Icons.jsx';

export default function Mic({ listening, onStart, onStop, size = '', label }) {
  return (
    <button
      type="button"
      className={`mic ${size} ${listening ? 'listening' : ''}`}
      onClick={listening ? onStop : onStart}
      aria-label={listening ? 'Stop recording' : label || 'Start speaking'}
      title={listening ? 'Stop' : label || 'Speak'}
    >
      {listening ? <StopIcon /> : <MicIcon />}
    </button>
  );
}
