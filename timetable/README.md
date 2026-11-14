# School Timetable Builder

Builds a clash-free weekly timetable for a whole school: every class, teacher, department and special room.

**No installation and no server.** Open `index.html` in any modern browser (Chrome, Edge, Firefox, Safari). Your data is kept in that browser automatically. Use **Save to file** to keep a backup or move it to another computer, and **Open file** to load it again.

## How to use it

Work through the tabs from left to right:

1. **School & periods**: school days (e.g. Sunday–Thursday) and the teaching periods with their times.
2. **Departments**: e.g. Mathematics, Science, Languages. Each gets a colour on the timetable.
3. **Teachers**: department, the most periods they can teach per day, and any times they are unavailable (part-time staff, days off).
4. **Subjects**: department, and a room type when the subject needs a special room (Science Lab, Computer Lab, Gym…).
5. **Classes**: each section (7A, 7B…) with its grade.
6. **Rooms**: only special rooms. Ordinary lessons happen in the class's own room.
7. **Lessons**: who teaches what to which class, how many periods a week, and how many of them are double periods. You can add a subject to a whole grade in one step. The **Workload check** flags any class or teacher with more periods than fit in the week.
8. **Timetable**: click **Generate timetable**.

Tip: click **Load example school** to try everything with sample data first.

## What the generator guarantees

- No teacher, class or room is booked twice at the same time.
- Teacher and class unavailability is respected.
- Teachers never exceed their maximum periods per day.
- Each subject is spread across the week (e.g. a 5-period subject in a 5-day week gets one period a day).
- Double periods are two consecutive periods on the same day.
- Subjects that need a special room get a free room of that type.
- Idle gaps in class and teacher days are kept to a minimum.

If something cannot be placed, the app lists what is missing and the likely cause.

## After generating

- View by **Class**, **Teacher**, **Department** (all its teachers on one sheet) or **Room**.
- **Adjust by hand**: click a lesson, then click an empty slot to move it, or another lesson to swap. You are warned if the change causes a clash.
- **Print**: choose "All" in the list to print every class or teacher, one per landscape page.
- **Export CSV**: opens in Excel or Google Sheets.
- **Who is free?**: pick a day and period to find teachers available to cover an absence.

## Files

| File | Purpose |
| --- | --- |
| `index.html`, `styles.css`, `app.js` | The app |
| `solver.js` | The scheduling engine (works in the browser and in Node) |
| `sample-data.js` | The example school |
| `tests/solver.test.js` | Engine tests: `npm test` from this folder |
