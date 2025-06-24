from shiny import App, render, ui, reactive, req
from dateutil import rrule
from datetime import date, datetime
import pandas as pd
import yfinance as yf
from shiny_validate import InputValidator, check

# import plotly.express as px
import seaborn as sns

# from shinywidgets import render_plotly
import calendar

FREQ_STR_TO_ENUM = {
    "DAILY": rrule.DAILY,
    "WEEKLY": rrule.WEEKLY,
    "MONTHLY": rrule.MONTHLY,
    "YEARLY": rrule.YEARLY,
}
BYSETPOS_CHOICES = {
    "1": "first",
    "2": "second",
    "3": "third",
    "4": "fourth",
    "-1": "last",
    "-2": "next to last",
}
BYMONTHDAY_MONTHLY_CHOICES = {str(i): str(i) for i in range(1, 29)} | {
    "-2": "next to last",
    "-1": "last",
}
BYMONTHDAY_YEARLY_31_CHOICES = {str(i): str(i) for i in range(1, 32)}
BYMONTHDAY_YEARLY_30_CHOICES = {str(i): str(i) for i in range(1, 31)}
BYMONTHDAY_YEARLY_28_CHOICES = {str(i): str(i) for i in range(1, 29)}
BYWEEKDAY_ABBR_CHOICES = {day[:2].upper(): day for day in calendar.day_abbr}
BYWEEKDAY_CHOICES = {day[:2].upper(): day for day in calendar.day_name}
BYMONTH_CHOICES = dict(list(enumerate(calendar.month_abbr))[1:])


def generate_rrule(
    freq: str,
    interval: int,
    byweekday_weekly: str,
    setpos_monthly: str,
    bysetpos_monthly: str,
    byweekday_monthly: str,
    bymonthday_monthly: str,
    setpos_yearly: str,
    bysetpos_yearly: str,
    byweekday_yearly: str,
    bymonth_bysetpos_yearly: str,
    bymonth_yearly: str,
    bymonthday_yearly: str,
    end: str,
    until: date,
    count: int,
) -> str:
    if freq == "NEVER":
        return "FREQ=DAILY;COUNT=1"  # ;INTERVAL=1
    else:
        RRULE = f"FREQ={freq};INTERVAL={interval}"
        if freq == "WEEKLY":
            RRULE += f";BYDAY={','.join(byweekday_weekly)}"
        elif freq == "MONTHLY":
            if setpos_monthly == "True":
                RRULE += f";BYSETPOS={bysetpos_monthly};BYDAY={byweekday_monthly}"
            else:
                RRULE += f";BYMONTHDAY={bymonthday_monthly()}"
        elif freq == "YEARLY":
            if setpos_yearly == "True":
                RRULE += f";BYSETPOS={bysetpos_yearly};BYDAY={byweekday_yearly};BYMONTH={bymonth_bysetpos_yearly}"
            else:
                RRULE += f";BYMONTH={bymonth_yearly};BYMONTHDAY={bymonthday_yearly}"
        # nothing for DAILY
        if end == "UNTIL":
            RRULE += f";UNTIL={until}"
        elif end == "COUNT":
            RRULE += f";COUNT={count}"
        return RRULE


def generate_occurences(
    row: pd.Series, after: datetime, before: datetime
) -> list[date]:
    # row["rrule"] and row["dtstart"] are str
    return [
        dt.date()
        for dt in rrule.rrulestr(
            row["rrule"], dtstart=datetime.fromisoformat(row["dtstart"])
        ).between(after, before, inc=True)
    ]


def split_account(account: str) -> list[dict[str, int]]:
    # format:
    # checking:+1; savings:+2
    res = {}
    for acc_amt in account.split("; "):
        acc, amt = acc_amt.split(":")
        res[acc] = int(amt)
    return res


def get_stock_price(symbol: str) -> int:
    # _cache = {} TODO
    try:
        return int(yf.Ticker(symbol).history(period="1d")["Close"].iloc[-1])
    except:
        return 0


