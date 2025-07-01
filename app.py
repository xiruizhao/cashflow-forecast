from add_entry import add_entry_ui, add_entry_server
from view_table import view_table_ui, view_table_server
from forecast import forecast_ui, forecast_server
from utils import split_accounts, get_cashflow_series_upload

import functools
import operator
import logging

import pandas as pd
import shiny
from shiny import App, ui, reactive, req

SHINY_MODULE_ID = "app"

# logging.basicConfig(level=logging.INFO)
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__file__)

app_ui = ui.page_sidebar(
    ui.sidebar(
        "Add/Edit a Cash Flow Series",
        add_entry_ui(SHINY_MODULE_ID),
        id="add_entry_sidebar",
        width="350px",
        open={"desktop": "open", "mobile": "closed"},
    ),
    ui.head_content(ui.tags.script(open("app.js").read())),
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
        ui.markdown("Your edits are saved in your browser and not on the server.<br>"),
        ui.a(
            "View User Guide and Source Code on GitHub",
            href="https://github.com/xiruizhao/cashflow-forecast",
        ),
    ),
    title="Cash Flow Forecast",
)


def server(input: shiny.Inputs, output: shiny.Outputs, session: shiny.Session):
    logger.info("server")
    cashflow_series: reactive.Value[pd.DataFrame | None] = reactive.value(None)

    @reactive.effect
    def load_localstorage_cfs():
        localstorage_cfs = input.localstorage_cfs()
        logger.info(
            f"load_localstorage_cfs {len(localstorage_cfs) if isinstance(localstorage_cfs, str) else None} char"
        )
        if localstorage_cfs:
            cfs = get_cashflow_series_upload(localstorage_cfs, isfilepath=False)
            if cfs is not None:
                logger.info("load_localstorage_cfs recover from previous")
                # no need to sort_cfs(cfs)
                cashflow_series.set(cfs)
                return
        logger.info("load_localstorage_cfs default init")
        cashflow_series.set(
            pd.DataFrame(columns=["desc", "accounts", "dtstart", "rrule"])
        )

    @reactive.effect
    async def set_localstorage_cfs():
        cfs = cashflow_series()
        req(cfs is not None)
        logger.info(f"set_localstorage_cfs {len(cfs)} row")
        await session.send_custom_message(
            "set_localstorage_cfs",
            cfs.to_csv(index=False),
        )

    @reactive.calc
    def cfs_acc_names() -> set[str]:
        cfs = cashflow_series()
        req(cfs is not None)
        logger.info("cfs_acc_names")
        return set(
            functools.reduce(
                operator.or_, cashflow_series()["accounts"].map(split_accounts), {}
            )
        )

    cashflow_series_table = view_table_server(
        SHINY_MODULE_ID, cashflow_series
    )
    add_entry_server(
        SHINY_MODULE_ID,
        cashflow_series,
        cfs_acc_names,
        cashflow_series_table,
        input.add_entry_sidebar,
    )
    forecast_server(SHINY_MODULE_ID, cashflow_series, cfs_acc_names)


app = App(app_ui, server)
