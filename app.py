import calendar
from datetime import date, datetime
from io import StringIO

from dateutil import rrule
import humanize
import pandas as pd

# import plotly.express as px
import quantmod.charts
from shiny import App, render, ui, reactive, req

# from shinywidgets import output_widget, render_plotly
from shiny_validate import InputValidator, check
import yfinance as yf

question_circle_fill = ui.HTML(
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-question-circle-fill mb-1" viewBox="0 0 16 16"><path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM5.496 6.033h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 0 0 .25.246h.811a.25.25 0 0 0 .25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286a.237.237 0 0 0 .241.247zm2.325 6.443c.61 0 1.029-.394 1.029-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94 0 .533.425.927 1.01.927z"/></svg>'
)

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
        RRULE = f"FREQ={freq}"
        if interval > 1:
            RRULE += f";INTERVAL={interval}"
        if freq == "WEEKLY":
            RRULE += f";BYDAY={','.join(byweekday_weekly)}"
        elif freq == "MONTHLY":
            if setpos_monthly == "True":
                RRULE += f";BYSETPOS={bysetpos_monthly};BYDAY={byweekday_monthly}"
            else:
                RRULE += f";BYMONTHDAY={bymonthday_monthly}"
        elif freq == "YEARLY":
            if setpos_yearly == "True":
                RRULE += f";BYSETPOS={bysetpos_yearly};BYDAY={byweekday_yearly};BYMONTH={bymonth_bysetpos_yearly}"
            else:
                RRULE += f";BYMONTH={bymonth_yearly};BYMONTHDAY={bymonthday_yearly}"
        # nothing for DAILY
        if end == "UNTIL":
            RRULE += ";UNTIL=" + until.strftime("%Y%m%dT0000Z")
        elif end == "COUNT":
            RRULE += f";COUNT={count}"
        return RRULE


def generate_occurences(row: pd.Series, after: datetime, before: datetime) -> list[str]:
    # row["rrule"] and row["dtstart"] are str
    return [
        dt.date().isoformat()
        for dt in rrule.rrulestr(
            row["rrule"], dtstart=datetime.fromisoformat(row["dtstart"]), ignoretz=True
        ).between(after, before, inc=True)
    ]


def split_account(account: str) -> list[dict[str, int]]:
    # format:
    # checking+1 savings-2
    res = {}
    for acc_amt in account.split():
        acc_amt = acc_amt.split("+")
        if len(acc_amt) == 2:
            acc, amt = acc_amt
        else:
            acc, amt = acc_amt[0].split("-")
            amt = "-" + amt
        res[acc] = int(amt)
    return res


def get_stock_price(symbol: str) -> int:
    # _cache = {} TODO
    try:
        return int(yf.Ticker(symbol).history(period="1d")["Close"].iloc[-1])
    except (TypeError, ValueError):
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
    cfs = cfs[cfs["date"].notna()]

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
    cfs["desc_account"] = cfs["desc"].str.cat(cfs["account"], sep=": ")
    cfs_desc_account = cfs.groupby("date")["desc_account"].apply("; ".join)

    # 4. calculate amount on date
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

    # 5. convert stock shares to prices
    for column in cfs:
        if column.startswith("$"):
            cfs[column] *= stock_price
            break
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
        ui.input_numeric("count", None, 1, min=1),
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
            ui.row(
                ui.div("every", style="width:33%;"),
                ui.input_numeric("interval", None, 1, min=1, width="33%"),
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
        ui.input_action_button("add_account_ui", "+ account", width="50%"),
        ui.input_action_button(
            "delete_account_ui", "- account", disabled=True, width="50%"
        ),
        id="add_delete_account_ui",
    ),
)