def generate_forecast(
    cfs: pd.DataFrame,
    after: datetime,
    before: datetime,
    stock_price: int,
) -> pd.DataFrame:
    # assert set(cfs.columns) == set(("desc", "amount", "dtstart", "rrule"))
    # 1. generate occurences from rrule, dtstart, today and forecast_dtend
    cfs["date"] = cfs.apply(
        lambda row: generate_occurences(row, after, before),
        axis=1,
    )

    cfs = cfs.drop(["dtstart", "rrule"], axis=1).explode("date")
    cfs["desc_account"] = cfs["desc"].str.cat(cfs["account"], sep=": ")
    # 2. concat desc_account on date
    cfs_desc_account = cfs.groupby("date")["desc_account"].apply("; ".join)

    # 3. calculate amount on date
    cfs.drop("desc_account", axis=1, inplace=True)
    cfs["account"] = cfs["account"].map(split_account)
    cfs = (
        cfs["account"]
        .apply(pd.Series)
        .fillna(0)
        .set_index(cfs["date"])
        .sort_index()
        .cumsum()
        .reset_index()
        .drop_duplicates(subset=["date"], keep="last")
        .set_index("date")
    )
    cfs["desc"] = cfs_desc_account
    # Convert stock shares to prices
    for column in cfs:
        if column.startswith("$"):
            cfs[column] *= stock_price
    return cfs.reset_index()


repeat_weekly_ui = ui.panel_conditional(
    "input.freq =='WEEKLY'",
    ui.input_checkbox_group(
        "byweekday_weekly",
        None,
        BYWEEKDAY_ABBR_CHOICES,
        inline=True,
    ),
)
repeat_monthly_ui = ui.panel_conditional(
    "input.freq == 'MONTHLY'",
    ui.input_radio_buttons(
        "setpos_monthly",
        None,
        {"False": "on day", "True": "on the"},
        inline=True,
    ),
    ui.panel_conditional(
        "input.setpos_monthly == 'False'",
        ui.input_selectize(
            "bymonthday_monthly",
            None,
            BYMONTHDAY_MONTHLY_CHOICES,
        ),
    ),
    ui.panel_conditional(
        "input.setpos_monthly == 'True'",
        ui.row(
            ui.input_selectize(
                "bysetpos_monthly",
                None,
                BYSETPOS_CHOICES,
                width="50%",
            ),
            ui.input_selectize(
                "byweekday_monthly",
                None,
                BYWEEKDAY_CHOICES,
                width="50%",
            ),
        ),
    ),
)

repeat_yearly_ui = ui.panel_conditional(
    "input.freq == 'YEARLY'",
    ui.input_radio_buttons(
        "setpos_yearly",
        None,
        {"False": "on", "True": "on the"},
        inline=True,
    ),
    ui.panel_conditional(
        "input.setpos_yearly == 'False'",
        ui.row(
            ui.input_selectize(
                "bymonth_yearly",
                None,
                BYMONTH_CHOICES,
                width="50%",
            ),
            ui.input_selectize(
                "bymonthday_yearly",
                None,
                BYMONTHDAY_YEARLY_31_CHOICES,
                width="50%",
            ),
        ),
    ),
    ui.panel_conditional(
        "input.setpos_yearly == 'True'",
        ui.row(
            ui.input_selectize(
                "bysetpos_yearly",
                None,
                BYSETPOS_CHOICES,
                width="30%",
            ),
            ui.input_selectize(
                "byweekday_yearly",
                None,
                BYWEEKDAY_CHOICES,
                width="30%",
            ),
            ui.div("of", style="width:10%;"),
            ui.input_selectize(
                "bymonth_bysetpos_yearly",
                None,
                BYMONTH_CHOICES,
                width="30%",
            ),
        ),
    ),
)

repeat_end_ui = ui.TagList(
    ui.input_radio_buttons(
        "end",
        "End",
        {
            "NEVER": "never",
            "UNTIL": "until",
            "COUNT": "count",
        },
        inline=True,
    ),
    ui.panel_conditional(
        "input.end == 'UNTIL'",
        ui.input_date("until", None),
    ),
    ui.panel_conditional(
        "input.end == 'COUNT'",
        ui.input_numeric("count", None, "1"),
    ),
)
repeat_ui = ui.TagList(
    ui.panel_conditional(
        "!input.advanced_repeat",
        ui.input_selectize(
            "freq",
            "Repeat",
            {
                "NEVER": "never",
                "DAILY": "daily",
                "WEEKLY": "weekly",
                "MONTHLY": "monthly",
                "YEARLY": "yearly",
            },
        ),
        ui.panel_conditional(
            "[ 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY' ].includes( input.freq )",
            # TODO manually inline
            ui.row(
                ui.div("every", style="width:33%;"),
                ui.input_numeric("interval", None, "1", width="33%"),
                ui.div(
                    ui.output_text("freq_selected", inline=True), style="width:33%;"
                ),
            ),
        ),
        repeat_weekly_ui,
        repeat_monthly_ui,
        repeat_yearly_ui,
        repeat_end_ui,
    ),
    ui.panel_conditional(
        "input.advanced_repeat",
        ui.input_text("custom_rrule", "Input RFC5545 (iCalendar) RRULE here"),
    ),
    ui.input_switch("advanced_repeat", "Advanced Repeat", False),
)

