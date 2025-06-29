from add_entry import add_entry_ui, add_entry_server
from view_table import view_table_ui, view_table_server
from forecast import forecast_ui, forecast_server
from utils import split_accounts

import functools
import operator
import logging

import pandas as pd
from shiny import App, ui, reactive

logging.basicConfig(level=logging.INFO)

SHINY_MODULE_ID = "app"

app_ui = ui.page_sidebar(
    ui.sidebar(
        "Add a Cash Flow Series",
        add_entry_ui(SHINY_MODULE_ID),
        width="350px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.accordion(
        ui.accordion_panel(
            "Cash Flow Series",
            view_table_ui(SHINY_MODULE_ID),
        ),
        ui.accordion_panel(
            "Cash Flow Forecast",
            forecast_ui(SHINY_MODULE_ID),
        ),
    ),
    ui.tags.footer(
        ui.a(
            ui.HTML("View Source Code on GitHub"),
            href="https://github.com/xiruizhao/cashflow-forecast",
        ),
    ),
    title="Cash Flow Forecast",
)


def server(input, output, session):
    cashflow_series: reactive.Value[pd.DataFrame] = reactive.value(
        pd.DataFrame(columns=["desc", "accounts", "dtstart", "rrule"])
    )

    @reactive.calc
    def cfs_acc_names() -> set[str]:
        return set(
            functools.reduce(
                operator.or_, cashflow_series()["accounts"].map(split_accounts), {}
            )
        )

    add_entry_server(SHINY_MODULE_ID, cashflow_series, cfs_acc_names)
    view_table_server(SHINY_MODULE_ID, cashflow_series)
    forecast_server(SHINY_MODULE_ID, cashflow_series, cfs_acc_names)


app = App(app_ui, server)
