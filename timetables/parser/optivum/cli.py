import argparse
import asyncio
import os

from timetables.parser.base import File

from timetables.parser.optivum import OptivumParser

parser = argparse.ArgumentParser(description="VULCAN® Optivum® Parser CLI.")
parser.add_argument("url", type=str, help="Timetable URL/path")
parser.add_argument(
    "--register", type=str, help="Class name", required=False, default=""
)

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def a_run(url: str, register_name: str):
    async with OptivumParser() as optivum:
        file = File(path=url)
        ds = await optivum.run_all(file)
        lessons = sorted(ds.lessons, key=lambda x: (x.weekday, x.number))
        if register_name:
            print(
                "\n".join(str(s) for s in lessons if s.register_.name == register_name)
            )
        else:
            for lesson in lessons:
                print(str(lesson))


def main():
    args = parser.parse_args()
    asyncio.run(a_run(args.url, args.register))


if __name__ == "__main__":
    main()
