import re
from datetime import time
from os.path import basename, splitext
from typing import Optional, Tuple

from bs4 import NavigableString, Tag
from timetables.base import Nameable
from timetables.parser.base import Dataset, File
from timetables.schemas import Register, Subject, Team, WeekDay

date_regex = r"(19[0-9]{2}|2[0-9]{3})-0?([1-9]|1[012])-0?([123]0|[12]?[1-9]|31)"
timespan_regex = r"0?(1?[0-9]|2[0-3]):0?([0-6][0-9]|[0-9])-\s?0?(1?[0-9]|2[0-3]):0?([0-6][0-9]|[0-9])"
teacher_regex = r"(.\..+?) \((.+?)\)"


def split_id(path: str) -> Tuple[str, int]:
    file_name = basename(path)
    file_id = splitext(file_name)[0]
    return file_id[0], int(file_id[1:])


def build_id(
    weekday: WeekDay,
    time_start: time,
    subject: Subject,
    register_: Register,
    team: Team,
    **kwargs,
):
    time_value = time_start.hour * 60 + time_start.minute
    team_id = team.internal_id if team else register_.internal_id
    data_value = team_id * 100 + subject.internal_id
    return (
        (weekday.value + 1) * 100000000000
        + time_value * 10000000
        + (data_value % 10000000)
    )


def fill_param(ds: Dataset, params: dict, name: Optional[str], file: File) -> Nameable:
    (param_type, param_id) = split_id(str(file.path))
    if param_type == "o":
        param = ds.get_register(
            type=Register.Type.CLASS, name=name, internal_id=param_id, url=file.path
        )
        params["register_"] = param
    elif param_type == "n":
        param = ds.get_teacher(name=name, internal_id=param_id, url=file.path)
        match = re.match(teacher_regex, name or "")
        if match:
            param.name = match.group(2)
            param.__name_full__ = match.group(1)
        params["teacher"] = param
    elif param_type == "s":
        param = ds.get_classroom(name=name, internal_id=param_id, url=file.path)
        params["classroom"] = param
    else:
        raise ValueError(
            f"Unknown item type for ID {param_id}: {param_type} (name={name})"
        )
    return param


def find_team(
    ds: Dataset, register: Register, element: Tag, in_name: bool
) -> Optional[Team]:
    if not register or not element:
        return None
    team_suffix = element.next_sibling
    if isinstance(team_suffix, NavigableString):
        team_suffix = team_suffix.strip(" ,")
    if in_name and "-" in element.text:
        team_suffix = "-" + element.text.rpartition("-")[2]
    if isinstance(team_suffix, str) and team_suffix:
        team_name = register.name + team_suffix
        return ds.get_team(register, team_name)
    return None
