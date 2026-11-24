# Which model to use

Athar uses a language model for three small jobs, and only on the Agent page:

1. read a quiz sheet or a teacher's note, in Arabic or English, and turn it into rows;
2. choose which checks to run on a learner's records;
3. write one or two careful sentences from facts it is given.

The conclusions themselves come from plain code, so a modest model is enough for jobs 1 and 2. Job 3 in Arabic is the hard one. Everything else in Athar works with no model at all.

Athar talks to any program or service that speaks the OpenAI protocol. How to connect one is in [GETTING-STARTED.md](GETTING-STARTED.md).

## The short answer

| What you have | Use | How sure are we |
|---|---|---|
| A laptop with 8 GB of memory and no graphics card | Qwen3.5 4B, or a cloud key | A guess. We found no Arabic score for a model this small. Expect it to read sheets and to be slow. |
| 16 GB of memory | Gemma 4 12B, or Qwen3.5 9B | Qwen3.5 9B is the one Athar was built and tested with. Gemma 4 12B is a guess from its larger siblings' scores. |
| A graphics card with 12 to 16 GB | Gemma 4 12B at a higher quality setting | A guess, as above. |
| A graphics card with 24 GB | Gemma 4 31B | It had the highest score of any open model on a public Arabic writing test (see below). We have not run Athar on the official build. |
| An API key | A current flagship from OpenAI or Anthropic | Their earlier models led the same test. No Arabic result exists yet for the current ones. |

Model names are as they appear in LM Studio's own search (publisher `lmstudio-community`). They were checked in November 2026 and will go out of date. When they do, look for the newest model of the same family that fits your memory.

## Arabic: what you need to know

- **Reading Arabic works on the small model.** In our tries Qwen3.5 9B read a quiz sheet written in Arabic and recorded every mark correctly.
- **Writing careful Arabic did not.** Asked to word findings in Arabic, the same model dropped a word from a topic name, added a claim that was not in the facts, and described a learner's understanding as "deep". None of that was caught by the guard.
- **So Athar does not let the model word Arabic findings by default.** Findings and questions in Arabic use fixed sentences written in code. They are correct and plain. To let your model write them instead, set `ATHAR_ARABIC_WORDING=model`, and read what it writes before you trust it.
- **Notes for families** in Arabic are always written by the model, and a teacher must approve each one. This is where a better model helps most.

## What we tried ourselves

In November 2026 we gave four models on one computer the same four sets of facts and asked each to word a finding in Arabic, once. A script checked that every topic name, number and term was still there and that the guard passed. Then we read each sentence.

| Model | Kept every name and number | What we saw when we read them |
|---|---|---|
| Qwen3.5 9B | 3 of 4 | Rewrote a term code in words. Spoke of "the student" where it should speak of the results. |
| Qwen3.6 27B | 4 of 4 | Added that results show "solid understanding", which is a claim about the child, not the records. |
| Qwen3.8 27B | 3 of 4 | Left out an average. Used an odd word for a strand. Called results "weak". |
| A community variant of Gemma 4 31B | 4 of 4 | Attached an average to the wrong topic in one sentence. The script did not catch it. |

What this shows, and what it does not:

- The larger models kept names and numbers better and read more naturally. The first sentence took 50 to 75 seconds on them while the model loaded, then under 15 seconds each.
- Every model made at least one mistake that matters on a child's record, in only four sentences.
- Four sentences, one try each, on one computer, is not a measurement. The Gemma tried was a third-party variant, not Google's own build.

This is why Arabic findings use fixed sentences unless you turn the model's wording on.

## Models made for Arabic

It is natural to reach for a model built for Arabic. On the one public test that scores Arabic writing, the small Arabic-first models did not come out ahead of the general ones. Scores are out of 100, on AraGen, as listed in May 2026:

| Model | Score |
|---|---|
| GPT-5 (closed) | 84 |
| Claude Opus 4.5 (closed) | 80 |
| Gemma 4 31B (open) | 73 |
| Gemma 4 26B (open) | 67 |
| Jais 2 70B (open, Arabic-first) | 52 |
| Jais 2 8B (open, Arabic-first) | 34 |
| Qwen3 8B (open, an older Qwen) | 27 |
| Fanar 1 9B (open, Arabic-first) | 16 |

Read this with care:

- The test is run by the company that makes Jais.
- It does not include the model Athar is tested with (Qwen3.5 9B), Gemma 4 12B, or newer Arabic-first models such as Fanar 2 and Falcon Arabic.
- Other leaderboards, such as the Open Arabic LLM Leaderboard, are mostly multiple-choice questions. A high score there does not show that a model writes careful Arabic.
- No public test measures what Athar needs: restating given facts without adding anything.