account_ui = ui.TagList(
    ui.row(
        ui.input_action_button("add_account_ui", "Add another account", width="50%"),
        ui.input_action_button(
            "delete_account_ui", "Delete previous account", disabled=True, width="50%"
        ),
        id="add_delete_account_ui",
    ),
)

app_ui = ui.page_fluid(
    ui.layout_columns(
        ui.card(
            ui.card_header("Add a Cash Flow Series"),
            ui.input_text("desc", "Description", placeholder="current"),
            account_ui,
            ui.input_date("dtstart", "Start Date"),
            repeat_ui,
            ui.hr(),
            ui.input_action_button("add_cashflow_series", "Add the cash flow series"),
        ),
        ui.card(
            ui.card_header("Added Cash Flow Series"),
            ui.output_data_frame("show_cashflow_series"),
            ui.row(
                ui.input_action_button(
                    "save_cashflow_series_edits",
                    "Save Cash Flow Series Edits",
                    width="50%",
                ),
                ui.download_button(
                    "download_cashflow_series",
                    "Download All Cash Flow Series",
                    width="50%",
                ),
            ),
            ui.row(
                ui.input_action_button(
                    "delete_cashflow_series",
                    "Delete Selected Cash Flow Series",
                    width="50%",
                ),
                ui.input_action_button(
                    "delete_all_cashflow_series",
                    "Delete All Cash Flow Series",
                    width="50%",
                ),
            ),
            ui.input_file(
                "upload_cashflow_series", "Upload Cash Flow Series", accept=[".csv"]
            ),
        ),
        ui.card(
            ui.card_header("Cash Flow Forecast"),
            ui.row(
                ui.input_date(
                    "forecast_dtend",
                    "Forecast End Date",
                    value=(date.today() + pd.DateOffset(years=2)).date(),
                    startview="year",
                    width="50%",
                ),
                ui.input_switch(
                    "forecast_graph", "Show Forecast as Graph", width="50%"
                ),
            ),
            ui.panel_conditional(
                "!input.forecast_graph",
                ui.output_data_frame("cashflow_forecast_table"),
            ),
            ui.panel_conditional(
                "input.forecast_graph",
                ui.output_plot("cashflow_forecast_graph"),
            ),
            ui.input_numeric(
                "set_stock_price",
                "Set Stock Price",
                0,
            ),
        ),
        col_widths=(2, 4, 6),
    ),
    title="Cash Flow Forecast",
)


