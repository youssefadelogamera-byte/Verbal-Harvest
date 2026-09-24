import Anthropic from '@anthropic-ai/sdk';
import { LEVEL_INFO, LEVELS, levelIndex } from './data/cefr.js';

const MODEL = process.env.CLAUDE_MODEL || 'claude-opus-5';
const client = process.env.ANTHROPIC_API_KEY || process.env.ANTHROPIC_AUTH_TOKEN ? new Anthropic() : null;

export const aiEnabled = () => Boolean(client);

// ───────────────────────── Claude helper ─────────────────────────

class RefusalError extends Error {}

async function structured({ system, messages, schema, effort, maxTokens = 4000 }) {
  const response = await client.beta.messages.create({
    model: MODEL,
    max_tokens: maxTokens,
    system,
    messages,
    thinking: { type: 'adaptive' },
    output_config: { effort, format: { type: 'json_schema', schema } },
    // Re-run on Anthropic's recommended fallback model if a request is declined.
    betas: ['server-side-fallback-2026-07-01'],
    fallbacks: 'default',
  });
  if (response.stop_reason === 'refusal') throw new RefusalError('The coach could not respond to that message.');
  const text = response.content.filter((b) => b.type === 'text').map((b) => b.text).join('');
  return JSON.parse(text);
}

const AUDIENCE_GUIDE = {
  children: `The learner is a CHILD (6–11). Be warm, playful and very encouraging. Use short sentences, simple words and the occasional emoji.
Keep all content strictly age-appropriate. Never ask for personal details such as full name, address, school name, phone number or photos.
If the child mentions something worrying (being hurt, scared, unsafe), respond kindly and encourage them to talk to a parent, teacher or trusted adult.`,
  teens: `The learner is a TEENAGER (12–17). Be friendly and relatable, reference school, hobbies, music, tech. Keep content age-appropriate and never ask for personal identifying details.`,
  adults: `The learner is an ADULT. Be natural, respectful and engaging, like a skilled conversation partner.`,
  business: `The learner is a BUSINESS PROFESSIONAL. Use a professional register, realistic workplace language and model effective business communication.`,
};

function levelGuide(level) {
  const i = levelIndex(level);
  if (i <= 1) return 'Use very short sentences (5–8 words), high-frequency words, present tense. Ask one simple question at a time. Speak slowly and clearly.';
  if (i === 2) return 'Use short, clear sentences with common vocabulary and simple past/future forms. Ask one question at a time.';
  if (i === 3) return 'Use clear, natural language on familiar topics; some phrasal verbs and linking words. Invite reasons and explanations.';
  if (i === 4) return 'Use natural speed and a wider range of vocabulary and structures. Challenge the learner to justify views and speculate.';
  return 'Use fully natural, idiomatic English with nuance, including irony and implicit meaning. Push for precision, register control and reformulation.';
}

// ─────────────────────── Conversation coach ───────────────────────

const COACH_SCHEMA = {
  type: 'object',
  properties: {
    reply: { type: 'string', description: 'Your next line in the conversation, in character.' },
    corrections: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          original: { type: 'string' },
          corrected: { type: 'string' },
          explanation: { type: 'string' },
        },
        required: ['original', 'corrected', 'explanation'],
        additionalProperties: false,
      },
    },
    tip: { type: 'string', description: 'One short, useful language tip or better phrase (empty string if none).' },
    goalAchieved: { type: 'boolean', description: 'True once the learner has achieved the scenario goal.' },
  },
  required: ['reply', 'corrections', 'tip', 'goalAchieved'],
  additionalProperties: false,
};

export async function coachReply({ audience, level, scenario, topic, messages, name }) {
  if (!client) return offlineCoach({ audience, level, scenario, topic, messages, name });

  const setting = scenario
    ? `ROLE-PLAY: You play ${scenario.aiRole}. Setting: ${scenario.setting}. The learner's goal: ${scenario.goal}.
Stay in character. Guide the learner towards the goal naturally; don't do the talking for them.`
    : `FREE CONVERSATION on the topic: "${topic || 'anything the learner wants to talk about'}". You are a friendly conversation partner.`;

  const system = `You are Harvey, the AI speaking coach inside Verbal Harvest, an English speaking app aligned to the CEFR.
The learner, ${name}, is working at CEFR ${level} (${LEVEL_INFO[level].name}). Target speaking descriptor: "${LEVEL_INFO[level].speaking}"

${AUDIENCE_GUIDE[audience]}

LANGUAGE LEVEL: ${levelGuide(level)} Stretch the learner slightly above their level (i+1) but keep them comfortable.

${setting}

The learner is usually SPEAKING (their text comes from speech recognition), so ignore punctuation, capitalisation and obvious transcription glitches.
Keep "reply" short enough to be read aloud comfortably (1–3 sentences; up to 4 at C1–C2). End most turns with a question or prompt that keeps them talking.
In "corrections", list only genuine errors from the learner's LAST message that matter at their level (max 3, most important first). Explanations should be one short sentence${audience === 'children' ? ', super simple and kind' : ''}. Leave the array empty if there are none — praise is better than nitpicking.
Never correct inside "reply"; stay natural there.`;

  const convo = messages.slice(-20).map((m) => ({ role: m.role === 'coach' ? 'assistant' : 'user', content: m.text }));
  if (!convo.length || convo[0].role !== 'user') convo.unshift({ role: 'user', content: '(The learner has just joined. Start the conversation.)' });

  return structured({ system, messages: convo, schema: COACH_SCHEMA, effort: 'low' });
}

