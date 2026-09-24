import { Link } from 'react-router-dom';
import { ChatIcon, TargetIcon, WaveIcon, ChartIcon, ShieldIcon, SparkIcon, ArrowIcon } from '../components/Icons.jsx';
import { LogoMark } from '../components/Logo.jsx';

const LEVELS = [
  ['Pre-A1', 'Starter'], ['A1', 'Breakthrough'], ['A2', 'Waystage'], ['B1', 'Threshold'],
  ['B2', 'Vantage'], ['C1', 'Advanced'], ['C2', 'Mastery'],
];

const AUDIENCES = [
  ['🧸', 'Children', '6–11', 'Playful role-plays with Pip the parrot, stories and games. Pre-A1 → B1, with parent consent built in.'],
  ['🎧', 'Young Learners', '12–17', 'School life, friends, tech and exam-ready speaking skills. A1 → C1.'],
  ['🌍', 'Adults', '18+', 'Travel, social life, study and everyday confidence. A complete A1 → C2 pathway.'],
  ['💼', 'Business', 'Professionals', 'Meetings, negotiations, presentations and difficult conversations. A2 → C2.'],
];

const FEATURES = [
  [TargetIcon, 'Adaptive CEFR placement', 'A test that adapts to every answer across grammar, vocabulary, reading and listening, then assesses your speaking. You know your level before you choose it.'],
  [ChatIcon, 'AI conversation coach', 'Speak naturally with an AI partner who adjusts to your exact CEFR level, stays in role and quietly corrects your mistakes after each turn.'],
  [WaveIcon, 'Pronunciation lab', 'Read key phrases aloud and see instantly which words were clear and which need another go — with native-speed audio models.'],
  [ChartIcon, 'Examiner-style feedback', 'Speaking tasks scored on the five CEFR qualitative criteria: range, accuracy, fluency, coherence and interaction.'],
  [SparkIcon, 'Can-do curriculum', 'Every unit is anchored to a CEFR “can-do” statement, so progress means real things you can now do in English.'],
  [ShieldIcon, 'Safe for every age', 'Child-safe AI behaviour, guardian consent for young learners, and private accounts with secure sign-in.'],
];

export default function Landing() {
  return (
    <main>
      <section className="hero">
        <div className="container hero-grid">
          <div className="fade-in">
            <div className="eyebrow">CEFR-aligned · AI-powered · Speaking-first</div>
            <h1>Speak English with <em>confidence</em>, not just correctness.</h1>
            <p className="lead">Find your true CEFR level, then practise real conversations with an AI coach that listens, adapts and helps you grow — from first words to full mastery.</p>
            <div className="row" style={{ marginTop: 28 }}>
              <Link to="/register" className="btn btn-primary btn-lg">Find my level — free <ArrowIcon width={18} /></Link>
              <Link to="/login" className="btn btn-ghost btn-lg">I have an account</Link>
            </div>
            <div className="trust">
              <div><strong>7</strong>CEFR levels, Pre-A1 to C2</div>
              <div><strong>4</strong>tailored learner tracks</div>
              <div><strong>5</strong>CEFR speaking criteria</div>
            </div>
          </div>

          <div className="hero-card fade-in" aria-label="Example conversation">
            <div className="spread" style={{ marginBottom: 16 }}>
              <div className="row"><span className="msg-avatar">H</span><div><strong>Harvey</strong><div className="muted small">Role-play · Hotel reception · B1</div></div></div>
              <span className="pill pill-sage">● Listening</span>
            </div>
            <div className="bubble coach">Good evening! How can I help you?</div>
            <div className="bubble me">Hi, my room didn't cleaned today and the shower is broken.</div>
            <div className="fix"><s>didn't cleaned</s> → <b>wasn't cleaned</b> · Passive past: was/wasn't + past participle.</div>
            <div className="bubble coach">I'm so sorry about that. Would you like me to send housekeeping now, or would you prefer to change rooms?</div>
            <div className="row" style={{ marginTop: 16 }}>
              <span className="mic sm listening" style={{ pointerEvents: 'none' }}><WaveIcon /></span>
              <span className="muted small">“I'd prefer to change rooms, if possible…”</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container">
          <div className="section-head">
            <div className="eyebrow">The CEFR ladder</div>
            <h2>One international standard. Your personal path.</h2>
            <p className="muted">The Common European Framework of Reference describes what learners can do at each stage. Verbal Harvest maps every test item, lesson and speaking task to it — so your progress is measurable and recognised worldwide.</p>
          </div>
          <div className="ladder">
            {LEVELS.map(([lv, name], i) => (
              <div key={lv} className="rung" style={{ background: `var(--lv-${lv})`, minHeight: 90 + i * 26 }}>
                <b>{lv}</b><span>{name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head">
            <div className="eyebrow">Built for every learner</div>
            <h2>The right English for the right stage of life.</h2>
          </div>
          <div className="grid grid-4">
            {AUDIENCES.map(([emoji, title, ages, text]) => (
              <div key={title} className="card card-hover">
                <div style={{ fontSize: '2rem' }}>{emoji}</div>
                <h3 style={{ marginTop: 12 }}>{title}</h3>
                <div className="pill" style={{ marginBottom: 12 }}>{ages}</div>
                <p className="muted small">{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section section-alt">
        <div className="container grid grid-2" style={{ alignItems: 'center', gap: 60 }}>
          <div>
            <div className="eyebrow">How it works</div>
            <h2>From “What's my level?” to fluent conversation.</h2>
            <p className="muted">No guessing. You take the placement first, see a detailed profile of your skills, and only then choose where to begin.</p>
          </div>
          <div className="steps stack">
            <div className="step"><h3>Create your account</h3><p className="muted">Choose your learner profile — Children, Young Learners, Adults or Business.</p></div>
            <div className="step"><h3>Take the adaptive placement</h3><p className="muted">About 15 minutes: listening, reading, grammar and vocabulary that adapt to you, plus a short speaking task.</p></div>
            <div className="step"><h3>Choose your level</h3><p className="muted">See your recommended CEFR level and skill breakdown, then confirm or adjust it.</p></div>
            <div className="step"><h3>Speak every day</h3><p className="muted">Role-plays, pronunciation drills and speaking tasks — with instant, level-appropriate feedback.</p></div>
          </div>
        </div>
      </section>

      <section className="section">
        <div className="container">
          <div className="section-head">
            <div className="eyebrow">Features</div>
            <h2>Everything you need to actually communicate.</h2>
          </div>
          <div className="grid grid-3">
            {FEATURES.map(([Icon, title, text]) => (
              <div key={title} className="card">
                <div className="feature-icon"><Icon /></div>
                <h3>{title}</h3>
                <p className="muted small" style={{ marginBottom: 0 }}>{text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="cta-band">
            <div>
              <h2 style={{ color: '#fff' }}>Discover your CEFR level today.</h2>
              <p style={{ margin: 0 }}>Free account · Adaptive placement · Personal speaking coach</p>
            </div>
            <Link to="/register" className="btn btn-accent btn-lg">Start the placement test <ArrowIcon width={18} /></Link>
          </div>
        </div>
      </section>

      <footer className="site">
        <div className="container spread">
          <div className="row"><span style={{ width: 28, display: 'inline-block' }}><LogoMark /></span> © {new Date().getFullYear()} Verbal Harvest</div>
          <div>CEFR levels and descriptors are based on the Council of Europe's Common European Framework of Reference for Languages.</div>
        </div>
      </footer>
    </main>
  );
}
