# Athar for teachers

Athar follows each learner across years and shows where they are strong, where they struggle, and where a struggle may have started. Plain code reaches the findings, every finding lists the records behind it, and a named teacher approves each one. It runs on your own computer and works with no internet.

Arabic version: [FOR-TEACHERS.ar.md](FOR-TEACHERS.ar.md). The same guide with pictures opens from inside Athar under **Guide and help**.

Athar is an early version. It opens with a made-up school so you can try everything. Do not put real learner data in it yet.

## The first ten minutes

1. **Start Athar.** The first time, it asks who is using it. Choose **I am a teacher or I work in a school**.
2. **Choose your name** under **Signed in as**, at the bottom of the side panel. Every decision is recorded under that name.
3. **Open Class overview.** It shows how many records there are, what is waiting for your decision, and the average for each area in each grade.
4. **Open a learner** under **Learners**, then open the **Learning map**. Click a topic with low results and press **Trace back**.
5. **Open the Review queue** and decide one finding.

## The pages

| Page | What it is for |
|---|---|
| Class overview | Where the class stands, by area and grade. It describes topics, not learners. |
| School map | The whole school by topic. No page ranks learners. |
| Learners | One learner: profile, learning map, patterns held over several terms, and what was approved. |
| My teaching | What you taught, when, and with which approach. |
| Review queue | Findings waiting for a teacher. Approve, edit or reject each one. |
| Agent | Start the assistant on a learner and a document. It needs the model. |
| Add records | A marks sheet (exact, no model) or a document for the assistant to read. |
| School | Add a learner, sign-in and accounts, backup, save or delete one learner's record. |
| Audit log | Every action and who did it. |

## Deciding a finding

Open a finding in the **Review queue**. It shows the statement, why it is suggested, and the records behind it, line by line. Then:

- **Approve** it if it matches what you know of the learner.
- **Edit** it if the idea is right but the wording is not.
- **Reject** it if it does not match.

The assistant cannot approve anything. A learner's printable report is built from approved findings only.

## Adding records

**A marks sheet.** On **Add records**, download the sheet for a class, fill it in with Excel, and upload it. This is the exact way and it needs no model. One column per topic keeps the marks useful: a total alone cannot show where the difficulty is.

**A document.** A typed quiz sheet or a note in your own words. The assistant reads it, records what it finds, and stops to ask you when something is unclear. Write the learner's record code in the document, not the name.

**A new learner.** On the **School** page, use **Add a learner**. The learner gets a short record code.

## Adding to the curriculum

Athar comes with the Cambridge curriculum for Mathematics, Science and English, Years 1 to 11. On the **School** page, under **The curriculum**, the school admin can add topics for another grade or another subject. Before sign-in is turned on, the teacher whose name is chosen can do it.

1. Choose the subject (or type a new one), the grade and the term.
2. Give Athar the topics. Type or paste them, one on each line, or upload the contents page of the book as a text, Word or Excel file, or as a picture. For a PDF, take a screenshot of the contents page.
3. Tick **Let the model read it** if you want the model to list the topics and suggest which topic needs which. A picture is always read by the model. This takes about a minute.
4. **Check the draft.** Every topic shows its name in both languages, its grade, term and area, the topics it needs first, and the later topics that need it. Fix the names. Remove every link you do not agree with and add the ones that are missing.
5. Tick **I checked every topic and every link**, then press **Approve and add to the curriculum**.

From then on the new topics appear in the marks sheet, the learning map and the trace-back.

What to know:

- The model reads topic names well. Its links are suggestions, and in our tries some were wrong. A wrong link sends a teacher or a parent to the wrong place to start helping, so the check in step 4 is the real safeguard.
- The books that came with Athar are never changed. An addition sits on top of them, under your name.
- An addition can be withdrawn as long as no record uses its topics. It cannot be edited after approval: withdraw it and make it again.
- Parents cannot add to the curriculum.

## Sign-in

Sign-in is off at first, so anyone at the computer can open Athar and act as any teacher. To turn it on, open the **School** page and create the school admin. From then on every page needs a username and a password, only the admin adds teachers, and each teacher sees only the learners of their own classes.

## What Athar will not do

- It never ranks learners or compares one learner with another.
- It never labels a learner or assigns a track.
- It never states a finding without the records behind it.
- It reads only what is on record. You know things the records do not. If a finding does not match what you see, reject it.

## Keeping it safe

On the **School** page, press **Make a backup now** and keep a copy somewhere else as well. The same page can save one learner's whole record as a file, or delete it for good.

## A made-up family, for showing the parent side

To show the parent side with something on every page, run `uv run athar family-demo` on a fresh copy. It sets up an invented parent with three invented children and results across three school years. No model is used.
