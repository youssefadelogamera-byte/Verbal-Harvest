// Placement item bank, calibrated to CEFR levels.
// pool: 'kids' (children track), 'general' (teens & adults), 'business'.
// skill: grammar | vocabulary | reading | listening | functional
// For listening items, `audio` is spoken by the browser's text-to-speech and is
// never shown on screen.

const q = (id, pool, level, skill, prompt, options, answer, extra = {}) =>
  ({ id, pool, level, skill, prompt, options, answer, ...extra });

export const ITEMS = [
  // ───────────────────────────── KIDS ─────────────────────────────
  // Pre-A1
  q('k0-1', 'kids', 'Pre-A1', 'vocabulary', 'Which one is a colour? 🎨', ['dog', 'red', 'run', 'ten'], 1),
  q('k0-2', 'kids', 'Pre-A1', 'vocabulary', 'How many? 🍎🍎🍎', ['two', 'four', 'three', 'five'], 2),
  q('k0-3', 'kids', 'Pre-A1', 'listening', 'Listen. What animal is it?', ['a cat 🐱', 'a fish 🐟', 'a bird 🐦', 'a horse 🐴'], 0, { audio: 'It is small. It says meow.' }),
  q('k0-4', 'kids', 'Pre-A1', 'grammar', 'Hello! My name ___ Sam.', ['are', 'am', 'is', 'be'], 2),
  q('k0-5', 'kids', 'Pre-A1', 'functional', '"How old are you?"', ['I am fine.', "I'm seven.", 'Yes, I am.', 'It is blue.'], 1),
  q('k0-6', 'kids', 'Pre-A1', 'listening', 'Listen. Where is the ball?', ['on the bed', 'under the table', 'in the box', 'on the chair'], 2, { audio: 'Where is my ball? Oh, it is in the box!' }),
  // A1
  q('k1-1', 'kids', 'A1', 'grammar', 'She ___ a sister and a brother.', ['have', 'has', 'is', 'having'], 1),
  q('k1-2', 'kids', 'A1', 'vocabulary', 'You wear these on your feet. 👟', ['gloves', 'hats', 'shoes', 'shirts'], 2),
  q('k1-3', 'kids', 'A1', 'reading', 'Read: "Tom likes football. He doesn\'t like swimming. He plays football every Saturday." — What does Tom do on Saturday?', ['He swims.', 'He plays football.', 'He reads.', 'He sleeps.'], 1),
  q('k1-4', 'kids', 'A1', 'listening', 'Listen. What does Mia want?', ['an ice cream', 'a sandwich', 'some juice', 'an apple'], 3, { audio: "Mum, I'm hungry. Can I have an apple, please?" }),
  q('k1-5', 'kids', 'A1', 'grammar', '___ you like pizza? Yes, I do!', ['Are', 'Do', 'Is', 'Does'], 1),
  q('k1-6', 'kids', 'A1', 'functional', '"Can I borrow your pencil?"', ['Here you are.', 'I am a pencil.', 'Yes, it is.', 'Goodbye.'], 0),
  // A2
  q('k2-1', 'kids', 'A2', 'grammar', 'Yesterday we ___ to the zoo.', ['go', 'goes', 'went', 'going'], 2),
  q('k2-2', 'kids', 'A2', 'vocabulary', 'An elephant is ___ than a mouse.', ['big', 'bigger', 'biggest', 'more big'], 1),
  q('k2-3', 'kids', 'A2', 'reading', 'Read: "Lily was at the park when it started to rain. She ran to a café and waited there with a hot chocolate until the sun came out." — Why did Lily go to the café?', ['She was hungry.', 'It was raining.', 'Her friend was there.', 'The park was closed.'], 1),
  q('k2-4', 'kids', 'A2', 'listening', 'Listen. What time does the film start?', ['at 4:15', 'at 5:30', 'at 5:15', 'at 3:50'], 2, { audio: "Hurry up, Ben! The film starts at quarter past five and it's already five o'clock." }),
  q('k2-5', 'kids', 'A2', 'grammar', 'There isn\'t ___ milk in the fridge.', ['some', 'any', 'many', 'a'], 1),
  q('k2-6', 'kids', 'A2', 'functional', '"Shall we play a game?"', ['Yes, I shall.', "Good idea! Let's play cards.", 'No, I am not.', 'I played.'], 1),
  // B1
  q('k3-1', 'kids', 'B1', 'grammar', 'I have lived in this town ___ I was five.', ['for', 'since', 'from', 'when'], 1),
  q('k3-2', 'kids', 'B1', 'vocabulary', 'Our teacher was very ___ when we all passed the test.', ['boring', 'proud', 'afraid', 'tired'], 1),
  q('k3-3', 'kids', 'B1', 'reading', 'Read: "Although the robot kit looked difficult, Amir followed the instructions carefully and finished it before dinner." — What can we say about Amir?', ['He gave up quickly.', 'He was careful and patient.', 'He did not read the instructions.', 'He finished it the next day.'], 1),
  q('k3-4', 'kids', 'B1', 'listening', 'Listen. Why can\'t Zoe come to the party?', ['She is ill.', 'She has a swimming competition.', "She doesn't like parties.", 'She is visiting her grandma.'], 3, { audio: "I'd love to come to your party on Saturday, but we're driving to see my grandma that weekend. Sorry!" }),
  q('k3-5', 'kids', 'B1', 'grammar', 'If it ___ tomorrow, we will stay inside.', ['rains', 'will rain', 'rained', 'raining'], 0),
  q('k3-6', 'kids', 'B1', 'functional', 'Your friend is sad because she lost her cat. What do you say?', ["That's great news!", "Oh no, I'm really sorry. Can I help you look for it?", 'Cats are animals.', 'Why not?'], 1),

  // ─────────────────────────── GENERAL ────────────────────────────
  // A1
  q('g1-1', 'general', 'A1', 'grammar', 'They ___ from Brazil.', ['is', 'am', 'are', 'be'], 2),
  q('g1-2', 'general', 'A1', 'vocabulary', 'I usually have breakfast in the ___.', ['night', 'morning', 'evening', 'week'], 1),
  q('g1-3', 'general', 'A1', 'functional', '"Nice to meet you."', ['Nice to meet you, too.', "I'm 25.", 'Yes, please.', 'See you.'], 0),
  q('g1-4', 'general', 'A1', 'listening', 'Listen. What is the woman\'s phone number?', ['0761 553 902', '0716 535 902', '0761 535 902', '0761 535 290'], 2, { audio: 'My number is oh seven six one, five three five, nine oh two.' }),
  q('g1-5', 'general', 'A1', 'reading', 'Read the sign: "Museum — Open Tuesday to Sunday, 10:00–17:00." — When is the museum closed?', ['Sunday', 'Monday', 'Tuesday', 'Every evening after 5 only'], 1),
  q('g1-6', 'general', 'A1', 'grammar', 'Where ___ he work?', ['do', 'is', 'does', 'are'], 2),
  // A2
  q('g2-1', 'general', 'A2', 'grammar', 'I ___ TV when the phone rang.', ['watched', 'was watching', 'am watching', 'watch'], 1),
  q('g2-2', 'general', 'A2', 'vocabulary', 'Could you ___ me the salt, please?', ['pass', 'borrow', 'bring up', 'take'], 0),
  q('g2-3', 'general', 'A2', 'reading', 'Read: "Hi Jo, the train is delayed by 40 minutes, so I\'ll miss the start of the meeting. Can you tell everyone? — Sam" — What does Sam want Jo to do?', ['Wait at the station', 'Start the meeting later', 'Tell the others Sam will be late', 'Book a new train'], 2),
  q('g2-4', 'general', 'A2', 'listening', 'Listen. Where are the speakers going to meet?', ['outside the cinema', 'at the bus stop', 'in the café next to the cinema', 'at home'], 2, { audio: "It's too cold to wait outside. Let's meet in the café next to the cinema at seven, OK?" }),
  q('g2-5', 'general', 'A2', 'grammar', 'This is the ___ hotel I have ever stayed in.', ['more comfortable', 'most comfortable', 'comfortablest', 'comfortable'], 1),
  q('g2-6', 'general', 'A2', 'functional', 'In a shop: "Can I try this on?"', ['Sure, the changing rooms are over there.', "No, it isn't.", "It's 20 pounds.", 'I try it.'], 0),
  // B1
  q('g3-1', 'general', 'B1', 'grammar', "I've been learning English ___ three years.", ['since', 'for', 'during', 'ago'], 1),
  q('g3-2', 'general', 'B1', 'vocabulary', 'We had to ___ the picnic because of the storm.', ['put off', 'put on', 'take off', 'give up'], 0),
  q('g3-3', 'general', 'B1', 'grammar', 'If I ___ more time, I would travel around Asia.', ['have', 'had', 'will have', 'would have'], 1),
  q('g3-4', 'general', 'B1', 'reading', 'Read: "While remote work saves commuting time, many employees report that they miss the informal conversations that used to happen in the office." — What is the main point?', ['Remote work is always better.', 'Commuting is enjoyable.', 'Remote work has a social downside.', 'Offices are too noisy.'], 2),
  q('g3-5', 'general', 'B1', 'listening', 'Listen. What is the problem with the flat?', ["It's too expensive.", 'The heating does not work.', "It's far from the city centre.", 'It is too small.'], 1, { audio: "The flat's in a great location and the rent is fine, but honestly, the heating's been broken since November and the landlord still hasn't fixed it." }),
  q('g3-6', 'general', 'B1', 'functional', 'You disagree politely in a discussion:', ["You're wrong.", "I see your point, but I'm not sure I agree.", 'No way!', 'Whatever you say.'], 1),
  // B2
  q('g4-1', 'general', 'B2', 'grammar', 'By the time we arrived, the concert ___.', ['already started', 'has already started', 'had already started', 'was already starting'], 2),
  q('g4-2', 'general', 'B2', 'vocabulary', 'The new policy had a significant ___ on small businesses.', ['effect', 'affect', 'result', 'cause'], 0),
  q('g4-3', 'general', 'B2', 'grammar', 'She suggested ___ a taxi instead of waiting.', ['to take', 'taking', 'take', 'that taking'], 1),
  q('g4-4', 'general', 'B2', 'reading', 'Read: "Critics argue that the documentary, while visually stunning, glosses over the economic factors that drove the crisis." — What do critics think?', ['The film is badly made.', 'The film ignores important causes.', 'The film exaggerates the economy.', 'The film is too long.'], 1),
  q('g4-5', 'general', 'B2', 'listening', 'Listen. What is the speaker\'s attitude?', ['enthusiastic', 'doubtful', 'angry', 'indifferent'], 1, { audio: "Well, the plan sounds good on paper, I suppose. I'm just not convinced we have the budget or the people to pull it off by March." }),
  q('g4-6', 'general', 'B2', 'grammar', 'I wish I ___ so much money on that phone last year.', ["didn't spend", "hadn't spent", "wouldn't spend", "haven't spent"], 1),
  // C1
  q('g5-1', 'general', 'C1', 'grammar', 'Not only ___ the deadline, but she also exceeded every target.', ['she met', 'did she meet', 'she did meet', 'met she'], 1),
  q('g5-2', 'general', 'C1', 'vocabulary', 'The minister\'s remarks were deliberately ___, leaving journalists unsure of her position.', ['ambiguous', 'ambitious', 'ambivalent', 'amiable'], 0),
  q('g5-3', 'general', 'C1', 'grammar', '___ the weather been better, the match would have gone ahead.', ['If', 'Had', 'Should', 'Were'], 1),
  q('g5-4', 'general', 'C1', 'reading', 'Read: "The author\'s praise of rural life is not without irony; the idyll she describes is, after all, one she abandoned at eighteen." — What does the sentence imply?', ['The author still lives in the countryside.', 'Her praise may not be entirely sincere.', 'She was forced to leave the countryside.', 'Rural life is ironic.'], 1),
  q('g5-5', 'general', 'C1', 'listening', 'Listen. What is the speaker implying?', ['The report is excellent.', 'The report was finished too early.', 'The report lacks substance.', 'The report is too short.'], 2, { audio: "It's certainly a very... thorough-looking report. Lots of charts. I just kept waiting for it to actually say something." }),
  q('g5-6', 'general', 'C1', 'vocabulary', 'The negotiations reached a(n) ___, with neither side willing to compromise.', ['impasse', 'outcome', 'agreement', 'milestone'], 0),
  // C2
  q('g6-1', 'general', 'C2', 'vocabulary', 'His explanation was so ___ that even specialists struggled to follow it.', ['lucid', 'abstruse', 'succinct', 'candid'], 1),
  q('g6-2', 'general', 'C2', 'grammar', 'Little ___ that the decision would change the company forever.', ['they realised', 'did they realise', 'they did realise', 'realised they'], 1),
  q('g6-3', 'general', 'C2', 'vocabulary', 'The committee will not ___ any deviation from the agreed procedure.', ['countenance', 'counteract', 'contend', 'condone to'], 0),
  q('g6-4', 'general', 'C2', 'reading', 'Read: "To call the reforms a success is to mistake the absence of protest for the presence of consent." — What is the writer arguing?', ['The reforms were popular.', 'Silence does not prove people agree.', 'Protests caused the reforms to fail.', 'Consent was formally given.'], 1),
  q('g6-5', 'general', 'C2', 'listening', 'Listen. What does the speaker mean?', ['She will definitely accept the offer.', 'She is inclined to refuse but is keeping options open.', 'She has already refused.', 'She does not understand the offer.'], 1, { audio: "I wouldn't go so far as to rule it out entirely, but let's just say I'm not exactly rushing to sign on the dotted line." }),
  q('g6-6', 'general', 'C2', 'vocabulary', 'Her speech struck exactly the right ___: serious but never solemn.', ['note', 'chord', 'key', 'pitch'], 0),

  // ─────────────────────────── BUSINESS ───────────────────────────
  q('b2-1', 'business', 'A2', 'functional', 'Answering the phone at work:', ["Hello, who's this?", 'Good morning, Lumen Ltd. Maria speaking. How can I help?', 'Yes?', 'What do you want?'], 1),
  q('b2-2', 'business', 'A2', 'vocabulary', 'Please send the ___ to the customer so they can pay.', ['invoice', 'receipt', 'salary', 'contract'], 0),
  q('b3-1', 'business', 'B1', 'functional', 'Opening a meeting:', ["OK, let's get started. The aim of today's meeting is to agree the budget.", 'Hi. Budget.', "Let's finish.", 'Any other business?'], 0),
  q('b3-2', 'business', 'B1', 'reading', 'Email: "Further to our call, I\'m attaching the revised quote. Please note prices are valid until 30 June." — What must the client remember?', ['The call was cancelled.', 'The quote has a time limit.', 'Prices will fall in June.', 'The quote is not attached.'], 1),
  q('b4-1', 'business', 'B2', 'vocabulary', 'We need to ___ costs by 10% without affecting quality.', ['cut back', 'cut down on', 'cut out', 'cut off'], 1),
  q('b4-2', 'business', 'B2', 'listening', 'Listen. What does the manager decide?', ['to cancel the project', 'to postpone the launch', 'to hire more staff', 'to launch early'], 1, { audio: "Given the supplier issues, I think it's wiser to push the launch back to the autumn rather than risk a half-finished product." }),
  q('b5-1', 'business', 'C1', 'functional', 'Softening a refusal in a negotiation:', ["That's impossible.", "I'm afraid that would be difficult for us to accommodate at this stage.", 'No.', "You can't have that."], 1),
  q('b5-2', 'business', 'C1', 'vocabulary', 'The merger is expected to create significant ___ between the two sales teams.', ['synergies', 'symmetries', 'sympathies', 'syndicates'], 0),
  q('b6-1', 'business', 'C2', 'reading', 'Read: "While the board has not formally withdrawn its support, its conspicuous silence at the AGM spoke volumes." — What is implied?', ['The board strongly supports the plan.', 'The board has lost confidence without saying so.', 'The AGM was cancelled.', 'The board formally opposed the plan.'], 1),
  q('b6-2', 'business', 'C2', 'vocabulary', 'The CEO was careful not to ___ the company to any timeline for the rollout.', ['commit', 'commend', 'compel', 'comply'], 0),
];

export const ITEM_BY_ID = Object.fromEntries(ITEMS.map((i) => [i.id, i]));

// Productive (speaking/writing) tasks shown after the receptive section.
export const PRODUCTIVE_TASKS = {
  children: {
    low: 'Tell me about your favourite animal. What does it look like? What can it do?',
    mid: 'Tell me about your best day ever. Where were you, who was with you, and what happened?',
  },
  teens: {
    low: 'Describe your typical school day. What do you like and not like about it?',
    mid: 'Should students be allowed to use phones in class? Give your opinion with reasons and examples.',
    high: 'Some people say social media does more harm than good for teenagers. Discuss both sides and give your own view.',
  },
  adults: {
    low: 'Introduce yourself: where you live, what you do, and what you enjoy doing in your free time.',
    mid: 'Describe a memorable trip you took. What happened, and would you recommend it?',
    high: 'Many cities are banning cars from their centres. Evaluate the advantages and disadvantages of this policy.',
  },
  business: {
    low: 'Introduce yourself professionally: your role, your company and your main responsibilities.',
    mid: 'Describe a problem you solved at work. What happened, what did you do, and what was the result?',
    high: 'Your company is considering a four-day working week. Present a balanced recommendation to the leadership team.',
  },
};
