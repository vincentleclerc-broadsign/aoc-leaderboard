
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from json import JSONDecodeError
from typing import List, Self, Optional
import requests
from flask import Flask, render_template, send_from_directory, request

app = Flask(__name__, template_folder="templates", static_folder="static")
BOARDS = {2020: 642101, 2021: 642101, 2022: 1505617}
CACHE_FOLDER = "cache"
logger = logging.getLogger(__name__)


@dataclass(order=True)
class Result:
    day: int
    silver_ts: Optional[int]
    gold_ts: Optional[int]

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
    stars: int
    results: List[Result] = field(default_factory=list)
    position: int = 0
    name: str = None

    def __eq__(self, other: Self) -> bool:
        has_same_number_of_stars = self.stars == other.stars
        has_same_number_of_gold_stars = self.number_of_gold_stars == other.number_of_gold_stars
        has_same_sum_of_gold_stars = self.sum_gold_stars == other.sum_gold_stars
        if has_same_number_of_stars and has_same_number_of_gold_stars and has_same_sum_of_gold_stars:
            return self.total_time == other.total_time
        return False

    def __lt__(self, other: Self) -> bool:
        if self.stars == other.stars:
            if self.number_of_gold_stars == other.number_of_gold_stars:
                if self.sum_gold_stars == other.sum_gold_stars:
                    return self.total_time > other.total_time
                return self.sum_gold_stars < other.sum_gold_stars
            return self.number_of_gold_stars < other.number_of_gold_stars
        return self.stars < other.stars

    @property
    def total_time(self) -> int:
        return sum([result.delta for result in self.results if result.gold_ts])

    def get_number_of_participating_days(self) -> int:
        return len([1 for result in self.results if result.silver_ts])

    @property
    def average_time(self) -> float:
        if self.stars:
            return self.total_time / self.get_number_of_participating_days()
        return 0.0

    @property
    def number_of_gold_stars(self) -> int:
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


def split_timestamp(timestamp: int | float) -> tuple:
    days = int(timestamp // 86_400)
    hours = int((timestamp // 3600) % 24)
    minutes = int((timestamp // 60) % 60)
    seconds = int(timestamp % 60)
    milliseconds = int((timestamp - timestamp // 1) * 1000)
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


def populate_members(data: dict) -> List[Member]:
    members = []
    for member in data["members"].values():

        if not member["stars"]:
            continue
        results = [Result(day=i, silver_ts=None, gold_ts=None) for i in range(1, 26)]
        for day, result in member["completion_day_level"].items():

            results[int(day) - 1].silver_ts = result["1"].get("get_star_ts", None) if "1" in result else None
            results[int(day) - 1].gold_ts = result["2"].get("get_star_ts", None) if "2" in result else None

        members.append(Member(
            id=member["id"],
            name=member["name"] or f"User #{member['id']}",
            stars=member["stars"],
            results=sorted(results)
        ))

    members.sort(reverse=True)

    if members:
        determine_positions(members)

    return members


def use_cached_json(year: int) -> Optional[dict]:
    if not os.path.exists(f"{CACHE_FOLDER}/{year}.json"):
        return
    try:
        with open(f"{CACHE_FOLDER}/{year}.json", "r") as f:
            data = json.loads(f.read())
            if time.time() - data["timestamp"] < 900:
                return data
    except JSONDecodeError:
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
        logger.info("Using cached data.")
        return cached_data

    session_cookie = get_session_cookie()

    logging.info("Retrieving data for adventofcode.com")
    url = f"https://adventofcode.com/{year}/leaderboard/private/view/{BOARDS[year]}.json"
    response = requests.get(url=url, cookies=session_cookie)
    response.raise_for_status()

    if response.headers["Content-Type"] != "application/json":
        raise Exception("Unable to fetch standings from advent-of-code")

    data = response.json()
    data["timestamp"] = time.time()

    with open(f"{CACHE_FOLDER}/{year}.json", "w") as f:
        json.dump(data, f, indent=4, sort_keys=True)

    return data


@app.route('/')
def current_leaderboard() -> str:
    return leaderboard(sorted(list(BOARDS.keys()))[-1])


@app.route('/<int:year>')
def leaderboard(year: int) -> str:
    logger.info(f"Deserving leaderboard for {year}")
    data = fetch_json(year)
    members = populate_members(data)
    return render_template(
        'index.html',
        members=members,
        days=[f"{i:02}" for i in range(1, 26)],
        current_year=year,
        years=BOARDS.keys(),
        timestamp=datetime.fromtimestamp(data["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
    )


@app.route("/robots.txt")
def robots():
    return send_from_directory(app.static_folder, request.path[1:])
