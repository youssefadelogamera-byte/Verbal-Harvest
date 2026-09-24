// CEFR reference data. Descriptors are paraphrased from the Common European
// Framework of Reference (Council of Europe, Companion Volume 2020), written in
// learner-friendly language.

export const LEVELS = ['Pre-A1', 'A1', 'A2', 'B1', 'B2', 'C1', 'C2'];

export const LEVEL_INFO = {
  'Pre-A1': {
    name: 'Starter',
    band: 'Basic user',
    summary: 'Recognises and uses a small number of familiar words and simple phrases.',
    kidSummary: 'You know some English words and can say hello, count and name colours!',
    speaking: 'Can say simple things about themselves (name, age, family) using single words and memorised phrases.',
    guidedHours: 60,
  },
  A1: {
    name: 'Breakthrough',
    band: 'Basic user',
    summary: 'Understands and uses familiar everyday expressions and very basic phrases for concrete needs. Can introduce themselves and ask simple personal questions.',
    kidSummary: 'You can talk about yourself, your family and things you like with short sentences.',
    speaking: 'Can interact simply if the other person talks slowly and is ready to help.',
    guidedHours: 100,
  },
  A2: {
    name: 'Waystage',
    band: 'Basic user',
    summary: 'Understands frequently used expressions about immediate areas (family, shopping, work). Communicates in simple, routine exchanges.',
    kidSummary: 'You can chat about your day, your school and your hobbies, and ask simple questions.',
    speaking: 'Can describe background, immediate environment and needs in simple terms.',
    guidedHours: 200,
  },
  B1: {
    name: 'Threshold',
    band: 'Independent user',
    summary: 'Understands the main points of clear input on familiar matters. Deals with most travel situations and describes experiences, hopes and plans with brief reasons.',
    kidSummary: 'You can tell stories, explain what you think and deal with everyday situations in English.',
    speaking: 'Can connect phrases to describe experiences, dreams and ambitions, and give brief reasons and explanations.',
    guidedHours: 400,
  },
  B2: {
    name: 'Vantage',
    band: 'Independent user',
    summary: 'Understands the main ideas of complex texts and interacts with a degree of fluency and spontaneity that makes regular interaction with expert speakers possible without strain.',
    kidSummary: 'You can discuss lots of topics fluently and explain your opinions clearly.',
    speaking: 'Can give clear, detailed descriptions and explain a viewpoint, giving the advantages and disadvantages of options.',
    guidedHours: 600,
  },
  C1: {
    name: 'Effective Operational Proficiency',
    band: 'Proficient user',
    summary: 'Understands demanding, longer texts and recognises implicit meaning. Expresses ideas fluently and spontaneously, using language flexibly for social, academic and professional purposes.',
    kidSummary: 'You use English easily and flexibly, almost like your own language.',
    speaking: 'Can present clear, well-structured descriptions of complex subjects, integrating sub-themes and rounding off with a conclusion.',
    guidedHours: 800,
  },
  C2: {
    name: 'Mastery',
    band: 'Proficient user',
    summary: 'Understands virtually everything heard or read. Expresses themselves spontaneously, very fluently and precisely, differentiating finer shades of meaning even in complex situations.',
    kidSummary: 'You understand almost everything and speak with great precision.',
    speaking: 'Can convey finer shades of meaning precisely and reformulate smoothly around any difficulty.',
    guidedHours: 1100,
  },
};

// Qualitative aspects of spoken language (CEFR Table 3), used for speaking rubrics.
export const SPEAKING_CRITERIA = [
  { key: 'range', label: 'Range', hint: 'Breadth of vocabulary and structures' },
  { key: 'accuracy', label: 'Accuracy', hint: 'Grammatical control' },
  { key: 'fluency', label: 'Fluency', hint: 'Flow and ease of speech' },
  { key: 'interaction', label: 'Interaction', hint: 'Turn-taking and responding' },
  { key: 'coherence', label: 'Coherence', hint: 'Linking ideas clearly' },
];

export const AUDIENCES = {
  children: {
    label: 'Children',
    ages: '6–11',
    description: 'Playful, picture-rich learning with short activities, stories and songs. Mapped to Pre-A1 → B1.',
    levels: ['Pre-A1', 'A1', 'A2', 'B1'],
    startLevel: 'A1',
  },
  teens: {
    label: 'Young Learners',
    ages: '12–17',
    description: 'School life, friendships, technology and exam-ready skills. Mapped to A1 → C1.',
    levels: ['A1', 'A2', 'B1', 'B2', 'C1'],
    startLevel: 'A2',
  },
  adults: {
    label: 'Adults',
    ages: '18+',
    description: 'Real-life communication for travel, social life, study and work. Full A1 → C2 pathway.',
    levels: ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'],
    startLevel: 'B1',
  },
  business: {
    label: 'Business',
    ages: 'Professionals',
    description: 'Meetings, negotiations, presentations and email with a professional register. A2 → C2.',
    levels: ['A2', 'B1', 'B2', 'C1', 'C2'],
    startLevel: 'B1',
  },
};

export const levelIndex = (l) => LEVELS.indexOf(l);
export const clampToAudience = (level, audience) => {
  const allowed = AUDIENCES[audience].levels;
  const i = levelIndex(level);
  if (i < levelIndex(allowed[0])) return allowed[0];
  if (i > levelIndex(allowed[allowed.length - 1])) return allowed[allowed.length - 1];
  return level;
};