app_ui = ui.page_sidebar(
    ui.sidebar(
        "Add a Cash Flow Series",
        ui.input_text(
            "desc",
            ui.popover(
                ui.span("Description ", question_circle_fill),
                "`balance` is a required special description that sets the forecast start date. "
                "`*_override`s are special descriptions that override specific dates of the prefix description.",
            ),
            placeholder="balance",
        ),
        ui.help_text(),
        account_ui,
        ui.input_date("dtstart", "Start Date"),
        repeat_ui,
        ui.hr(),
        ui.input_action_button("add_cashflow_series", "Submit"),
        width="350px",
    ),
    ui.accordion(
        ui.accordion_panel(
            "Cash Flow Series",
            ui.output_data_frame("show_cashflow_series"),
            ui.row(
                ui.input_action_button(
                    "save_cashflow_series_edits",
                    "Save Edits",
                    width="12%",
                ),
                ui.input_action_button(
                    "delete_cashflow_series",
                    "Delete Selected",
                    width="12%",
                ),
                ui.input_action_button(
                    "delete_all_cashflow_series",
                    "Delete All",
                    width="12%",
                ),
                ui.download_button(
                    "download_cashflow_series",
                    "Download",
                    width="12%",
                ),
            ),
            ui.p(),
            ui.input_file(
                "upload_cashflow_series",
                None,
                button_label="Upload",
                accept=[".csv"],
                width="48%",
            ),
        ),
        ui.accordion_panel(
            "Cash Flow Forecast",
            ui.row(
                ui.output_text("show_forecast_dtstart"),
                ui.input_date(
                    "forecast_dtend",
                    "Forecast End Date",
                    value=(date.today() + pd.DateOffset(years=2)).date(),
                    startview="year",
                    width="50%",
                ),
                # humanize.naturaltime(datetime.from)
                ui.input_switch("forecast_graph", "Graph", width="50%"),
            ),
            ui.panel_conditional(
                "!input.forecast_graph",
                ui.output_data_frame("cashflow_forecast_table"),
            ),
            ui.panel_conditional(
                "input.forecast_graph",
                # output_widget("cashflow_forecast_graph"),
                ui.output_ui("cashflow_forecast_graph"),
            ),
            ui.input_numeric(
                "set_stock_price",
                "Set Stock Price",
                0,
                min=0,
            ),
            ui.help_text("default is last day close price"),
        ),
    ),
    ui.tags.footer(
        "Disclaimer: Your data will be lost when you reload the page. Please download to save them."
    ),
    title="Cash Flow Forecast",
)


def validate_rrule(rrulestr: str | None) -> str | None:
    try:
        rrule.rrulestr(rrulestr)
    except (TypeError, ValueError):
        return "invalid RRULE"
    return None


