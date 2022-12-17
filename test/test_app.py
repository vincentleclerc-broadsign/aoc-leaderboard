import json
from datetime import datetime
from types import NoneType
from typing import Optional, List, Tuple

import pytest
import pytz

from app import (
    Result,
    Member,
    is_contest_over,
    contest_end,
    split_timestamp,
    determine_positions,
    populate_members,
    use_cached_json,
)


class TestResult:
    @pytest.mark.parametrize("silver_ts, gold_ts, delta", [(2, 5, 3), (2, None, None), (None, None, None)])
    def test_delta(self, silver_ts: Optional[int], gold_ts: Optional[int], delta: Optional[int]):
        assert Result(day=1, silver_ts=silver_ts, gold_ts=gold_ts).delta == delta

    @pytest.mark.parametrize(
        "silver_ts, gold_ts, str_time",
        [
            (2, 5, "0:00:00:03"),
            (2, 12, "0:00:00:10"),
            (2, 65, "0:00:01:03"),
            (2, 665, "0:00:11:03"),
            (2, 3665, "0:01:01:03"),
            (2, 36065, "0:10:01:03"),
            (2, 86405, "1:00:00:03"),
            (2, None, ""),
            (None, None, ""),
        ],
    )
    def test_str_time(self, silver_ts: Optional[int], gold_ts: Optional[int], str_time: str):
        assert Result(day=1, silver_ts=silver_ts, gold_ts=gold_ts).str_time == str_time