If you want to try an Arabic-first model, Jais 2 8B has an official build for LM Studio, and Fanar 2 27B has community builds and lists Egyptian Arabic. We have not run Athar on either. Check each model's licence before using it in a paid service: Cohere's Arabic model, for one, is not licensed for commercial use.

## Reading a photo of a paper

On the family side a parent can photograph a marked paper. For that the model must be able to see pictures, and it must be on the same computer: Athar refuses to send a photo anywhere else, because a paper usually shows the child's name.

- **The Windows package:** "Download the model" fetches the model and the part that reads pictures (two files, 6.1 GB in all).
- **LM Studio:** pick a model marked as able to see images. Qwen3.5 9B from `lmstudio-community` is, and it is the one we tried.
- **A cloud key:** photos are not sent. Type the result in instead.

How well it reads is in `EVALS.md`. In short: good on a clear, straight picture; unreliable on a dim or tilted one.

## Things that trip people up

- **Thinking mode.** Recent Qwen and Gemma models can "think" before answering, which makes every step slow. Athar asks local models not to. Hosted services may reject that request, so for them set `ATHAR_LLM_REASONING=default`.
- **Very small models.** LM Studio's own documents say structured output is unreliable on models under about 7 billion parameters. If a run records odd rows, this is the first thing to suspect.
- **Tool calling.** Athar needs the model to call tools. Not every model does this well through LM Studio. If a run stops at "investigate" with no checks chosen, Athar's own coverage check still runs the checks, so you lose little.
- **Speed.** With no graphics card, one run can take several minutes. That is the model, not Athar.
- **Privacy.** A model on your own computer keeps everything on it. A cloud model receives the document and the records the agent reads, by record code and without names. Do not send real learners' records to a cloud model.

## Hosted services

Any service with an OpenAI-compatible address works through the three `ATHAR_LLM_...` settings. OpenAI and Claude also work by pasting a key on the Agent page. Addresses as documented in November 2026:

| Service | Address |
|---|---|
| OpenAI | built in: paste the key on the Agent page |
| Anthropic (Claude) | built in: paste the key on the Agent page |
| Google | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| Cohere | `https://api.cohere.ai/compatibility/v1` |
| Groq | `https://api.groq.com/openai/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |

We have run Athar's agent only on a local model. The cloud paths are covered by tests that do not call the services, so treat them as untried in practice.

## How to check a model yourself

1. Start Athar on the made-up school and open the Agent page.
2. Pick the learner whose quiz sheet is in the inbox, choose your model, and start a run.
3. Check three things: the six marks were recorded as they are on the sheet; the question with no answer was recorded as not attempted, not as zero; and the finding names the right topics.
4. To judge Arabic writing, set `ATHAR_ARABIC_WORDING=model`, run again, and read the finding beside the facts listed under it in the review queue. Every topic name, number and term should be there, and nothing else.

The small script we used for the table above is `evals/arabic_wording_check.py`. With LM Studio running: `uv run python evals/arabic_wording_check.py <model name>`. Read the sentences it prints; do not trust the count alone.

If you find a model that does this well in Arabic on an ordinary computer, please tell us in an issue. It is the most useful single thing a contributor can report.

## Sources

Checked in November 2026. Scores and names change; follow the links for the current state.

- AraGen scores: https://benchmarklist.com/benchmarks/aragen_v3/ and https://huggingface.co/spaces/inceptionai/Arabic-Leaderboards
- Gemma 4: https://huggingface.co/lmstudio-community/gemma-4-12B-it-GGUF and https://huggingface.co/lmstudio-community/gemma-4-31B-it-GGUF
- Qwen3.5: https://huggingface.co/lmstudio-community/Qwen3.5-9B-GGUF and https://huggingface.co/lmstudio-community/Qwen3.5-4B-GGUF
- Jais 2: https://huggingface.co/inceptionai/Jais-2-8B-Chat-GGUF
- Fanar 2: https://huggingface.co/QCRI/Fanar-2-27B-Instruct
- Cohere's Arabic model and its licence: https://huggingface.co/CohereLabs/c4ai-command-r7b-arabic-02-2025
- Open Arabic LLM Leaderboard, what it measures: https://huggingface.co/blog/leaderboard-arabic-v2
- LM Studio on tools and structured output: https://lmstudio.ai/docs/developer/openai-compat/tools and https://lmstudio.ai/docs/developer/openai-compat/structured-output
- Service addresses: https://aistudio.google.com/docs/openai , https://docs.cohere.com/docs/compatibility-api , https://console.groq.com/docs/models , https://openrouter.ai/docs/quickstart
