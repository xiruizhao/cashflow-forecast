from utils import (
    generate_rrulestr,
    validate_rrule,
    split_accounts,
    get_stock_price,
    get_cashflow_series_upload,
    generate_forecast,
)
from typing import NamedTuple
import pytest
from unittest.mock import Mock
from datetime import date, datetime
import curl_cffi

"""
    validator: InputValidator,
    freq: str,
    interval: int | float | None,
    byweekday_weekly: tuple[str],
    setpos_monthly: bool,
    bysetpos_monthly: str,
    byweekday_monthly: str,
    bymonthday_monthly: str,
    setpos_yearly: bool,
    bysetpos_yearly: str,
    byweekday_yearly: str,
    bymonth_bysetpos_yearly: str,
    bymonth_yearly: str,
    bymonthday_yearly: str,
    end: str,
    until: date | None,
    count: int | float | None
"""


class _TestCase(NamedTuple):
    kwargs: dict = {}
    ret: str = ""


def test_generate_rrulestr():
    validator = Mock()
    validator.is_valid.return_value = True
    test_cases = [
        _TestCase(
            {
                "validator": validator,
                "freq": "NEVER",
                "interval": 1,
            },
            "FREQ=DAILY;COUNT=1",
        ),
        _TestCase(
            {
                "validator": validator,
                "freq": "WEEKLY",
                "interval": 2,
                "byweekday_weekly": ("FR",),
            },
            "FREQ=WEEKLY;INTERVAL=2;BYDAY=FR",
        ),
        _TestCase(
            {
                "validator": validator,
                "freq": "MONTHLY",
                "interval": 3,
                "bymonthday_monthly": "20",
                "end": "UNTIL",
                "until": date(2025, 6, 24),
            },
            "FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=20;UNTIL=20250624T0000Z",
        ),
    ]
    for testcase in test_cases:
        assert generate_rrulestr(**testcase.kwargs) == testcase.ret


def test_validate_rrule():
    assert validate_rrule("") is not None
    assert validate_rrule(" ") is not None
    assert validate_rrule(";;") is not None


def test_split_accounts():
    assert split_accounts("") == {}
    assert split_accounts("a6+-++7.$") == {}
    assert split_accounts("checking+5 checking+5") == {}
    assert split_accounts("checking+5\nhecking+5") != {}


def test_get_stock_price():
    return
    with pytest.raises(curl_cffi.requests.exceptions.HTTPError):
        get_stock_price("$$$")


def test_get_cashflow_series_upload():
    # empty file
    assert get_cashflow_series_upload("", isfilepath=False) is None
    assert get_cashflow_series_upload("app.py") is None  # wrong format

    valid = get_cashflow_series_upload("example.csv")
    assert valid is not None
    assert (
        get_cashflow_series_upload(valid[0:0].to_csv(index=False), isfilepath=False)
        is not None
    )

    # empty string
    for column in valid.columns:
        invalid = valid.copy()
        invalid.at[invalid.index[-1], column] = ""
        assert (
            get_cashflow_series_upload(invalid.to_csv(index=False), isfilepath=False)
            is None
        )

    # duplicate account
    invalid = valid.copy()
    invalid.at[invalid.index[-1], "accounts"] = "checking+50 checking+100"
    assert (
        get_cashflow_series_upload(invalid.to_csv(index=False), isfilepath=False)
        is None
    )

    invalid = valid.copy()
    invalid.at[invalid.index[-1], "rrule"] = "invalid"
    assert (
        get_cashflow_series_upload(invalid.to_csv(index=False), isfilepath=False)
        is None
    )


def test_generate_forecast():
    df = generate_forecast(
        get_cashflow_series_upload("example.csv"),
        datetime(2025, 6, 24),
        datetime(2026, 6, 24),
    )
    lastrow = df.iloc[-1]
    assert lastrow["date"] == date(2026, 6, 12)
    assert lastrow["checking"] == -110
    assert lastrow["savings"] == 3240
    assert lastrow["retirement"] == 880
    assert lastrow["desc"] == "paycheck: checking+70 savings+140 retirement+30"