class TestMember:
    @pytest.mark.parametrize(
        "results, stars",
        [
            ([], 0),
            ([Result(1, 2, None)], 1),
            ([Result(1, 2, 3)], 2),
            ([Result(1, 2, None), Result(2, 4, None)], 2),
            ([Result(1, 2, 3), Result(2, 4, None)], 3),
            ([Result(1, 2, 3), Result(10, 12, None)], 3),
        ],
    )
    def test_stars(self, results: List[Result], stars: int):
        assert Member(id=1, name="bob", results=results).stars == stars

    @pytest.mark.parametrize(
        "first_results, second_results, is_equal",
        [
            ([Result(1, 2, None)], [], False),
            ([Result(1, 2, None)], [Result(1, 2, 3)], False),
            ([Result(1, 2, None), Result(2, 4, None)], [Result(1, 2, 3)], False),
            ([Result(1, 2, 3)], [Result(2, 4, 5)], False),
            ([Result(1, 2, 3)], [Result(1, 2, 4)], False),
            ([Result(1, 2, 3)], [Result(1, 2, 3)], True),
        ],
    )
    def test_eq(self, first_results: List[Result], second_results: List[Result], is_equal: bool):
        assert (
            Member(id=1, name="bob", results=first_results).__eq__(Member(id=2, name="alice", results=second_results))
            == is_equal
        )

    @pytest.mark.parametrize(
        "first_results, second_results, is_less",
        [
            ([Result(1, 2, None)], [], False),
            ([], [Result(1, 2, None)], True),
            ([Result(1, 2, None)], [Result(1, 2, 3)], True),
            ([Result(1, 2, 3)], [Result(1, 2, None)], False),
            ([Result(1, 2, None), Result(2, 4, None)], [Result(1, 2, 3)], True),
            ([Result(1, 2, 3)], [Result(1, 2, None), Result(2, 4, None)], False),
            ([Result(1, 2, 3)], [Result(2, 4, 5)], True),
            ([Result(2, 4, 5)], [Result(1, 2, 3)], False),
            ([Result(1, 2, 3)], [Result(1, 2, 4)], False),
            ([Result(1, 2, 4)], [Result(1, 2, 3)], True),
            ([Result(1, 2, 3)], [Result(1, 2, 3)], False),
        ],
    )
    def test_lt(self, first_results: List[Result], second_results: List[Result], is_less: bool):
        assert (
            Member(id=1, name="bob", results=first_results).__lt__(Member(id=2, name="alice", results=second_results))
            == is_less
        )

    @pytest.mark.parametrize(
        "results, total_time",
        [
            ([], 0),
            ([Result(1, 2, None)], 0),
            ([Result(1, 2, 3)], 1),
            ([Result(1, 2, None), Result(2, 4, None)], 0),
            ([Result(1, 2, None), Result(2, 4, 5)], 1),
            ([Result(1, 2, 3), Result(2, 4, 15)], 12),
        ],
    )
    def test_total_time(self, results: List[Result], total_time: int):
        assert Member(id=1, name="bob", results=results).total_time == total_time

    @pytest.mark.parametrize(
        "results, average_time",
        [
            ([], 0),
            ([Result(1, 2, None)], 0),
            ([Result(1, 2, 3)], 1),
            ([Result(1, 2, None), Result(2, 4, None)], 0),
            ([Result(1, 2, None), Result(2, 4, 5)], 0.5),
            ([Result(1, 2, 3), Result(2, 4, 15)], 6),
        ],
    )
    def test_average_time(self, results: List[Result], average_time: int):
        assert Member(id=1, name="bob", results=results).average_time == average_time

    @pytest.mark.parametrize(
        "results, participating_days",
        [
            ([], 0),
            ([Result(1, 2, None)], 1),
            ([Result(1, 2, 3)], 1),
            ([Result(1, 2, None), Result(2, 4, None)], 2),
            ([Result(1, 2, 3), Result(3, 4, 15)], 2),
        ],
    )
    def test_participating_days(self, results: List[Result], participating_days: int):
        assert Member(id=1, name="bob", results=results).participating_days == participating_days

    @pytest.mark.parametrize(
        "results, gold_stars",
        [
            ([], 0),
            ([Result(1, 2, None)], 0),
            ([Result(1, 2, 3)], 1),
            ([Result(1, 2, None), Result(2, 4, None)], 0),
            ([Result(1, 2, None), Result(2, 4, 5)], 1),
            ([Result(1, 2, 3), Result(3, 4, 15)], 2),
        ],
    )
    def test_gold_stars(self, results: List[Result], gold_stars: int):
        assert Member(id=1, name="bob", results=results).gold_stars == gold_stars

    @pytest.mark.parametrize(
        "results, sum_gold_stars",
        [
            ([], 0),
            ([Result(1, 2, None)], 0),
            ([Result(1, 2, 3)], 1),
            ([Result(1, 2, None), Result(2, 4, None)], 0),
            ([Result(1, 2, None), Result(2, 4, 5)], 2),
            ([Result(1, 2, 3), Result(3, 4, 15)], 4),
        ],
    )
    def test_sum_gold_stars(self, results: List[Result], sum_gold_stars: int):
        assert Member(id=1, name="bob", results=results).sum_gold_stars == sum_gold_stars

    @pytest.mark.parametrize(
        "results, str_total_time",
        [
            ([], "0:00:00:00"),
            ([Result(1, 2, None)], "0:00:00:00"),
            ([Result(1, 2, 3)], "0:00:00:01"),
            ([Result(1, 2, None), Result(2, 4, None)], "0:00:00:00"),
            ([Result(1, 2, None), Result(2, 4, 5)], "0:00:00:01"),
            ([Result(1, 2, 3), Result(3, 4, 15)], "0:00:00:12"),
        ],
    )
    def test_str_total_time(self, results: List[Result], str_total_time: int):
        assert Member(id=1, name="bob", results=results).str_total_time == str_total_time

    @pytest.mark.parametrize(
        "results, str_average_time",
        [
            ([], "0:00:00:00.000"),
            ([Result(1, 2, None)], "0:00:00:00.000"),
            ([Result(1, 2, 3)], "0:00:00:01.000"),
            ([Result(1, 2, None), Result(2, 4, None)], "0:00:00:00.000"),
            ([Result(1, 2, None), Result(2, 4, 5)], "0:00:00:00.500"),
            ([Result(1, 2, 3), Result(3, 4, 15)], "0:00:00:06.000"),
            ([Result(1, 2, 3), Result(3, 4, 15), Result(4, 16, 17)], "0:00:00:04.333"),
            ([Result(1, 2, 3), Result(3, 4, 15), Result(4, 16, 18)], "0:00:00:04.667"),
        ],
    )
    def test_str_average_time(self, results: List[Result], str_average_time: int):
        assert Member(id=1, name="bob", results=results).str_average_time == str_average_time


