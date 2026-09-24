// Speaking-first curriculum. Every unit is anchored to a CEFR "can-do"
// statement, has key language to drill (pronunciation lab) and a role-play
// scenario for the AI conversation coach.
//
// Tracks: 'kids' (children), 'general' (teens & adults), 'business'.
// Teens get the general units with youth-oriented role-play contexts.

const u = (id, level, track, title, canDo, focus, phrases, scenario) =>
  ({ id, level, track, title, canDo, focus, phrases, scenario });

// scenario: [aiRole, setting, learnerGoal]
export const UNITS = [
  // ─────────────── KIDS ───────────────
  u('k-pa1-1', 'Pre-A1', 'kids', 'Hello, Friends!', 'I can say hello and tell someone my name and age.', 'Greetings · numbers 1–10',
    ['Hello! My name is Leo.', "I'm seven years old.", 'Nice to meet you!', 'Goodbye, see you soon!'],
    ['Pip, a friendly talking parrot', 'a sunny playground', 'Say hello, tell Pip your name and age, and ask Pip his name.']),
  u('k-pa1-2', 'Pre-A1', 'kids', 'Colours & Toys', 'I can name colours and my favourite toys.', 'Colours · toys · "I like…"',
    ['My ball is red.', 'I like my blue car.', 'What colour is it?', "It's green!"],
    ['Pip the parrot', 'a toy shop full of colourful toys', 'Tell Pip the colours of three toys and which one you like best.']),
  u('k-pa1-3', 'Pre-A1', 'kids', 'Animal Safari', 'I can name animals and say what they can do.', 'Animals · can/can\'t',
    ['A fish can swim.', "A dog can't fly.", 'I like elephants.', 'Look! A monkey!'],
    ['Ranger Ruby, a safari guide', 'a jeep on an African safari', 'Name the animals you see and say one thing each animal can do.']),
  u('k-a1-1', 'A1', 'kids', 'My Family', 'I can talk about my family members.', 'Family words · has/have got',
    ['This is my mum.', "I've got one brother.", 'My grandad is funny.', 'Have you got a sister?'],
    ['Pip the parrot', 'looking at a family photo album', 'Describe three people in your family and ask Pip about his family.']),
  u('k-a1-2', 'A1', 'kids', 'Yummy Food', 'I can say what food I like and don\'t like.', 'Food · like/don\'t like · please/thank you',
    ['I like pizza.', "I don't like carrots.", 'Can I have some juice, please?', 'Thank you!'],
    ['Chef Coco, a cheerful cook', 'a picnic in the park', 'Tell Chef Coco what you like and ask politely for food.']),
  u('k-a1-3', 'A1', 'kids', 'My School Day', 'I can say what I do at school.', 'School objects · present simple',
    ['I go to school at eight.', 'I have got a pencil case.', 'My favourite subject is art.', 'We play at break time.'],
    ['Ms Bell, a kind teacher', 'a colourful classroom', 'Tell Ms Bell about your school day and your favourite subject.']),
  u('k-a2-1', 'A2', 'kids', 'Weekend Adventures', 'I can tell a short story about what I did.', 'Past simple · time words',
    ['Last Saturday I went to the beach.', 'We built a big sandcastle.', 'Then we ate ice cream.', 'It was great fun!'],
    ['Pip the parrot', 'Monday morning at school', 'Tell Pip what you did at the weekend, with at least three things in order.']),
  u('k-a2-2', 'A2', 'kids', 'Super Pets', 'I can compare animals and things.', 'Comparatives & superlatives',
    ['A cheetah is faster than a lion.', 'The whale is the biggest animal.', 'My cat is smaller than my dog.', 'Which is the best pet?'],
    ['Dr Vet, a friendly vet', 'a pet clinic', 'Compare two pets and choose the best pet for your family, saying why.']),
  u('k-b1-1', 'B1', 'kids', 'Save the Planet', 'I can give my opinion and simple reasons.', 'Opinions · because/so · should',
    ['I think we should recycle more.', 'Plastic is bad for the ocean because fish eat it.', 'We could walk to school.', 'What do you think?'],
    ['Captain Green, an eco-hero', 'a school eco-club meeting', 'Suggest three ways your class can help the planet and explain why.']),
  u('k-b1-2', 'B1', 'kids', 'Story Makers', 'I can tell a story with a beginning, middle and end.', 'Narrative tenses · sequencers',
    ['Once upon a time, there was a brave girl.', 'While she was walking, she heard a noise.', 'Suddenly, a dragon appeared!', 'In the end, they became friends.'],
    ['Pip the parrot', 'a cosy reading corner', 'Make up a short story together with Pip, taking turns to add to it.']),

  // ─────────────── GENERAL ───────────────
  u('g-a1-1', 'A1', 'general', 'First Introductions', 'I can introduce myself and ask others basic personal questions.', 'to be · question words',
    ["Hi, I'm Ana. I'm from Spain.", 'What do you do?', "I'm a student.", 'Where do you live?'],
    ['Sam, a new classmate / colleague', 'the first day of an English course', 'Introduce yourself and find out three things about Sam.']),
  u('g-a1-2', 'A1', 'general', 'At the Café', 'I can order food and drink and ask about prices.', 'Would like · numbers · prices',
    ["I'd like a coffee, please.", 'How much is it?', 'Can I have the bill, please?', 'Here you are.'],
    ['a barista', 'a busy city café', 'Order a drink and a snack, ask the price and pay.']),
  u('g-a1-3', 'A1', 'general', 'Daily Routines', 'I can describe my daily routine.', 'Present simple · time',
    ['I get up at seven.', 'I usually take the bus.', 'I have lunch at one.', 'In the evening I watch TV.'],
    ['Jo, a friendly neighbour', 'a chat in the lift', 'Describe your typical day and ask Jo about theirs.']),
  u('g-a1-4', 'A1', 'general', 'Finding Your Way', 'I can ask for and understand simple directions.', 'Imperatives · prepositions of place',
    ['Excuse me, where is the station?', 'Go straight on.', 'Turn left at the bank.', "It's next to the park."],
    ['a local passer-by', 'a street in a new city', 'Ask how to get to the train station and check you understood.']),
  u('g-a2-1', 'A2', 'general', 'Weekend Plans', 'I can make, accept and decline invitations.', 'going to · present continuous for future',
    ['Are you free on Saturday?', "Would you like to come to the cinema?", "I'd love to!", "Sorry, I'm busy. Maybe next time?"],
    ['Alex, a friend', 'a phone call on Thursday evening', 'Invite Alex out, agree on a time and a place.']),
  u('g-a2-2', 'A2', 'general', 'Shopping & Returns', 'I can deal with simple transactions in shops.', 'Too / enough · polite requests',
    ['Do you have this in a medium?', "It's too small for me.", 'Could I return this, please?', 'Here is my receipt.'],
    ['a shop assistant', 'a clothes shop', 'Return a jacket that is the wrong size and ask for a different one.']),
  u('g-a2-3', 'A2', 'general', 'Past Experiences', 'I can describe past events and experiences in simple terms.', 'Past simple · present perfect (ever/never)',
    ['Have you ever been to London?', 'I went there last summer.', 'It was amazing.', "I've never tried sushi."],
    ['Kim, a travel-loving friend', 'a café catch-up', 'Swap stories about places you have visited and food you have tried.']),
  u('g-a2-4', 'A2', 'general', 'At the Doctor\'s', 'I can explain simple health problems.', 'Body · symptoms · should',
    ["I've got a headache.", 'I feel sick.', 'It started two days ago.', 'Should I take anything?'],
    ['a GP (family doctor)', 'a medical centre', 'Explain your symptoms and understand the doctor\'s advice.']),
  u('g-b1-1', 'B1', 'general', 'Travel Problems', 'I can deal with most situations likely to arise while travelling.', 'Complaints · requests · modals',
    ["I'm afraid my room hasn't been cleaned.", 'Would it be possible to change rooms?', 'My flight has been cancelled.', 'What are my options?'],
    ['a hotel receptionist', 'a hotel lobby late at night', 'Politely complain about a problem and negotiate a solution.']),
  u('g-b1-2', 'B1', 'general', 'Hopes & Ambitions', 'I can describe my dreams, hopes and ambitions and give reasons.', 'Future forms · hope/plan/would like',
    ["I'm hoping to study abroad.", 'In five years I would like to…', 'The main reason is that…', "I'm planning to save up."],
    ['a career / study advisor', 'an advising session', 'Explain your goals and ask for advice on how to reach them.']),
  u('g-b1-3', 'B1', 'general', 'Giving Opinions', 'I can express and justify opinions in a discussion.', 'Opinion language · agreeing & disagreeing',
    ['In my opinion…', 'I see what you mean, but…', "That's a good point.", 'I completely agree.'],
    ['Chris, a friend with strong opinions', 'a debate about whether cities should be car-free', 'Share your view, respond to Chris\'s arguments, and find common ground.']),
  u('g-b1-4', 'B1', 'general', 'Telling Stories', 'I can narrate a story and describe my reactions.', 'Narrative tenses · linkers',
    ['I was walking home when…', 'All of a sudden…', 'I felt really embarrassed.', 'In the end, it turned out that…'],
    ['a curious friend', 'a dinner party', 'Tell a funny or surprising story from your life and answer follow-up questions.']),
  u('g-b2-1', 'B2', 'general', 'Debating Issues', 'I can develop a clear argument, weighing advantages and disadvantages.', 'Discourse markers · concession',
    ['On the one hand…, on the other hand…', 'Admittedly, …', 'This would inevitably lead to…', 'All things considered, …'],
    ['a debate moderator', 'a TV debate on the four-day week', 'Argue your position, rebut a counter-argument and conclude.']),
  u('g-b2-2', 'B2', 'general', 'Job Interview', 'I can present myself confidently and answer detailed questions.', 'Present perfect continuous · hedging',
    ["I've been working in… for three years.", 'One of my key strengths is…', 'A challenge I faced was…', 'What would the first months look like?'],
    ['a hiring manager', 'a job interview', 'Answer competency questions with examples and ask two smart questions.']),
  u('g-b2-3', 'B2', 'general', 'Problem Solving', 'I can speculate about causes and consequences and suggest solutions.', 'Modals of deduction · conditionals',
    ['It might have been caused by…', 'If we had known, we would have…', 'Why don\'t we…?', "That's worth a try."],
    ['a flatmate', 'a shared flat with a broken boiler', 'Work out what went wrong and agree on a plan together.']),
  u('g-b2-4', 'B2', 'general', 'Culture & Media', 'I can discuss films, books and news, giving detailed reactions.', 'Adjectives of opinion · relative clauses',
    ['What struck me most was…', 'It was gripping from start to finish.', 'The plot, which is based on…', "I'd highly recommend it."],
    ['a film-club member', 'a film club discussion', 'Review a film or series you watched and compare opinions.']),
  u('g-c1-1', 'C1', 'general', 'Nuanced Argument', 'I can argue a complex case, integrating sub-themes and anticipating objections.', 'Cleft sentences · inversion',
    ['What concerns me most is…', 'It could be argued that…', 'Not only does this…, but it also…', 'That said, we should not overlook…'],
    ['a sharp academic panellist', 'a university panel on AI in education', 'Present a nuanced position and handle probing questions.']),
  u('g-c1-2', 'C1', 'general', 'Diplomacy & Tact', 'I can handle sensitive conversations with appropriate tact.', 'Softening · indirectness',
    ['I wonder if we might…', "I don't want to overstep, but…", 'I can see where you\'re coming from.', 'Perhaps we could look at it another way.'],
    ['a friend who has made a questionable decision', 'a quiet café', 'Share honest concerns without damaging the friendship.']),
  u('g-c1-3', 'C1', 'general', 'Presenting Ideas', 'I can give a well-structured presentation and handle questions.', 'Signposting · rhetorical devices',
    ["Let me begin by…", 'This brings me to my next point.', "I'm glad you asked that.", 'To sum up, …'],
    ['a conference audience member', 'a short conference talk', 'Present an idea you care about in three parts and field a question.']),
  u('g-c2-1', 'C2', 'general', 'Precision & Style', 'I can convey finer shades of meaning precisely, using idiom naturally.', 'Idiom · collocation · register shifting',
    ['That\'s splitting hairs, frankly.', 'To put it another way, …', 'I\'d stop short of calling it…', 'It\'s a moot point.'],
    ['a witty literary critic', 'a radio arts programme', 'Debate whether a classic novel deserves its reputation, with precision and wit.']),
  u('g-c2-2', 'C2', 'general', 'Mediation', 'I can mediate between people with differing views and reformulate complex ideas.', 'Mediation strategies · paraphrase',
    ['If I understand you both correctly…', 'What I\'m hearing is…', 'Where you both seem to agree is…', 'Could we reframe the question as…?'],
    ['two neighbours in dispute (played by the coach)', 'a community meeting', 'Mediate a dispute and guide them to a compromise.']),
  u('g-c2-3', 'C2', 'general', 'Spontaneous Talk', 'I can speak spontaneously on abstract topics, reformulating smoothly.', 'Abstract vocabulary · fillers & repair',
    ['That\'s a fascinating question — let me think.', 'Or rather, what I mean is…', 'It hinges on how we define…', 'There\'s a paradox there.'],
    ['a philosopher on a podcast', 'a podcast recording', 'Discuss whether technology makes us freer, thinking aloud.']),

  // ─────────────── BUSINESS ───────────────
  u('b-a2-1', 'A2', 'business', 'Workplace Introductions', 'I can introduce myself and my role at work.', 'Job titles · present simple',
    ["I work in the marketing department.", "I'm responsible for customer orders.", 'This is my colleague, Tom.', 'How long have you worked here?'],
    ['a new colleague', 'the office kitchen on your first day', 'Introduce yourself, your role and ask about the colleague\'s job.']),
  u('b-a2-2', 'A2', 'business', 'Phone Calls', 'I can make and take simple business calls.', 'Telephone language · spelling',
    ['Could I speak to Ms Lee, please?', "I'm calling about the order.", 'Can I take a message?', 'Could you spell that, please?'],
    ['a receptionist at a supplier', 'a phone call', 'Call to check the status of an order and leave a message.']),
  u('b-b1-1', 'B1', 'business', 'Running a Meeting', 'I can take part in routine meetings and state my view.', 'Meeting language · suggestions',
    ["Let's move on to the next point.", 'I suggest we…', 'Could you clarify that?', 'So, to summarise the action points…'],
    ['a team member', 'a weekly team meeting', 'Chair a short meeting: set the agenda, gather views and agree actions.']),
  u('b-b1-2', 'B1', 'business', 'Customer Service', 'I can handle customer requests and simple complaints.', 'Apologising · offering solutions',
    ["I'm sorry to hear that.", 'Let me look into it for you.', 'What I can do is…', 'Is there anything else I can help with?'],
    ['an unhappy customer', 'a customer service call', 'Calm the customer, find out the issue and offer a solution.']),
  u('b-b2-1', 'B2', 'business', 'Negotiating Deals', 'I can negotiate terms, make concessions and reach agreement.', 'Conditionals · bargaining language',
    ["If you could increase the volume, we'd be able to…", 'That\'s a bit higher than we expected.', 'Would you be willing to…?', "I think we've got a deal."],
    ['a procurement manager', 'a supplier negotiation', 'Negotiate price and delivery terms and close the deal.']),
  u('b-b2-2', 'B2', 'business', 'Presenting Results', 'I can present data clearly and explain trends.', 'Describing trends · signposting',
    ['Sales rose sharply in Q3.', 'As you can see from this chart…', 'This was mainly due to…', 'Going forward, we expect…'],
    ['a senior manager', 'a quarterly review', 'Present your team\'s results, explain the causes and answer a question.']),
  u('b-c1-1', 'C1', 'business', 'Leading Change', 'I can persuade stakeholders and handle objections diplomatically.', 'Persuasion · hedging',
    ['The case for change is compelling.', 'I appreciate your concerns; however…', 'What this means for your team is…', 'Let\'s pilot it first.'],
    ['a sceptical department head', 'a one-to-one meeting', 'Persuade the stakeholder to support a new process.']),
  u('b-c1-2', 'C1', 'business', 'Difficult Conversations', 'I can deliver sensitive feedback constructively.', 'Softening · feedback models',
    ['I wanted to talk about…', 'The impact of this has been…', 'How do you see it?', 'What support would help?'],
    ['a team member who is missing deadlines', 'a private feedback meeting', 'Give clear, empathetic feedback and agree a plan.']),
  u('b-c2-1', 'C2', 'business', 'Boardroom Strategy', 'I can debate strategy at executive level with precision and nuance.', 'Strategic vocabulary · nuance',
    ['The risk-reward profile is compelling.', 'We\'d be remiss not to consider…', 'It hinges on execution.', 'I\'d push back on that assumption.'],
    ['a board member', 'a board meeting on international expansion', 'Argue for or against expansion and address pointed challenges.']),
  u('b-c2-2', 'C2', 'business', 'Crisis Communication', 'I can communicate authoritatively and reassuringly under pressure.', 'Press statements · reformulation',
    ['Our priority right now is…', 'I want to be absolutely clear…', "We don't yet have all the facts, but…", 'We will provide an update by…'],
    ['a persistent journalist', 'a press briefing after a data breach', 'Handle tough questions transparently without speculating.']),
];

