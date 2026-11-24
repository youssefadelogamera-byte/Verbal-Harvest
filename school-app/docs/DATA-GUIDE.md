# Putting your own class data into Athar

For a teacher or a school's IT person who wants to try Athar with real class data, and for a developer helping them. Read [Before you use real records](#before-you-use-real-records) first.

[بالعربي](DATA-GUIDE.ar.md)

## What Athar needs to say anything useful

- **Each mark tied to a topic and a term.** A mark with no topic cannot be used.
- **Marks per question or per topic, not only a total.** A total of 14 out of 20 says the learner lost 6 marks. It does not say where. Two learners with 14 can have quite different gaps, so a total cannot be traced.
- **The same learner code across years.** Athar gives each learner a record code such as K-42. Keep that one record every year. Do not add the learner again in a new grade.
- **Enough terms and enough marks.** These numbers come from `src/athar/graph.py`:

| What | The rule in the code |
|---|---|
| A pattern | At least 3 terms in a row that have marks, all low or all strong. This cannot be lowered. |
| Low, strong | A term's average below 50%, above 80% |
| Tracing back | Starts from a topic whose average over all its marks is below 50% |
| Confidence | Marks divided by (marks plus 4): one mark gives 0.2, four give 0.5, twelve give 0.75 |
| An earlier topic with no records | Confidence is capped at 0.35, or Athar says it cannot tell where the difficulty began |

Athar does not refuse a topic with one or two marks. It gives a low confidence. Treat anything under four marks as a hint.

## The marks sheet, step by step

One sheet is one quiz. No model reads it. Plain code checks it.

1. Open **Add records**. Choose the class, grade, term, subject and number of questions (up to 60). Press **Download for Excel**, or the CSV button.
2. The workbook has a **Marks** sheet to fill and a **Topics** sheet that lists the subject's topics for that grade and earlier grades.

   ```
   Learner code | Name      | Q1      | Q2      | Q3
   Topic        |           | <topic> | <topic> | <topic>
   Out of       |           | 2       | 3       | 2
   K-42         | Zainab H. | 1       | 3       | 0
   ```

   - **Learner code row**: the headings. A column with an empty heading is ignored.
   - **Topic row**: the topic each question tests. In Excel, pick it from the list in the cell, which comes from the Topics sheet. In a CSV file, type the topic name or its id exactly as that sheet shows it.
   - **Out of row**: the full mark for each question, a number above zero.
   - **One row per learner.** Learners are matched by code only. The name is for your eyes and is not stored from the sheet.
3. Fill in the marks. **Zero** means the learner tried and got nothing, and it counts. **Not attempted** saves no record: leave the cell blank, or write `-`, `x`, `na`, `n/a`, `abs`, `absent`, `غ` or `غائب`.
4. Arabic and English sheets both work, whatever language the page is in. Arabic-Indic digits (٠ to ٩) and a decimal comma are accepted.
5. Save as `.xlsx` or `.csv`, up to 2 MB. Only the first sheet of a workbook is read.
6. On **Add records**, name the quiz, set the school year and term, choose the file and press **Check the sheet**. Nothing is saved yet. You see every mark, each question's topic, and anything unclear: a missing or unknown topic, a missing "Out of", a mark that is not a number or is above the maximum, an unknown code, a code twice, a learner outside your classes.
7. A sheet with even one problem cannot be saved. Fix the file and check again. Then press **Save**. Each mark becomes one record under your name.

**Uploading the same quiz twice is safe.** Athar knows a mark by learner, school year, term, grade, subject, quiz name and question number, and skips marks it already holds. So:

