from constants import BYMONTHDAY_MONTHLY_CHOICES, BYWEEKDAY_ORD_CHOICES
from datetime import datetime, date
from io import StringIO
import logging

from dateutil import rrule
import pandas as pd
import pandera.pandas as pa
from shiny import req
from shiny_validate import InputValidator
import yfinance as yf

logger = logging.getLogger("cashflow")


class CashFlowSeriesSchema(pa.DataFrameModel):
    desc: str = pa.Field(str_length=1)
    accounts: str = pa.Field()
    dtstart: date = pa.Field()
    rrule: str = pa.Field()

    @pa.check("accounts")
    def validate_accounts(cls, series: pd.Series) -> pd.Series:
        return series.map(split_accounts).map(bool)

    @pa.check("rrule")
    def validate_rrule(cls, series: pd.Series) -> pd.Series:
        return ~series.map(validate_rrule).map(bool)


def required(
    val: (
        str
        | int
        | float
        | tuple[str, ...]
        | tuple[date | None, date | None]
        | date
        | None
    ),
) -> str | None:
    """
    applicable to (as of shiny 1.4.0):
    - ui.input_seletize : str | tuple[str, ...]
    - ui.input_date: date | None,
    - ui.input_date_range: tuple[date | None, date | None]
    - ui.input_checkbox: tuple[str]
    - ui.input_numeric: int | float | None
    - ui.input_text: str
    - ui.input_text_area: str
    - ui.input_password: str
    all other ui.input_* are inapplicable or unnecessary.

    this function is not the same as bool because bool
    - treats 0 as falsy
    - treats a tuple containing None as truthy
    """
    if val is None:
        return "Required"
    if isinstance(val, str | tuple) and len(val) == 0:
        return "Required"
    if isinstance(val, tuple) and any(v is None for v in val):
        return "Required"
    return None


def integer(val: int | float | None) -> str | None:
    """
    applicable to: ui.input_numeric
    """
    if val is None or isinstance(val, float):
        return "Integer Required"
    return None


def validate_rrule(rrulestr: str | None) -> str | None:
    """returns an error string if ValueError"""
    try:
        for invalid in [
            "FREQ=SECONDLY",
            "FREQ=MINUTELY",
            "FREQ=HOURLY",
            "BYHOUR=",
            "BYMINUTE=",
            "BYSECOND=",
        ]:
            assert invalid not in rrulestr
        rrule_obj = rrule.rrulestr(rrulestr)
        assert not rrule_obj._byeaster  # dateutil.rrule extension
    except (AssertionError, ValueError):
        return "invalid rrulestr"
    return None


def generate_rrulestr(
    *,
    validator: InputValidator,
    freq: str = "NEVER",
    interval: int | float | None = 1,
    byweekday_weekly: tuple[str] = tuple(),
    onday_monthly: str = "monthday",
    byweekday_ord_monthly: str = "1",
    byweekday_monthly: str = "MO",
    bymonthday_monthly: str = "1",
    onday_yearly: str = "monthday",
    byweekday_ord_yearly: str = "1",
    byweekday_yearly: str = "MO",
    bymonth_byweekday_yearly: str = "1",
    bymonth_yearly: str = "1",
    bymonthday_yearly: str = "1",
    end: str = "NEVER",
    until: date | None = None,
    count: int | float | None = 1,
) -> str:
    validator.add_rule("freq", required)
    req(validator.is_valid())
    if freq == "NEVER":
        return "FREQ=DAILY;COUNT=1"  # ;INTERVAL=1
    else:
        rrulestr = f"FREQ={freq}"
        validator.add_rule("interval", integer)
        req(validator.is_valid())
        if interval > 1:
            rrulestr += f";INTERVAL={interval}"
        if freq == "WEEKLY":
            validator.add_rule("byweekday_weekly", required)
            req(validator.is_valid())
            rrulestr += f";BYDAY={','.join(byweekday_weekly)}"
        elif freq == "MONTHLY":
            if onday_monthly == "weekday":
                validator.add_rule("byweekday_ord_monthly", required)
                validator.add_rule("byweekday_monthly", required)
                req(validator.is_valid())
                rrulestr += f";BYDAY={byweekday_ord_monthly}{byweekday_monthly}"
            else:
                validator.add_rule("bymonthday_monthly", required)
                req(validator.is_valid())
                rrulestr += f";BYMONTHDAY={bymonthday_monthly}"
        elif freq == "YEARLY":
            if onday_yearly == "weekday":
                validator.add_rule("byweekday_ord_yearly", required)
                validator.add_rule("byweekday_yearly", required)
                validator.add_rule("bymonth_byweekday_yearly", required)
                req(validator.is_valid())
                rrulestr += f";BYDAY={byweekday_ord_yearly}{byweekday_yearly};BYMONTH={bymonth_byweekday_yearly}"
            else:
                validator.add_rule("bymonth_yearly", required)
                validator.add_rule("bymonthday_yearly", required)
                req(validator.is_valid())
                rrulestr += f";BYMONTH={bymonth_yearly};BYMONTHDAY={bymonthday_yearly}"
        # nothing for freq == "DAILY"
        if end == "UNTIL":
            validator.add_rule("until", required)
            req(validator.is_valid())
            rrulestr += ";UNTIL=" + until.strftime("%Y%m%dT0000Z")
        elif end == "COUNT":
            validator.add_rule("count", integer)
            req(validator.is_valid())
            rrulestr += f";COUNT={count}"
        # nothing for end == "Never"
        return rrulestr


