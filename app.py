import os
import pytz
import time
from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import List, Self, Optional
import requests
from flask import Flask, render_template, send_from_directory, request, abort

app = Flask(__name__, template_folder="templates", static_folder="static")
BOARDS = {2022: 1505617}
SESSION_COOKIE = {"session": os.getenv("SESSION_COOKIE")}
CACHE_FOLDER = "cache"
TIMEZONE = pytz.timezone("EST")
CURRENT_TIME = datetime.now(tz=TIMEZONE)


@dataclass(order=True)
class Result:
    day: int
    silver_ts: Optional[int] = None
    gold_ts: Optional[int] = None

    @property
    def delta(self) -> int:
        if self.gold_ts:
            return self.gold_ts - self.silver_ts

    @property
    def str_time(self) -> str:
        if not self.gold_ts:
            return ""
        delta = self.gold_ts - self.silver_ts
        days, hours, minutes, seconds, _ = split_timestamp(delta)
        return f"{days}:{hours:02}:{minutes:02}:{seconds:02}"


@dataclass(order=False)
class Member:
    id: int
    results: List[Result] = field(default_factory=list)
    position: int = 0
    name: str = None

    @property
    def stars(self) -> int:
        stars = 0
        for result in self.results:
            stars += 1 if result.silver_ts else 0
            stars += 1 if result.gold_ts else 0
        return stars

    def __eq__(self, other: Self) -> bool:
        has_same_number_of_stars = self.stars == other.stars
        has_same_number_of_gold_stars = self.gold_stars == other.gold_stars
        has_same_sum_of_gold_stars = self.sum_gold_stars == other.sum_gold_stars
        if has_same_number_of_stars and has_same_number_of_gold_stars and has_same_sum_of_gold_stars:
            return self.total_time == other.total_time
        return False

    def __lt__(self, other: Self) -> bool:
        if self.stars == other.stars:
            if self.gold_stars == other.gold_stars:
                if self.sum_gold_stars == other.sum_gold_stars:
                    return self.total_time > other.total_time
                return self.sum_gold_stars < other.sum_gold_stars
            return self.gold_stars < other.gold_stars
        return self.stars < other.stars

    @property
    def total_time(self) -> int:
        return sum([result.delta for result in self.results if result.gold_ts])

    @property
    def participating_days(self) -> int:
        return sum([1 for result in self.results if result.silver_ts])

    @property
    def average_time(self) -> float:
        if self.stars:
            return self.total_time / self.participating_days
        return 0.0

    @property
    def gold_stars(self) -> int:
        return sum([1 for result in self.results if result.gold_ts])

    @property
    def sum_gold_stars(self) -> int:
        return sum([result.day for result in self.results if result.gold_ts])

    @property
    def str_total_time(self) -> str:
        days, hours, minutes, seconds, _ = split_timestamp(self.total_time)
        return f"{days}:{hours:02}:{minutes:02}:{seconds:02}"

    @property
    def str_average_time(self) -> str:
        days, hours, minutes, seconds, milliseconds = split_timestamp(self.average_time)
        return f"{days}:{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03}"


def contest_end(year: int) -> datetime:
    return datetime(
        year=year,
        month=12,
        day=31,
        hour=23,
        minute=59,
        second=59,
        microsecond=999999,
        tzinfo=TIMEZONE,
    )


def is_contest_over(year: int, current_time: Optional[datetime] = None) -> bool:
    current_time = current_time or CURRENT_TIME
    print(current_time.astimezone(tz=TIMEZONE))
    print(contest_end(year).astimezone(tz=TIMEZONE))
    return current_time > contest_end(year)


def split_timestamp(timestamp: int | float) -> tuple:
    days = int(timestamp // 86_400)
    hours = int((timestamp // 3600) % 24)
    minutes = int((timestamp // 60) % 60)
    seconds = int(timestamp % 60)
    milliseconds = int(round((timestamp - (timestamp // 1)) * 1000))
    print(f"{timestamp=} {timestamp // 1=} {timestamp - timestamp // 1}")
    return days, hours, minutes, seconds, milliseconds


def determine_positions(members: List[Member]) -> None:
    for i, member in enumerate(members):
        if i == 0:
            member.position = 1
            continue
        if member == members[i - 1]:
            member.position = members[i - 1].position
        else:
            member.position = i + 1


def populate_members(data: dict, year: int) -> List[Member]:
    members = []
    for member in data["members"].values():

        if not member["stars"]:
            continue
        results = [Result(day=i, silver_ts=None, gold_ts=None) for i in range(1, 26)]
        for day, result in member["completion_day_level"].items():
            for star in [("silver", "1"), ("gold", "2")]:
                if star[1] not in result:
                    continue
                timestamp = result[star[1]].get("get_star_ts", None)
                if timestamp and timestamp <= contest_end(year).timestamp():
                    setattr(results[int(day) - 1], f"{star[0]}_ts", timestamp)

        members.append(Member(id=member["id"], name=member["name"], results=sorted(results)))

    members.sort(reverse=True)

    if members:
        determine_positions(members)

    return members


def use_cached_json(
    year: int,
    cache_folder: str = CACHE_FOLDER,
    timestamp: int = None,
    forced: bool = False,
) -> Optional[dict]:
    timestamp = time.time() if timestamp is None else timestamp
    if not os.path.exists(f"{cache_folder}/{year}.json"):
        return
    try:
        with open(f"{cache_folder}/{year}.json", "r") as f:
            data = json.loads(f.read())
            if forced or timestamp - data["timestamp"] < 900:
                return data
    except json.JSONDecodeError:
        pass
    return


def get_session_cookie() -> dict:
    with open("etc/config.json") as f:
        config_file = f.read()
        config = json.loads(config_file)
        return config["session_cookie"]


def fetch_json(year: int) -> dict:
    cached_data = use_cached_json(year)
    if cached_data:
        return cached_data

    try:
        url = f"https://adventofcode.com/{year}/leaderboard/private/view/{BOARDS[year]}.json"
        response = requests.get(url=url, cookies=SESSION_COOKIE)
        response.raise_for_status()

        if response.headers["Content-Type"] != "application/json":
            raise Exception("Unable to fetch standings from advent-of-code")

        data = response.json()
        data["timestamp"] = time.time()

        with open(f"{CACHE_FOLDER}/{year}.json", "w") as f:
            json.dump(data, f, indent=4, sort_keys=True)

        return data

    except Exception:
        return use_cached_json(year, forced=True)


@app.route("/")
def current_leaderboard() -> str:
    return leaderboard(sorted(list(BOARDS.keys()))[-1])


@app.route("/<int:year>")
def leaderboard(year: int) -> str:
    if year not in BOARDS:
        abort(404)
    data = fetch_json(year)
    members = populate_members(data, year)
    return render_template(
        "index.html",
        members=members,
        days=[f"{i:02}" for i in range(1, 26)],
        current_year=year,
        current_day=CURRENT_TIME.day if not is_contest_over(year) else 25,
        timestamp=datetime.fromtimestamp(data["timestamp"], tz=TIMEZONE).strftime("%Y-%m-%d %H:%M:%S"),
    )


@app.route("/rules")
def rules() -> str:
    return render_template("rules.html", current_year=sorted(list(BOARDS.keys()))[-1])


@app.route("/robots.txt")
def robots():
    return send_from_directory(app.static_folder, request.path[1:])