@pytest.mark.parametrize(
    "year, end_datetime",
    [
        (2022, datetime(2022, 12, 31, 23, 59, 59, 999999, tzinfo=pytz.timezone("EST"))),
        (2022, datetime(2023, 1, 1, 4, 59, 59, 999999, tzinfo=pytz.utc)),
    ],
)
def test_contest_end(year: int, end_datetime: datetime):
    assert contest_end(year) == end_datetime.astimezone(tz=pytz.timezone("EST"))


@pytest.mark.parametrize(
    "year, current_time, is_over",
    [
        (
            2022,
            datetime(2022, 12, 31, 23, 59, 59, 0, tzinfo=pytz.timezone("EST")),
            False,
        ),
        (2022, datetime(2023, 1, 1, 0, 0, 0, 0, tzinfo=pytz.timezone("EST")), True),
        (2022, datetime(2023, 1, 1, 4, 59, 59, 0, tzinfo=pytz.timezone("UTC")), False),
        (2022, datetime(2023, 1, 1, 5, 0, 0, 0, tzinfo=pytz.timezone("UTC")), True),
    ],
)
def test_is_contest_over(year: int, current_time: datetime, is_over: bool):
    assert is_contest_over(year, current_time) == is_over


def test_split_timestamp():
    assert split_timestamp(timestamp=99_999.999) == (1, 3, 46, 39, 999)


@pytest.mark.parametrize(
    "results, positions",
    [
        ([[]], (1,)),
        ([[Result(1, None, None)]], (1,)),
        ([[Result(1, None, None)], [Result(1, 1, None)]], (2, 1)),
        ([[Result(1, 1, 2)], [Result(1, 1, None)]], (1, 2)),
        ([[Result(1, 1, 2)], [Result(1, 1, None), Result(2, 3, None)]], (1, 2)),
        ([[Result(1, 1, 2)], [Result(4, 1, 2)]], (2, 1)),
        ([[Result(1, 1, 2)], [Result(1, 1, 2)], []], (1, 1, 3)),
        (
            [
                [Result(1, 1, 2)],
                [Result(1, 1, 4)],
                [Result(1, 1, 4)],
                [Result(1, 1, 5)],
            ],
            (1, 2, 2, 4),
        ),
        (
            [
                [Result(1, 1, 2)],
                [Result(1, 1, 4)],
                [Result(1, 1, 4)],
                [Result(1, 1, 4)],
                [Result(1, 1, 5)],
            ],
            (1, 2, 2, 2, 5),
        ),
    ],
)
def test_determine_positions(results: List[List[Result]], positions: Tuple[int, ...]):
    members: List[Member] = []
    for i, result in enumerate(results):
        members.append(Member(id=i, name="", results=result))
    determine_positions(members)
    assert (member.position for member in members)


def test_populate_members():
    """Test the following scenarios that can happen in the returned json file.

    * Day 1 has a silver star obtained in time and a gold star obtained after the contest end.
    * Day 2 has both stars obtained after the contest end.
    * Day 3 only has a silver star, and it has been obtained after the contest end.
    * Day 4 and 5 have been swapped in the json file. The indexes don't appear in order.
        * Day 4 has both stars obtained in time.
        * Day 5 only has the silver star.
    """
    with open("2022.json") as f:
        data = json.load(f)
    members = populate_members(data, year=2022)
    assert len(members) == 1
    assert members[0].id == 1337
    assert members[0].name == "bob"
    assert members[0].position == 1
    assert members[0].results[:5] == [
        Result(1, 4, None),
        Result(2, None, None),
        Result(3, None, None),
        Result(4, 6, 7),
        Result(5, 5, None),
    ]


@pytest.mark.parametrize(
    "year, timestamp, forced, expected_type",
    [
        (1, None, False, NoneType),
        (2022, None, False, NoneType),
        (2022, None, True, dict),
        (2022, 124, False, dict),
    ],
)
def test_use_cached_json(year: str, timestamp: int, forced: bool, expected_type: type):
    assert type(use_cached_json(year, cache_folder=".", timestamp=timestamp, forced=forced)) == expected_type
