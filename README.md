# VULCAN® Optivum® timetable parser library

This library provides access to public timetables generated using the "Plan lekcji Optivum" software.
The resulting dataset is compatible with and based on [timetables-lib](https://github.com/szkolny-eu/timetables-lib).

## Usage examples

```python
async with OptivumParser() as parser:
    # specify an entire timetable
    file = File(path="https://www.school.pl/plan/index.html")
    # specify a single timetable (class, teacher, classroom)
    file = File(path="https://www.school.pl/plan/plany/o3.html")
    # specify a local timetable
    file = File(path="C:/html/index.html")
    
    # enqueue and parse all (you can specify more files)
    ds = await parser.run_all(file)
    # enqueue, then parse
    parser.enqueue(file)
    ds = await parser.run_all()

    # sort lessons, because why not
    lessons = sorted(ds.lessons, key=lambda x: (x.weekday, x.number))
    # print lessons for a specific class
    print("\n".join(str(s) for s in lessons if s.register_.name == "1A"))
```

## Command-line scripts

Available after installing the package (if scripts directory is in your `PATH`, or you're using a virtualenv). 
```shell
$ optivum https://www.school.pl/plan/index.html --register 1A
Parsing 'https://www.school.pl/plan/index.html'
Lesson(...)
Lesson(...)
...
```