- Give every quiz its own name. Two quizzes with the same name, in the same subject, grade and term, are treated as one. The same name in two subjects is fine.
- The name can be in Arabic or English.
- Uploading again does not change a saved mark. See [Mistakes and removal](#mistakes-and-removal).

## Getting old records in

- **Old Excel mark books.** Download a template for each old quiz, copy the marks in, and fill the Topic row from the question paper. Set the year and term the quiz was given in. If you no longer know what a question tested, leave that column out.
- **Only term totals.** Athar cannot trace from a total. You may enter a total as one column under one topic only if the whole test was about that topic. A mixed test filed under one topic gives wrong findings.
- **Start now.** Tag this term's quizzes and build forward. Patterns can appear after three terms. Until then you get each learner's map by topic, and Athar says which terms have no marks.

## Real data is messier than the made-up school

- **One question tests two topics.** A column takes one topic. Split it into two columns (Q3a, Q3b) and split the marks, or choose the main topic.
- **A quiz with no topic recorded.** The check refuses it. Tag it from the paper or leave it out. Do not guess.
- **Different maximum marks.** Each mark is stored as a share of its "Out of". Every question then counts the same in an average, whatever its maximum.
- **Absent on the day.** Leave the cells blank or write `abs`. Nothing is saved. Do not enter zero.
- **Joined mid-year or changed school.** Add the learner with the grade and year they joined. Athar reports earlier topics as taught before the record and guesses nothing. Another school's record cannot be imported yet.
- **Re-sits.** Upload the re-sit as its own quiz with its own name. Both sets of marks count. Athar does not replace the first.
- **Copied or inflated marks.** Athar cannot tell. It takes marks as given. Do not enter a mark you know is not the learner's own work, or withdraw it.
- **Very small classes.** Findings are per learner, so class size does not change them. The school map shows topic totals, and in a small group a total can point at one child.
- **A teacher who marks harder.** Athar makes no adjustment, so a change of teacher can look like a change in the learner. Say so when you review.
- **Topics taught in a different order.** A mark is filed under the term you choose at upload. The trace follows the map's "needs this first" links, which are a draft no teacher has reviewed.
- **Topics the map does not have.** The check refuses them. Use a map topic only if it truly is the same thing. Otherwise leave the question out and propose a map change (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

## Documents for the agent

A quiz sheet or a note can go to the agent. This needs a model.

- Plain text only: `.md`, `.txt` or `.csv`, saved as UTF-8, up to 1 MB. The agent reads about the first 8,000 characters.
- One learner per document. Write the record code as `Learner K-42`, never the name. A document that names only other learners is not recorded.
- Give the year and term in the text, or in the file name like `2026-T1`.
- This is how days absent and written notes get in. The marks sheet holds marks only.
- **Know this:** the agent saves the rows as it reads them. It does not wait for you to confirm each row. It keeps a row only if the row quotes words from the document. The teacher's approval comes later, at the findings and the notes. After a run, open the learner's map, read the new records, and withdraw any that are wrong.

## Getting the best out of it

- Tag every question with its topic.
- Give small quizzes often. One big test gives one term of data.
- Write a one-line note when something unusual happened.
- Record days absent each term.
- Note how you taught a topic. The page has no form for this yet, so "what worked" stays empty for your own data.
- Review each finding and open the records it cites. Reject what does not match the child you know.

## Mistakes and removal

- **One wrong record.** Open the learner, click the topic on the learning map, and press **Withdraw** beside the row under **Records for this concept**. Give a reason. The row is kept, marked as withdrawn, and leaves the analysis. Your name and the reason go in the audit log, and Athar says how many findings cite it. A mark cannot be edited. To enter the right one, upload a small sheet with only that learner and that question, under a new quiz name.
- **One learner.** On the **School** page, under **Look after the records**, choose the learner, type their record code and press **Delete this record for good**. Once sign-in is on, only the school admin can. It cannot be undone, and earlier backups still hold the record until you delete them.
- **Backups.** On the same page press **Make a backup now**, then **Save a copy elsewhere**. A backup holds names and is not encrypted. Nothing runs on a schedule.

```
uv run athar backup                           # one file in data/backups, newest 14 kept
uv run athar restore data/backups/<file>      # stop the app first
uv run athar export-learner K-42              # everything held about one learner, as a file
uv run athar delete-learner K-42 --code K-42  # for good
```

## Before you use real records

This is not legal advice.

Athar has been tested on made-up data only. [SECURITY.md](../SECURITY.md) lists what the code protects and what it does not: among the gaps, the stored records are not encrypted, consent is not recorded, and backups are manual. Read it before you decide. If you go ahead:

- **Get the guardian's written consent first,** and keep it yourself.
- **Create the school admin before anything else.** Until then anyone at the computer can see and delete every record.
- **Keep the computer and every backup safe.** A USB stick with a backup is the mark book itself.
- **Use record codes, not names, in every document.**
- **Do not send real records to a cloud model.** Use a model that runs on the school's computer.
- **Take local legal advice.** Egyptian law treats children's data as sensitive. We are not lawyers.
- **Never put real learner data in the public repository,** an issue or a screenshot.
