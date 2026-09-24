import { useCallback, useEffect, useRef, useState } from 'react';

const Recognition = typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);
export const speechSupported = Boolean(Recognition);
export const ttsSupported = typeof window !== 'undefined' && 'speechSynthesis' in window;

let cachedVoice = null;
function pickVoice() {
  if (cachedVoice) return cachedVoice;
  const voices = window.speechSynthesis.getVoices();
  cachedVoice =
    voices.find((v) => /en-GB/i.test(v.lang) && /natural|neural|google|serena|daniel|libby|sonia/i.test(v.name)) ||
    voices.find((v) => /en-(US|GB)/i.test(v.lang) && /natural|neural|google|samantha|aria|jenny/i.test(v.name)) ||
    voices.find((v) => /^en/i.test(v.lang)) || null;
  return cachedVoice;
}
if (ttsSupported) window.speechSynthesis.onvoiceschanged = () => { cachedVoice = null; };

export function speak(text, { rate = 0.95, onEnd } = {}) {
  if (!ttsSupported || !text) { onEnd?.(); return; }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, ''));
  const voice = pickVoice();
  if (voice) u.voice = voice;
  u.lang = voice?.lang || 'en-GB';
  u.rate = rate;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.speak(u);
}
export const stopSpeaking = () => ttsSupported && window.speechSynthesis.cancel();

// Speaking rate by CEFR level: slower for beginners.
export const rateFor = (level) => ({ 'Pre-A1': 0.78, A1: 0.82, A2: 0.88, B1: 0.95 }[level] || 1);

export function useSpeechRecognition({ lang = 'en-US' } = {}) {
  const recRef = useRef(null);
  const [listening, setListening] = useState(false);
  const [finalText, setFinalText] = useState('');
  const [interim, setInterim] = useState('');
  const [error, setError] = useState('');

  useEffect(() => () => recRef.current?.abort(), []);

  const start = useCallback(() => {
    if (!Recognition) { setError('Speech recognition is not supported in this browser. Try Chrome, Edge or Safari — or type instead.'); return; }
    setError('');
    setFinalText('');
    setInterim('');
    stopSpeaking();
    const rec = new Recognition();
    rec.lang = lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (e) => {
      let fin = '';
      let tmp = '';
      for (let i = 0; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) fin += t; else tmp += t;
      }
      setFinalText(fin.trim());
      setInterim(tmp);
    };
    rec.onerror = (e) => {
      if (e.error === 'not-allowed') setError('Microphone access was blocked. Please allow the microphone in your browser settings.');
      else if (e.error !== 'aborted' && e.error !== 'no-speech') setError('We could not hear you clearly. Please try again.');
    };
    rec.onend = () => { setListening(false); setInterim(''); };
    recRef.current = rec;
    rec.start();
    setListening(true);
  }, [lang]);

  const stop = useCallback(() => recRef.current?.stop(), []);
  const reset = useCallback(() => { setFinalText(''); setInterim(''); }, []);

  return { listening, transcript: finalText, interim, error, start, stop, reset, supported: speechSupported };
}

// Word-level alignment (Levenshtein) between a target sentence and what was heard.
const norm = (s) => s.toLowerCase().replace(/[’']/g, "'").replace(/[^a-z0-9' ]+/g, ' ').split(/\s+/).filter(Boolean);
const NUM = { '1': 'one', '2': 'two', '3': 'three', '4': 'four', '5': 'five', '6': 'six', '7': 'seven', '8': 'eight', '9': 'nine', '10': 'ten' };
const eq = (a, b) => a === b || NUM[a] === b || NUM[b] === a || a.replace(/'/g, '') === b.replace(/'/g, '');

export function compareSpeech(target, heard) {
  const t = norm(target);
  const h = norm(heard);
  const d = Array.from({ length: t.length + 1 }, (_, i) => Array.from({ length: h.length + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= t.length; i++) {
    for (let j = 1; j <= h.length; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (eq(t[i - 1], h[j - 1]) ? 0 : 1));
    }
  }
  const matched = new Array(t.length).fill(false);
  let i = t.length; let j = h.length;
  while (i > 0 && j > 0) {
    if (eq(t[i - 1], h[j - 1]) && d[i][j] === d[i - 1][j - 1]) { matched[i - 1] = true; i--; j--; }
    else if (d[i][j] === d[i - 1][j - 1] + 1) { i--; j--; }
    else if (d[i][j] === d[i - 1][j] + 1) i--;
    else j--;
  }
  const words = target.split(/\s+/).filter(Boolean);
  // Map normalised words back to display words (1:1 in practice for our phrase lists).
  const display = words.length === t.length ? words : t;
  const score = t.length ? Math.round((matched.filter(Boolean).length / t.length) * 100) : 0;
  const extra = Math.max(0, h.length - t.length);
  return { score: Math.max(0, score - extra * 3), words: display.map((w, k) => ({ word: w, ok: matched[k] })) };
}