def parse_rrulestr(rrulestr: str) -> tuple[rrule.rrule | None, str]:
    rrule_obj = rrule.rrulestr(rrulestr)
    if (
        rrule_obj._wkst
        or rrule_obj._bysetpos
        or rrule_obj._byyearday
        or rrule_obj._byweekno
    ):
        return None, "advanced_repeat"

    # checklist: BYDAY (_byweekday, _bynweekday), BYMONTHDAY (_bymonthday, _bynmonthdat), BYMONTH
    if rrule_obj._freq == rrule.WEEKLY:
        if (
            not rrule_obj._byweekday
            or rrule_obj._bynweekday
            or rrule_obj._bymonthday
            or rrule_obj._bynmonthday
            or rrule_obj._bymonth
        ):
            return None, "advanced_repeat"
        else:
            return rrule_obj, "byweekday_weekly"

    if rrule_obj._freq == rrule.MONTHLY:
        if rrule_obj._byweekday or rrule_obj._bymonth:
            # _bynmonthday is allowed because -2, -1
            return None, "advanced_repeat"

        if rrule_obj._bymonthday or rrule_obj._bynmonthday:  # 1 to 28, or -2, -1
            if (
                rrule_obj._bynweekday
                or rrule_obj._bymonthday
                and (
                    len(rrule_obj._bymonthday) > 1
                    or str(rrule_obj._bymonthday[0])
                    not in BYMONTHDAY_MONTHLY_CHOICES.keys()
                )
                or rrule_obj._bynmonthday
                and (
                    len(rrule_obj._bynmonthday) > 1
                    or str(rrule_obj._bynmonthday[0])
                    not in BYMONTHDAY_MONTHLY_CHOICES.keys()
                )
            ):
                return None, "advanced_repeat"
            return rrule_obj, "bymonthday_monthly"

        if rrule_obj._bynweekday:
            if (
                len(rrule_obj._bynweekday) > 1
                or str(rrule_obj._bynweekday[0][1]) not in BYWEEKDAY_ORD_CHOICES.keys()
            ):
                return None, "advanced_repeat"
            return rrule_obj, "byweekday_monthly"

        return None, "advanced_repeat"

    # YEARLY
    if (
        rrule_obj._byweekday
        or rrule_obj._bynmonthday
        or not rrule_obj._bymonth
        or len(rrule_obj._bymonth) > 1
    ):
        # only _bynweekday or _bymonthday
        return None, "advanced_repeat"

    if rrule_obj._bymonthday:
        if len(rrule_obj._bymonthday) > 1 or rrule_obj._bynweekday:
            return None, "advanced_repeat"
        return rrule_obj, "bymonthday_yearly"

    if rrule_obj._bynweekday:
        if len(rrule_obj._bynweekday) > 1:
            return None, "advanced_repeat"
        return rrule_obj, "byweekday_yearly"

    return None, "advanced_repeat"


def generate_occurences(
    row: pd.Series, after: datetime, before: datetime
) -> list[date]:
    """
    row: row["rrule"] and row["dtstart"] are str
    throws: ValueError
    """
    return [
        dt.date()
        for dt in rrule.rrulestr(
            row["rrule"],
            dtstart=datetime.fromordinal(row["dtstart"].toordinal()),
            ignoretz=True,
        ).between(after, before, inc=True)
    ]