def server(input, output, session):
    account_ui_counter = reactive.value(0) # TODO not actually a reactive value
    cashflow_series = reactive.value(
        pd.DataFrame(columns=["desc", "account", "dtstart", "rrule"])
    )
    cfs_validator = InputValidator()
    cfs_validator.add_rule("dtstart", check.required())
    cfs_validator.add_rule("freq", check.required())
    # assume user does not maliciously send empty data
    # cfs_validator.add_rule("interval", check.required())
    # cfs_validator.add_rule("byweekday_weekly", check.required()) # tuple?
    # cfs_validator.add_rule("bymonthday_monthly", check.required())
    # cfs_validator.add_rule("bysetpos_monthly", check.required())
    # cfs_validator.add_rule("byweekday_monthly", check.required())
    # cfs_validator.add_rule("bymonth_monthly", check.required())
    # cfs_validator.add_rule("bymonthday_yearly", check.required())
    # cfs_validator.add_rule("bysetpos_yearly", check.required())
    # cfs_validator.add_rule("byweekday_yearly, check.required())
    # cfs_validator.add_rule("bymonth_setpos_yearly, check.required())

    rrule_validator = InputValidator()

    def validate_rrule(rrulestr: str | None) -> str | None:
        try:
            rrule.rrulestr(rrulestr)
        except (TypeError, ValueError):
            return "invalid RRULE"
        return None

    rrule_validator.add_rule("custom_rrule", validate_rrule)

    @reactive.effect
    def update_bymonthday_yearly():
        if input.bymonth_yearly() == "2":
            ui.update_selectize(
                "bymonthday_yearly", choices=BYMONTHDAY_YEARLY_28_CHOICES
            )
        elif input.bymonth_yearly() in ["4", "6", "9", "11"]:
            ui.update_selectize(
                "bymonthday_yearly", choices=BYMONTHDAY_YEARLY_30_CHOICES
            )
        else:
            ui.update_selectize(
                "bymonthday_yearly", choices=BYMONTHDAY_YEARLY_31_CHOICES
            )

    @reactive.effect
    @reactive.event(input.add_cashflow_series)
    def add_cashflow_series():
        cfs_validator.enable()
        req(cfs_validator.is_valid())
        if input.advanced_repeat():
            rrule_validator.enable()
            req(rrule_validator.is_valid())
            RRULE = input.custom_rrule()
        else:
            RRULE = generate_rrule(
                input.freq(),
                input.interval(),
                input.byweekday_weekly(),
                input.setpos_monthly(),
                input.bysetpos_monthly(),
                input.byweekday_monthly(),
                input.bymonthday_monthly(),
                input.setpos_yearly(),
                input.bysetpos_yearly(),
                input.byweekday_yearly(),
                input.bymonth_bysetpos_yearly(),
                input.bymonth_yearly(),
                input.bymonthday_yearly(),
                input.end(),
                input.until(),
                input.count(),
            )
        acc_amt = f"{input.account1()}:{input.amount1():+}"
        for i in range(2, account_ui_counter() + 1):
            acc = getattr(input, f"account{i}")()
            amt = getattr(input, f"amount{i}")()
            acc_amt += f"; {acc}:{amt:+}"

        # update cashflow_series
        cfs = cashflow_series()
        if input.desc().lower() == "current":
            cfs = cfs[cfs["desc"].str.lower() != "current"]
        cashflow_series.set(
            pd.concat(
                [
                    cfs,
                    pd.DataFrame(
                        {
                            "desc": [input.desc()],
                            "account": [acc_amt],
                            "dtstart": [input.dtstart().isoformat()],
                            "rrule": [RRULE],
                        }
                    ),
                ]
            ).reset_index(drop=True)
        )
        # reset ui
        ui.update_text("desc", value="")
        ui.update_selectize("account1", selected="checking")
        ui.update_numeric("amount1", value=0)
        for i in range(2, account_ui_counter() + 1):
            ui.remove_ui(f"account-row{i}")
        account_ui_counter.set(1)
        ui.update_action_button("delete_account_ui", disabled=True)
        ui.update_date("dtstart", value=date.today())
        ui.update_selectize("freq", selected="NEVER")
        ui.update_numeric("interval", value=1)
        ui.update_checkbox("byweekday_weekly", value=tuple())
        ui.update_radio_buttons("setpos_monthly", selected="False")
        ui.update_selectize("bymonthday_monthly", selected="1")
        ui.update_selectize("bysetpos_monthly", selected="1")
        ui.update_selectize("byweekday_monthly", selected="MO")
        ui.update_radio_buttons("setpos_yearly", selected="False")
        ui.update_selectize("bymonth_yearly", selected="1")
        ui.update_selectize("bymonthday_yearly", selected="1")
        ui.update_selectize("bysetpos_yearly", selected="1")
        ui.update_selectize("byweekday_yearly", selected="MO")
        ui.update_selectize("bymonth_setpos_yearly", selected="1")
        ui.update_radio_buttons("end", selected="NEVER")
        ui.update_switch("advanced_repeat", value=False)
        ui.update_text("custom_rrule", value="")
        cfs_validator.disable()
        rrule_validator.disable()

    @render.data_frame
    def show_cashflow_series():
        cfs = cashflow_series()
        # TODO edit via UI
        return render.DataGrid(cfs, editable=True, selection_mode="rows")

    @reactive.effect
    def update_stock_price():
        # update stock price
        for column in cashflow_forecast():
            if column.startswith("$"):
                ui.update_numeric(
                    "set_stock_price",
                    label=f"Set {column} Price",
                    value=get_stock_price(column[1:]),
                )

    @render.text
    def freq_selected():
        return {
            "": "",
            "NEVER": "",
            "DAILY": "days",
            "WEEKLY": "weeks",
            "MONTHLY": "months",
            "YEARLY": "years",
        }[input.freq()]

    @render.download(filename=f"cashflow_series_{date.today().isoformat()}.csv")
    def download_cashflow_series():
        yield cashflow_series().to_csv(index=False)

    @reactive.effect
    @reactive.event(input.add_account_ui, ignore_none=False)
    def add_account_ui():
        # ui.update_action_button("#delete_account_ui", disabled=False)
        nex = account_ui_counter() + 1
        ui.insert_ui(
            ui.row(
                ui.tooltip(
                    ui.input_selectize(
                        f"account{nex}",
                        "Account",
                        {
                            "checking": "checking",
                            "savings": "savings",
                            "retirement": "retirement",
                            "investment": "investment",
                        },
                        width="50%",
                        remove_button=True,
                        options={"placeholder": "Account name", "create": True},
                    ),
                    "Type $TICKER to add a stock",
                ),
                ui.input_numeric(f"amount{nex}", "Amount", 0, width="50%"),
                id=f"account-row{nex}",
            ),
            "#add_delete_account_ui",
            where="beforeBegin",
        )
        account_ui_counter.set(nex)
        if nex > 1:
            ui.update_action_button("delete_account_ui", disabled=False)
        if nex == 1:
            pass
            # TODO shiny_validate delete_rule
            # cfs_validator.add_rule(f"account{nex}", check.required())
            # cfs_validator.add_rule(f"amount{nex}", check.required())  # integer?

    @reactive.effect
    @reactive.event(input.delete_account_ui)
    def delete_account_ui():
        cur = account_ui_counter()
        ui.remove_ui(f"#account-row{cur}")
        account_ui_counter.set(cur - 1)
        if cur <= 2:
            ui.update_action_button("delete_account_ui", disabled=True)

    @reactive.effect
    @reactive.event(input.delete_all_cashflow_series)
    def delete_all_cashflow_series():
        cashflow_series.set(cashflow_series()[0:0])

    @reactive.effect
    @reactive.event(input.delete_cashflow_series)
    def delete_cashflow_series():
        cfs = cashflow_series()
        selected_rows = show_cashflow_series.cell_selection()["rows"]
        if selected_rows:  # need to convert tuple to list
            cashflow_series.set(cfs.drop(list(selected_rows)).reset_index(drop=True))

    @reactive.effect
    @reactive.event(input.upload_cashflow_series)
    def upload_cashflow_series():
        cashflow_series.set(pd.read_csv(input.upload_cashflow_series()[0]["datapath"]))

    @reactive.calc
    def cashflow_forecast():
        cfs = cashflow_series().copy()
        if len(cfs) == 0:
            return pd.DataFrame(columns=["date", "account", "desc"])
        after = datetime.fromordinal(date.today().toordinal())
        before = datetime.fromordinal(input.forecast_dtend().toordinal())
        return generate_forecast(cfs, after, before, input.set_stock_price())

    @render.data_frame
    def cashflow_forecast_table():
        return render.DataGrid(cashflow_forecast())

    @reactive.effect
    @reactive.event(input.save_cashflow_series_edits)
    def save_cashflow_series_edits():
        cashflow_series.set(show_cashflow_series.data_patched())

    @render.plot
    def cashflow_forecast_graph():
        df = cashflow_forecast()
        if len(df) == 0:
            return None
        df = df.drop("desc", axis=1).set_index("date")
        df.columns.name = "account"
        p = sns.lineplot(df)
        p.set_ylabel("amount")
        return p


app = App(app_ui, server)

# TODO README.md
# inflation and interest rate/investment yield ignored
# add an entry named "current" will update the existing entry named "current"
# pre-populated examples
# paycheck FREQ=WEEKLY;INTERVAL=2;BYDAY=FR
# RSU FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=20
# rent FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=1
# credit card bill FREQ=MONTHLY;INTERVAL=1;BYMONTHDAY=10
# flights FREQ=YEARLY;INTERVAL=1;BYMONTH=8;BYMONTHDAY=1
# TODO testing
# https://shiny.posit.co/py/docs/unit-testing.html
# https://shiny.posit.co/py/docs/end-to-end-testing.html