// ─────────────────────── Speaking assessment ───────────────────────

const ASSESS_SCHEMA = {
  type: 'object',
  properties: {
    level: { type: 'string', enum: LEVELS },
    scores: {
      type: 'object',
      properties: Object.fromEntries(['range', 'accuracy', 'fluency', 'coherence', 'interaction'].map((k) => [k, { type: 'integer', description: '0-100' }])),
      required: ['range', 'accuracy', 'fluency', 'coherence', 'interaction'],
      additionalProperties: false,
    },
    summary: { type: 'string' },
    strengths: { type: 'array', items: { type: 'string' } },
    improvements: { type: 'array', items: { type: 'string' } },
    improvedVersion: { type: 'string' },
  },
  required: ['level', 'scores', 'summary', 'strengths', 'improvements', 'improvedVersion'],
  additionalProperties: false,
};

export async function assessSpeaking({ task, transcript, audience, targetLevel }) {
  if (!client) return offlineAssess({ transcript, targetLevel });

  const system = `You are a certified CEFR speaking examiner. Rate the learner's response using the CEFR qualitative aspects of spoken language (range, accuracy, fluency, coherence, interaction) as described in the CEFR Companion Volume.
The response was captured with speech recognition (or typed), so ignore punctuation, capitalisation and transcription artefacts; judge the language itself.
Be calibrated and fair: a short or off-task answer cannot demonstrate a high level. Very short answers (under ~15 words) rarely exceed A2.
Audience: ${audience}. ${audience === 'children' ? 'Write feedback for a child: simple, warm and encouraging.' : 'Write concise, specific, actionable feedback.'}
Scores are 0-100 relative to CEFR C2. Give 2-3 strengths and 2-3 improvements. "improvedVersion" rewrites the learner's answer one level higher, keeping their ideas.`;

  return structured({
    system,
    messages: [{ role: 'user', content: `Task: ${task}\n${targetLevel ? `Learner's current working level: ${targetLevel}\n` : ''}Learner response:\n"""${transcript}"""` }],
    schema: ASSESS_SCHEMA,
    effort: 'medium',
  });
}

// ─────────────────────── Offline fallbacks ───────────────────────
// Rule-based behaviour so the app is fully usable without an API key.

const RULES = [
  [/\bi\s+(is|are)\b/i, 'I am', 'Use "am" with "I".'],
  [/\b(he|she|it)\s+(go|have|do|like|want|play|work|live)\b/i, null, 'Add -s (or use has/does/goes) after he/she/it in the present simple.'],
  [/\bdid(?:n't| not)\s+(\w+ed|went|saw|came|ate|took)\b/i, null, 'After "did/didn\'t", use the base verb (e.g. "didn\'t go").'],
  [/\bmore\s+(better|bigger|easier|faster|worse)\b/i, null, 'Don\'t use "more" with a comparative that already ends in -er.'],
  [/\bi am agree\b/i, 'I agree', '"Agree" is a verb, so we say "I agree".'],
  [/\bpeoples\b/i, 'people', '"People" is already plural.'],
  [/\bexplain me\b/i, 'explain to me', 'We "explain something TO someone".'],
  [/\bsince (\d+|two|three|four|five|six|ten) (years|months|weeks|days)\b/i, null, 'Use "for" with a period of time (for 3 years) and "since" with a starting point (since 2020).'],
];

function ruleCorrections(text) {
  const out = [];
  for (const [re, fix, explanation] of RULES) {
    const m = text.match(re);
    if (!m) continue;
    let corrected = fix;
    if (!corrected) {
      if (/^(he|she|it)$/i.test(m[1])) {
        const v = m[2].toLowerCase();
        corrected = `${m[1]} ${{ go: 'goes', have: 'has', do: 'does' }[v] || v + 's'}`;
      } else if (/^did/i.test(m[0])) corrected = m[0].replace(/\s\w+$/, ' …(base form)');
      else if (/^more/i.test(m[0])) corrected = m[1];
      else if (/^since/i.test(m[0])) corrected = m[0].replace(/^since/i, 'for');
    }
    out.push({ original: m[0], corrected, explanation });
    if (out.length >= 3) break;
  }
  return out;
}

const FOLLOW_UPS = {
  low: ['That is great! Can you tell me more?', 'Nice! What else do you like?', 'Good! And what about you — how do you feel?', 'Wonderful! Why do you like it?'],
  mid: ['Interesting! Why do you think that is?', 'Could you give me an example?', 'What happened next?', 'How did that make you feel?'],
  high: ['That\'s a fair point — but how would you respond to someone who disagrees?', 'Could you unpack that a little more?', 'What do you see as the main trade-off there?', 'How might that play out in the long term?'],
};

function offlineCoach({ audience, level, scenario, topic, messages, name }) {
  const band = levelIndex(level) <= 2 ? 'low' : levelIndex(level) <= 4 ? 'mid' : 'high';
  const learnerTurns = messages.filter((m) => m.role === 'user');
  const last = learnerTurns.at(-1)?.text || '';
  if (!learnerTurns.length) {
    const opener = scenario
      ? `Hi ${name}! I'm ${scenario.aiRole.split(',')[0]}. Let's imagine: ${scenario.setting}. ${band === 'low' ? 'Are you ready?' : 'Shall we begin?'}`
      : `Hi ${name}! Let's chat about "${topic || 'anything you like'}". ${band === 'low' ? 'What do you like about it?' : 'What comes to mind first?'}`;
    return { reply: audience === 'children' ? `${opener} 😊` : opener, corrections: [], tip: '', goalAchieved: false, offline: true };
  }
  const pool = FOLLOW_UPS[band];
  const words = last.split(/\s+/).filter(Boolean).length;
  const tip = words < 6 && band !== 'low'
    ? 'Try to give longer answers: add a reason with "because" or an example with "for example".'
    : '';
  return {
    reply: pool[learnerTurns.length % pool.length],
    corrections: ruleCorrections(last),
    tip,
    goalAchieved: learnerTurns.length >= 6,
    offline: true,
  };
}

const CONNECTORS = /\b(because|although|however|therefore|whereas|moreover|nevertheless|so|but|while|since|unless|despite|in addition|on the other hand|as a result|for example)\b/gi;

export function offlineAssess({ transcript }) {
  const words = transcript.toLowerCase().match(/[a-z']+/g) || [];
  const n = words.length;
  const unique = new Set(words).size;
  const ttr = n ? unique / n : 0;
  const longWords = words.filter((w) => w.length >= 8).length / Math.max(n, 1);
  const connectors = (transcript.match(CONNECTORS) || []).length;
  const sentences = Math.max(1, transcript.split(/[.!?]+/).filter((s) => s.trim()).length);
  const errors = ruleCorrections(transcript).length;

  let score = 0;
  score += Math.min(n / 120, 1) * 35;
  score += Math.min(ttr / 0.7, 1) * 20;
  score += Math.min(longWords / 0.15, 1) * 20;
  score += Math.min(connectors / 6, 1) * 20;
  score += Math.min((n / sentences) / 18, 1) * 5;
  score -= errors * 6;
  score = Math.max(0, Math.min(100, score));

  const idx = n < 8 ? 0 : n < 20 ? Math.min(2, Math.floor(score / 18)) : Math.min(6, Math.floor(score / 15));
  const level = LEVELS[Math.max(1, idx)];
  const s = Math.round(score);
  return {
    level,
    scores: {
      range: Math.round(Math.min(100, (ttr * 60 + longWords * 250))),
      accuracy: Math.max(10, 90 - errors * 15),
      fluency: Math.round(Math.min(100, n * 0.9)),
      coherence: Math.round(Math.min(100, 30 + connectors * 12)),
      interaction: s,
    },
    summary: `Estimated from length, vocabulary variety and linking (practice mode). Connect an AI key for a full examiner-style assessment.`,
    strengths: [
      n >= 40 ? 'You gave a well-developed answer.' : 'You answered the question.',
      connectors >= 2 ? 'You used linking words to connect ideas.' : 'Your ideas were understandable.',
    ],
    improvements: [
      n < 40 ? 'Develop your answer further with reasons and examples.' : 'Vary your sentence structures more.',
      connectors < 3 ? 'Use more linking words (however, because, as a result…).' : 'Try more precise, less common vocabulary.',
    ],
    improvedVersion: '',
    offline: true,
  };
}

export { RefusalError };
