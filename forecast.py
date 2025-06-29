from utils import get_stock_price, required, generate_forecast

from datetime import date, datetime
from io import StringIO
import logging

from dateutil.relativedelta import relativedelta
import humanize
import pandas as pd
import quantmod.charts  # noqa: F401
from shiny import module, ui, render, reactive, req
from shiny_validate import InputValidator

logger = logging.getLogger("cashflow")


@module.ui
def stock_price_ui() -> ui.Tag:
    symbol = module.current_namespace().split("-")[-1]
    return ui.input_numeric(
        "stock_price",
        label=f"Set ${symbol} Price (default to last close)",
        value=get_stock_price(symbol),
        min=0,
    )


@module.server
def stock_price_server(
    input, output, session
) -> tuple[reactive.Value[int | float | None], InputValidator]:
    validator = InputValidator()
    validator.add_rule("stock_price", required)

    return input.stock_price, validator


@module.ui
def forecast_ui() -> ui.TagList:
    return ui.TagList(
        ui.row(
            ui.output_ui("show_forecast_dtstart"),
            ui.input_date(
                "forecast_dtend",
                "Forecast End Date",
                value=date.today() + relativedelta(years=2),
                startview="year",
                width="300px",
            ),
            ui.input_switch("forecast_graph", "Graph", width="100px"),
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
        ui.output_ui(id="set_stock_price_ui"),
    )


@module.server
def forecast_server(
    input,
    output,
    session,
    cashflow_series: reactive.Value[pd.DataFrame],
    cfs_acc_names: reactive.Value[set[str]],
):
    stock_price_inputs: reactive.Value[
        dict[str, tuple[reactive.Value[int | float | None], InputValidator]]
    ] = reactive.value(dict())  # {symbol: (input, validator)}
    # we need stock_prices as a reactive.value to mediate cashflow_forecast's
    # dependency on all input.stock_price

    @render.ui
    def set_stock_price_ui() -> ui.TagList:
        ret = ui.TagList()
        price_inputs = {}
        for acc_name in cfs_acc_names():
            if acc_name.startswith("$"):
                symbol = acc_name[1:]
                if not symbol.isalpha():
                    continue
                ret.append(stock_price_ui(symbol))
                price_inputs[symbol] = stock_price_server(symbol)
        stock_price_inputs.set(price_inputs)
        return ret

    @reactive.calc
    def forecast_dtstart() -> pd.Series:
        # use iloc[0] to get dtstart
        cfs = cashflow_series()
        return cfs[cfs["desc"] == "balance"]["dtstart"]

    @render.ui
    def show_forecast_dtstart() -> ui.Tag:
        dtstart = forecast_dtstart()
        if len(dtstart) == 0:
            return ui.markdown("Forecast Start Date:<br>Please add a `balance` entry")
        return ui.markdown(
            "Forecast Start Date:<br>"
            + dtstart.iloc[0].isoformat()
            + " "
            + humanize.naturaltime(
                datetime.fromordinal(dtstart.iloc[0].toordinal()),
                when=datetime.fromordinal(date.today().toordinal()),
            )
        )

    @reactive.calc
    def cashflow_forecast() -> pd.DataFrame:
        cfs = cashflow_series().copy()
        req(len(cfs) != 0 and len(forecast_dtstart()) == 1)
        after = datetime.fromordinal(forecast_dtstart().iloc[0].toordinal())
        before = datetime.fromordinal(input.forecast_dtend().toordinal())
        cfs = generate_forecast(cfs, after, before)
        price_inputs = stock_price_inputs()
        # 5. convert stock shares to prices
        for column in cfs:
            if column.startswith("$"):
                price_input, validator = price_inputs[column[1:]]
                validator.enable()
                req(validator.is_valid())
                cfs[column] = (cfs[column] * price_input()).round(2)
        return cfs

    @render.data_frame
    def cashflow_forecast_table() -> render.DataGrid:
        return render.DataGrid(cashflow_forecast())

    # @render_plotly clips the graph
    @render.ui
    def cashflow_forecast_graph() -> ui.HTML:
        df = cashflow_forecast()
        f = StringIO()
        df.drop("desc", axis=1).set_index("date").iplot(kind="overlay").write_html(f)
        return ui.HTML(f.getvalue())
