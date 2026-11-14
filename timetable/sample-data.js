/* Example school used by "Load example school" and by the tests. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.TimetableSample = api;
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  function sampleSchool() {
    const periods = [
      ['08:00', '08:45'], ['08:45', '09:30'], ['09:30', '10:15'], ['10:35', '11:20'],
      ['11:20', '12:05'], ['12:25', '13:10'], ['13:10', '13:55'],
    ].map(([start, end], i) => ({ label: String(i + 1), start, end }));

    const departments = [
      { id: 'd-math', name: 'Mathematics', color: '#2563eb' },
      { id: 'd-sci', name: 'Science', color: '#16a34a' },
      { id: 'd-lang', name: 'Languages', color: '#9333ea' },
      { id: 'd-hum', name: 'Humanities', color: '#d97706' },
      { id: 'd-arts', name: 'Arts & PE', color: '#db2777' },
      { id: 'd-tech', name: 'Technology', color: '#0891b2' },
    ];

    const subjects = [
      { id: 's-math', name: 'Mathematics', short: 'MATH', deptId: 'd-math', roomType: '' },
      { id: 's-ara', name: 'Arabic', short: 'ARA', deptId: 'd-lang', roomType: '' },
      { id: 's-eng', name: 'English', short: 'ENG', deptId: 'd-lang', roomType: '' },
      { id: 's-sci', name: 'Science', short: 'SCI', deptId: 'd-sci', roomType: 'Science Lab' },
      { id: 's-soc', name: 'Social Studies', short: 'SOC', deptId: 'd-hum', roomType: '' },
      { id: 's-rel', name: 'Religion', short: 'REL', deptId: 'd-hum', roomType: '' },
      { id: 's-pe', name: 'Physical Education', short: 'PE', deptId: 'd-arts', roomType: 'Gym' },
      { id: 's-art', name: 'Art', short: 'ART', deptId: 'd-arts', roomType: 'Art Room' },
      { id: 's-ict', name: 'ICT', short: 'ICT', deptId: 'd-tech', roomType: 'Computer Lab' },
    ];

    const teacherList = [
      ['t1', 'Ahmed Hassan', 'd-math'], ['t2', 'Mona Ali', 'd-math'], ['t3', 'Karim Said', 'd-math'],
      ['t4', 'Sara Mostafa', 'd-lang'], ['t5', 'Omar Fathy', 'd-lang'], ['t6', 'Nour Adel', 'd-lang'],
      ['t7', 'Hany Samir', 'd-lang'], ['t8', 'Laila Mahmoud', 'd-lang'], ['t9', 'Dina Kamal', 'd-lang'],
      ['t10', 'Tarek Nabil', 'd-sci'], ['t11', 'Rania Farouk', 'd-sci'], ['t12', 'Mahmoud Gaber', 'd-sci'],
      ['t13', 'Heba Salah', 'd-hum'], ['t14', 'Amr Khaled', 'd-hum'], ['t15', 'Yasmin Reda', 'd-hum'],
      ['t16', 'Sherif Lotfy', 'd-arts'], ['t17', 'Mai Wagdy', 'd-arts'], ['t18', 'Khaled Mounir', 'd-tech'],
    ];
    const teachers = teacherList.map(([id, name, deptId]) => ({ id, name, deptId, maxPerDay: 6, unavailable: [] }));
    // Example: one teacher works part-time and is not available on Thursdays.
    teachers.find((t) => t.id === 't15').unavailable = [0, 1, 2, 3, 4, 5, 6].map((p) => 'Thursday|' + p);

    const classes = [];
    [7, 8, 9].forEach((grade) =>
      ['A', 'B', 'C'].forEach((sec) => classes.push({ id: `c${grade}${sec}`, name: `${grade}${sec}`, grade: `Grade ${grade}`, unavailable: [] }))
    );

    const rooms = [
      { id: 'r-lab1', name: 'Lab 1', type: 'Science Lab' },
      { id: 'r-lab2', name: 'Lab 2', type: 'Science Lab' },
      { id: 'r-comp', name: 'Computer Lab', type: 'Computer Lab' },
      { id: 'r-gym', name: 'Gym', type: 'Gym' },
      { id: 'r-art', name: 'Art Studio', type: 'Art Room' },
    ];

    // subject, periods per week, double periods, teacher per grade (7, 8, 9) or per class index
    const plan = [
      ['s-math', 6, 1, (g) => ['t1', 't2', 't3'][g]],
      ['s-ara', 6, 0, (g) => ['t4', 't5', 't6'][g]],
      ['s-eng', 5, 0, (g) => ['t7', 't8', 't9'][g]],
      ['s-sci', 5, 1, (g) => ['t10', 't11', 't12'][g]],
      ['s-soc', 3, 0, (g, i) => (i < 5 ? 't13' : 't14')],
      ['s-rel', 2, 0, (g, i) => (i < 4 ? 't14' : 't15')],
      ['s-pe', 2, 1, () => 't16'],
      ['s-art', 2, 1, () => 't17'],
      ['s-ict', 2, 0, () => 't18'],
    ];
    const lessons = [];
    classes.forEach((c, i) => {
      const g = Math.floor(i / 3);
      plan.forEach(([subjectId, perWeek, doubles, teacherOf]) =>
        lessons.push({ id: `l-${c.id}-${subjectId}`, classId: c.id, subjectId, teacherId: teacherOf(g, i), perWeek, doubles })
      );
    });

    return {
      version: 1,
      settings: {
        schoolName: 'Example Secondary School',
        days: ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday'],
        periods,
      },
      departments,
      subjects,
      teachers,
      classes,
      rooms,
      lessons,
      timetable: null,
    };
  }

  return { sampleSchool };
});