def split_accounts(accounts: str) -> dict[str, int | float]:
    """
    accounts: formatted like checking+1 savings-2
    return: {"checking":1, "savings":-2} or empty dict when ValueError
    noexcept
    """
    ret = {}
    for account in accounts.split():
        try:
            if "+" in account:
                name, amt = account.split("+")
            elif "-" in account:
                name, amt = account.split("-")
                amt = "-" + amt
            else:
                return {}
            if name in ret:
                # duplicate account name not allowed
                return {}
            if "." in amt:
                ret[name] = round(float(amt), 2)
            else:
                ret[name] = int(amt)
        except ValueError:
            return {}
    return ret


def get_stock_price(symbol: str, cache: dict[str, float]) -> float:
    # Yahoo Finance API https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d
    # Accessing the API with `requests` is blocked (liekly due to TLS handshake fingerprint)
    # yfinance uses `curl-cffi` which can masquerade as broswer
    if symbol not in cache:
        try:
            cache[symbol] = round(
                yf.Ticker(symbol).history(period="1d")["Close"].iloc[-1], 2
            )
        except (TypeError, ValueError) as e:
            logger.error(f"get_stock_price error {e}")
    return cache.get(symbol, 0.0)


def sort_cfs(cfs: pd.DataFrame):
    # make sure balance entry comes first
    cfs.sort_values(
        "desc",
        inplace=True,
        key=lambda series: series.map(
            lambda desc: "\x00" + desc if desc == "balance" else desc
        ),
    )
    cfs.reset_index(drop=True, inplace=True)


def get_cashflow_series_upload(
    filepath_or_content: str, isfilepath: bool = True
) -> pd.DataFrame | None:
    if not isfilepath:
        filepath_or_buffer = StringIO()
        filepath_or_buffer.write(filepath_or_content)
        filepath_or_buffer.seek(0)
    else:
        filepath_or_buffer = filepath_or_content
    try:
        cfs = pd.read_csv(filepath_or_buffer)
        cfs["dtstart"] = cfs["dtstart"].map(date.fromisoformat)
        CashFlowSeriesSchema.validate(cfs)
        assert sum(cfs["desc"] == "balance") <= 1
        return cfs
    except (
        AssertionError,
        KeyError,
        TypeError,
        ValueError,
        pa.errors.SchemaError,
    ) as e:
        logger.error(f"get_cashflow_series_upload error {e}")
        return None


def generate_forecast(
    cfs: pd.DataFrame,
    after: datetime,
    before: datetime,
) -> pd.DataFrame:
    # 1. generate occurences from rrule, dtstart, today and forecast_dtend
    cfs["date"] = cfs.apply(
        lambda row: generate_occurences(row, after, before),
        axis=1,
    )
    cfs = cfs.drop(["dtstart", "rrule"], axis=1).explode("date")
    cfs = cfs[cfs["date"].notna()]  # due to empty lists

    # 2. process *_override
    regular = cfs[~cfs["desc"].str.endswith("_override")].reset_index(drop=True)
    overrides = cfs[cfs["desc"].str.endswith("_override")]

    def process_override(row: pd.Series) -> pd.Series:
        row["desc"] = row["desc"].removesuffix("_override")
        regular.drop(
            regular.index[
                (regular["desc"] == row["desc"]) & (regular["date"] == row["date"])
            ],
            inplace=True,
        )
        return row

    cfs = pd.concat([regular, overrides.apply(process_override, axis=1)], axis=0)

    # 3. concat desc_account on date
    cfs["desc_accounts"] = cfs["desc"].str.cat(cfs["accounts"], sep=": ")
    cfs_desc_account = cfs.groupby("date")["desc_accounts"].apply("; ".join)

    # 4. calculate amount on date
    cfs.drop("desc_accounts", axis=1, inplace=True)
    cfs["accounts"] = cfs["accounts"].map(split_accounts)
    cfs = (
        cfs["accounts"]
        .apply(pd.Series)
        .fillna(0)
        .set_index(cfs["date"])
        .sort_index()
        .cumsum()
        .round(2)
        .reset_index()
        .drop_duplicates(subset=["date"], keep="last")
        .set_index("date")
    )
    cfs["desc"] = cfs_desc_account
    return cfs.reset_index()
