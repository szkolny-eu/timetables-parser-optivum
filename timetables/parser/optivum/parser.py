import re
from datetime import date, time
from typing import List

from bs4 import BeautifulSoup
from bs4.element import Tag
from timetables.parser.base import File, Parser
from timetables.schemas import Classroom, Lesson, Register, WeekDay

from .utils import build_id, date_regex, fill_param, find_team, timespan_regex


class OptivumParser(Parser):
    async def _parse_file(self, file: File) -> None:
        html = await file.read(self.session)
        soup = BeautifulSoup(html, features="lxml")
        # supports modes:
        # - "lista wypunktowana z lewej strony"
        # - "drzewko z lewej strony"
        # - "listy rozwijane na dole"
        frame = soup.select("frame[name=list]")
        if frame:
            frame = frame[0]
            path = frame["src"]
            self.enqueue(file.sibling(path))
            return
        # supports modes:
        # - "lista wypunktowana z lewej strony"
        # - "drzewko z lewej strony"
        # - "wszystkie odnośniki na stronie głównej"
        # - "nawigacja za pomocą menu"
        tables = soup.select("a[target=plan], td[valign=top] .tabela td > a")
        if tables:
            for table in tables:
                target = file.sibling(table["href"])
                label = table.text
                self.enqueue(target)
                item = fill_param(self.ds, params={}, name=label, file=target)
                if isinstance(item, Classroom):
                    item.__name_full__ = label
            return
        # supports modes:
        # - "listy rozwijane na dole"
        selects = soup.select("select")
        if selects:
            for select in selects:
                select: Tag
                item_type = select["name"][0]
                options = select.select("option[value]")
                for option in options:
                    option: Tag
                    option_id = option["value"]
                    target = file.sibling(f"plany/{item_type}{option_id}.html")
                    label = option.text
                    self.enqueue(target)
                    item = fill_param(self.ds, params={}, name=label, file=target)
                    if isinstance(item, Classroom):
                        item.__name_full__ = label
            return
        # supports modes:
        # - "nawigacja za pomocą menu"
        # !! note: this has to be after the "tables" condition above;
        # the sub-menu pages contain the same menu elements, along with the searched
        # timetable links, which will stop the script above, instead of recursing indefinitely
        menu = soup.select(".menu a")
        if menu:
            for link in menu:
                target = file.sibling(link["href"])
                self.enqueue(target)
            return
        logo = soup.find(name="a", text="Plan lekcji Optivum")
        if logo:
            info = logo.parent.text
            match = re.search(date_regex, info)
            if match:
                self.ds.date_generated = date.fromisoformat(match.group(0))
            await self._parse_table(file, soup)
            return
        print("Unrecognized document:")
        print(soup)

    async def cleanup(self) -> None:
        for teacher in self.ds.teachers:
            if teacher.__name_full__:
                teacher.name = teacher.__name_full__
                teacher.__name_full__ = None
        for classroom in self.ds.classrooms:
            if classroom.__name_full__:
                # classroom name gets replaced with a short code, which is always prepending the full name
                parts = classroom.__name_full__.partition(classroom.name)
                # try not to cut the classroom number, i.e. "021 informatyczna"
                if not classroom.name[0].isnumeric() and parts[2]:
                    classroom.name = parts[2].strip()
                classroom.__name_full__ = None

    async def _parse_table(self, file: File, soup: BeautifulSoup) -> None:
        table = soup.select_one("table.tabela")
        headers: List[Tag] = table.select("tr > th")
        if len(headers) < 7:
            raise ValueError("Not enough table headers found")
        headers = [th.text for th in headers[2:]]

        params = {}
        # specifying the title for a classroom timetable (which has
        # a non-splittable full name) would produce unpredictable results, where
        # some classrooms have the short name in the result dataset
        table_title = soup.select_one("span.tytulnapis").text
        # (table_type, table_id) = split_id(str(file.path))
        # if table_type == "s" and self.ds.has_classroom(internal_id=table_id):  # classroom
        #     table_title = None
        fill_param(self.ds, params, name=table_title, file=file)

        rows = table.select("tr")
        if len(rows) < 2:
            raise ValueError("No lesson rows found")
        rows = rows[1:]
        for row in rows:
            row: Tag

            number = row.select_one("td.nr")
            if number:
                number = number.text.replace(".", "")
                number = int(number) if number.isnumeric() else None
            params["number"] = number

            timespan = row.select_one("td.g")
            if not timespan:
                raise ValueError("No timespan in the row")
            match = re.search(timespan_regex, timespan.text)
            if not match:
                raise ValueError("Invalid timespan in the row")
            timespan = match.group(0).split("-")
            if len(timespan) != 2:
                raise ValueError("Timespan has an invalid form")
            time_start = timespan[0].strip().split(":")
            time_start = time(hour=int(time_start[0]), minute=int(time_start[1]))
            time_end = timespan[1].strip().split(":")
            time_end = time(hour=int(time_end[0]), minute=int(time_end[1]))
            params["time_start"] = time_start
            params["time_end"] = time_end

            cols = row.select("td.l")
            if len(cols) != len(headers):
                raise ValueError(
                    f"Column count does not equal the header count: {len(cols)} vs {len(headers)}"
                )
            for weekday, col in enumerate(cols):
                col: Tag
                weekday = WeekDay(weekday)
                params["weekday"] = weekday
                await self._parse_lesson(col, params=dict(params), source=file)

    async def _parse_lesson(
        self,
        cell: Tag,
        params: dict,
        source: File,
        small_lesson: bool = False,
        parse_lines: bool = True,
    ):
        # select small lessons from cells with multiple lessons (only for class timetables, I guess)
        teams = cell.select("span[style]")
        for team in teams:
            team: Tag
            team = team.extract()
            # small lessons may have the team name in the span.p element (probably a bug...)
            await self._parse_lesson(
                cell=team, params=dict(params), source=source, small_lesson=True
            )

        # process cells with multiple lines (not for small lessons)
        br = cell.find(name="br") if parse_lines and not small_lesson else None
        while br:
            row = br.find_previous_siblings()
            # the <br> may be the first element, as small lessons are extracted before
            if row:
                # parse the first available row
                await self._parse_lesson(
                    cell=cell, params=dict(params), source=source, parse_lines=False
                )
                # destroy the row, not to parse it again
                for el in row:
                    el.decompose()
            # note: at this point, all small lessons are removed, also it shouldn't be possible
            # for the parser to select other lesson's teacher, as large split lessons do not have teachers
            br.decompose()
            br = cell.find(name="br")

        subject = cell.select_one(".p")
        if not subject:
            # probably an empty cell
            return

        if small_lesson:
            if "-" in subject.text:
                # extract the team name after '-' from the subject name, only for small lessons
                params["subject"] = self.ds.get_subject(
                    name=subject.text.rpartition("-")[0]
                )
            else:
                # no team suffix found, disable further lookup
                small_lesson = False
        if not small_lesson:
            # large lessons do not have team names in the span.p element
            params["subject"] = self.ds.get_subject(name=subject.text)

        teacher = cell.select_one(".n")
        if teacher:
            name_short = teacher.text
            if teacher.name == "a":
                file = source.sibling(teacher["href"])
                fill_param(self.ds, params, name=name_short, file=file)
            else:
                params["teacher"] = self.ds.get_teacher(name=name_short)

        classroom = cell.select_one(".s")
        if classroom:
            name_short = classroom.text
            if classroom.name == "a":
                file = source.sibling(classroom["href"])
                fill_param(self.ds, params, name=name_short, file=file)
            else:
                params["classroom"] = self.ds.get_classroom(name=name_short)

        if "teacher" in params:
            params["teachers"] = [params["teacher"]]
        else:
            params["teachers"] = []
        params.pop("teacher", None)

        # apparently, a single teacher can have a lesson with multiple classes, at once
        registers = cell.select(".o")
        for register in registers:
            register: Tag
            name_short = register.text

            if register.name == "a":
                file = source.sibling(register["href"])
                fill_param(self.ds, params, name=name_short, file=file)
            else:
                params["register_"] = self.ds.get_register(
                    type=Register.Type.CLASS, name=name_short
                )

            params["team"] = find_team(
                self.ds, params["register_"], element=register, in_name=False
            )
            self._add_lesson(**params)
        if not registers:
            params["team"] = find_team(
                self.ds, params["register_"], element=subject, in_name=small_lesson
            )
            if not params["team"]:
                parts = cell.select(".p")
                for part in parts:
                    # multi-class lesson
                    if part.text.startswith("#"):
                        name = params["register_"].name + " " + part.text
                        params["team"] = self.ds.get_team(
                            params["register_"], name=name
                        )
                        break
            self._add_lesson(**params)

    def _add_lesson(self, **params):
        internal_id = build_id(**params)
        lesson = Lesson(internal_id=internal_id, **params)
        # apparently, constructing a model makes a copy of all its properties
        for k, v in params.items():
            lesson.__setattr__(k, v)
        lesson2 = next(
            (
                item
                for item in self.ds.lessons
                if item.internal_id == lesson.internal_id
            ),
            None,
        )
        if lesson2:
            if lesson.teachers and not lesson2.teachers:
                lesson2.teachers = lesson.teachers
            if lesson.classroom and not lesson2.classroom:
                lesson2.classroom = lesson.classroom
        else:
            self.ds.lessons.append(lesson)