export const UNIT_BY_ID = Object.fromEntries(UNITS.map((x) => [x.id, x]));

const TEEN_CONTEXT = {
  'g-a1-1': ['a new classmate', 'the first day at a new school'],
  'g-a1-2': ['a server', 'a smoothie bar'],
  'g-a2-1': ['a friend from school', 'group chat that turned into a call'],
  'g-b1-2': ['a school careers advisor', 'a careers meeting'],
  'g-b2-2': ['an interviewer for a summer internship', 'an internship interview'],
};

export function trackFor(audience) {
  if (audience === 'children') return 'kids';
  if (audience === 'business') return 'business';
  return 'general';
}

// Units for an audience at a level. Falls back to the general track when a
// specialised track has no units at that level.
export function unitsFor(audience, level) {
  const track = trackFor(audience);
  let list = UNITS.filter((x) => x.track === track && x.level === level);
  if (!list.length) list = UNITS.filter((x) => x.track === 'general' && x.level === level);
  if (audience === 'teens') {
    list = list.map((x) => TEEN_CONTEXT[x.id]
      ? { ...x, scenario: [TEEN_CONTEXT[x.id][0], TEEN_CONTEXT[x.id][1], x.scenario[2]] }
      : x);
  }
  return list;
}

// Free-conversation topics for the AI coach, per audience.
export const FREE_TOPICS = {
  children: ['My favourite games', 'Animals I love', 'What I want to be', 'A magic day'],
  teens: ['Music & playlists', 'Gaming and esports', 'Social media', 'Dream travel destinations', 'School stress'],
  adults: ['Travel stories', 'Food & cooking', 'Work-life balance', 'Technology in daily life', 'Films & series'],
  business: ['Small talk with clients', 'Remote & hybrid work', 'Your industry trends', 'Leadership', 'Networking events'],
};