def server(input, output, session):
    account_ui_counter = reactive.value((0, 0))  # prev, curr
    cashflow_series = reactive.value(pd.read_csv("example.csv"))
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
    rrule_validator.add_rule("custom_rrule", validate_rrule)

    @reactive.calc
    def forecast_dtstart() -> pd.Series:
        cfs = cashflow_series()
        return cfs[cfs["desc"] == "balance"]["dtstart"]

    @render.text
    def show_forecast_dtstart():
        dtstart = forecast_dtstart()
        if len(dtstart) == 0:
            return "Please add a balance to set forecast start date"
        return (
            "Forecast Start Date: "
            + dtstart.iloc[0]
            + " "
            + humanize.naturaltime(
                datetime.fromisoformat(dtstart.iloc[0]),
                when=datetime.fromordinal(date.today().toordinal()),
            )
        )

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
        acc_amt = " ".join(
            "{}{:+}".format(
                getattr(input, f"account{i}")(), getattr(input, f"amount{i}")()
            )
            for i in range(1, account_ui_counter()[1] + 1)
        )  # format: checking+8 savings-5

        # update cashflow_series
        cfs = cashflow_series()
        if input.desc().lower() == "balance":
            cfs = cfs[cfs["desc"].str.lower() != "balance"]
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
        account_ui_counter.set((account_ui_counter()[1], 1))
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
                break

    @render.text
    def freq_selected():
        return {
            "": "",
            "NEVER": "",
            "DAILY": " days",
            "WEEKLY": " weeks",
            "MONTHLY": " months",
            "YEARLY": " years",
        }[input.freq()]

    @render.download(filename=f"cashflow_series_{date.today().isoformat()}.csv")
    def download_cashflow_series():
        yield cashflow_series().to_csv(index=False)

    @reactive.effect
    @reactive.event(input.add_account_ui, ignore_none=False)
    def add_account_ui():
        curr = account_ui_counter()[1]
        account_ui_counter.set((curr, curr + 1))

    @reactive.effect
    @reactive.event(input.delete_account_ui)
    def delete_account_ui():
        curr = account_ui_counter()[1]
        account_ui_counter.set((curr, curr - 1))

    @reactive.effect
    def update_account_ui():
        prev, curr = account_ui_counter()
        if curr > prev:
            assert curr == prev + 1
            ui.insert_ui(
                ui.row(
                    ui.tooltip(
                        ui.input_selectize(
                            f"account{curr}",
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
                        placement="top",
                    ),
                    ui.input_numeric(f"amount{curr}", "Amount in USD", 0, width="50%"),
                    id=f"account-row{curr}",
                ),
                "#add_delete_account_ui",
                where="beforeBegin",
            )
            if curr > 1:
                ui.update_action_button("delete_account_ui", disabled=False)
            # TODO only add if we can shiny_validate delete_rule
            # cfs_validator.add_rule(f"account{nex}", check.required())
            # cfs_validator.add_rule(f"amount{nex}", check.required())  # integer?

            def update_amount_label():
                if getattr(input, f"account{curr}")().startswith("$"):
                    ui.update_numeric(f"amount{curr}", label="Amount in shares")
                else:
                    ui.update_numeric(f"amount{curr}", label="Amount in USD")

            setattr(
                server,
                f"update_amount_label{curr}",
                reactive.effect(update_amount_label),
            )
        elif curr < prev:
            for i in range(curr + 1, prev + 1):
                ui.remove_ui(f"#account-row{i}")
                delattr(server, f"update_amount_label{i}")
            if curr == 1:
                ui.update_action_button("delete_account_ui", disabled=True)

    @reactive.effect
    @reactive.event(input.delete_all_cashflow_series)
    def delete_all_cashflow_series():
        cashflow_series.set(cashflow_series()[0:0])

    @reactive.effect
    @reactive.event(input.delete_cashflow_series)
    def delete_cashflow_series():
        cfs = cashflow_series()
        cfs_rows = show_cashflow_series.cell_selection()["rows"]
        if cfs_rows:  # need to convert tuple to list
            cashflow_series.set(cfs.drop(list(cfs_rows)).reset_index(drop=True))

    @reactive.effect
    @reactive.event(input.upload_cashflow_series)
    def upload_cashflow_series():
        cashflow_series.set(pd.read_csv(input.upload_cashflow_series()[0]["datapath"]))

    @reactive.calc
    def cashflow_forecast() -> pd.DataFrame:
        cfs = cashflow_series().copy()
        try:
            assert len(cfs) != 0
            after = datetime.fromisoformat(forecast_dtstart().iloc[0])
        except (AssertionError, IndexError):
            return pd.DataFrame(columns=["date", "account", "desc"])
        before = datetime.fromordinal(input.forecast_dtend().toordinal())
        return generate_forecast(cfs, after, before, input.set_stock_price())

    @render.data_frame
    def cashflow_forecast_table():
        return render.DataGrid(cashflow_forecast())

    @reactive.effect
    @reactive.event(input.save_cashflow_series_edits)
    def save_cashflow_series_edits():
        cashflow_series.set(show_cashflow_series.data_patched())

    @reactive.effect
    @reactive.event(input.discard_cashflow_series_edits)
    def discard_cashflow_series_edits():
        # TODO
        pass  # cashflow_forecast_table()  # will discard data_patched()

    # @render_plotly
    @render.ui
    def cashflow_forecast_graph():
        df = cashflow_forecast()
        req(len(df) != 0)
        f = StringIO()
        df.drop("desc", axis=1).set_index("date").iplot(kind="overlay").write_html(f)
        return ui.HTML(f.getvalue())


app = App(app_ui, server)

# TODO README.md
# inflation and interest rate/investment yield ignored
# add an entry named "current" will update the existing entry named "current"
# pre-populated examples
# paycheck FREQ=WEEKLY;INTERVAL=2;BYDAY=FR
# RSU FREQ=MONTHLY;INTERVAL=3;BYMONTHDAY=20
# rent FREQ=MONTHLY;BYMONTHDAY=1
# credit card bill FREQ=MONTHLY;BYMONTHDAY=10
# flights FREQ=YEARLY;BYMONTH=8;BYMONTHDAY=1
# TODO testing
# https://shiny.posit.co/py/docs/unit-testing.html
# https://shiny.posit.co/py/docs/end-to-end-testing.html
