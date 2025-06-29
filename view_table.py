from utils import (
    get_cashflow_series_upload,
    split_accounts,
    validate_rrule,
    sort_cfs,
)

from datetime import date
import logging
import urllib

import jinja2
import pandas as pd
from shiny import module, ui, render, reactive
from shiny.types import FileInfo

logger = logging.getLogger("cashflow")

# https://github.com/posit-dev/py-shiny/blob/d656fdb213ea5e48bb54f6627445627e6e49f4b6/shiny/api-examples/session_send_custom_message/app-core.py#L4
get_set_localstorage = jinja2.Template(
    """
// handle data encoded in URL search params
const params = new URLSearchParams(window.location.search);
if (cfs = params.get("cfs")) {
    localStorage.setItem("cashFlowSeries", cfs);
    console.log("set localstorage from url search " + cfs);
    window.location = window.location.origin;
}
function copyDataAsUrl() {
    if (cfs = localStorage.getItem("cashFlowSeries")) {
        const params = new URLSearchParams({cfs: cfs});
        console.log("copyDataAsUrl called with " + params.toString());
        if (params.toString().length <= 1900) {
            navigator.clipboard.writeText(window.location.origin + "/?" + params.toString());
        }
    }
}
Shiny.initializedPromise.then(() => {
    if (cfs = localStorage.getItem("cashFlowSeries")) {
        Shiny.setInputValue("{{inputid}}", cfs);
    }
    Shiny.addCustomMessageHandler("set_localstorage_cfs", function(message) {
        localStorage.setItem("cashFlowSeries", message);
        console.log("set_localstorage_cfs with " + message);
    });
});
"""
)


def set_onclick(tag: ui.Tag, js: str) -> ui.Tag:
    tag.attrs["onclick"] = js
    return tag


@module.ui
def view_table_ui() -> ui.TagList:
    return ui.TagList(
        ui.tags.script(
            get_set_localstorage.render(inputid=module.resolve_id("localstorage_cfs"))
        ),
        ui.output_data_frame("show_cashflow_series"),
        ui.row(
            ui.input_action_button(
                "delete_cashflow_series",
                "Delete Selected",
                width="200px",
            ),
            ui.input_action_button(
                "delete_all_cashflow_series",
                "Delete All",
                width="200px",
            ),
            ui.download_button(
                "download_cashflow_series",
                "Download",
                width="200px",
            ),
            set_onclick(
                ui.input_action_button(
                    "copy_data_as_url",
                    "Copy Data as URL",
                    width="200px",
                ),
                "copyDataAsUrl()",
            ),
            ui.output_ui("load_example_csv_ui"),
        ),
        ui.p(),
        ui.input_file(  # need to be on a seperate block because its height is larger
            "upload_cashflow_series",
            None,
            button_label="Upload",
            accept=[".csv"],
            # width="750px",
        ).add_class("col-auto"),
    )


@module.server
def view_table_server(
    input, output, session, cashflow_series: reactive.Value[pd.DataFrame]
) -> render.DataGrid:
    invalid_upload = ui.modal(
        ui.markdown("""The file should be a csv file with columns `desc`, `accounts`, `dtstart`, `rrule`<br>
        `desc` is a nonempty string (there should be exactly one entry whose `desc` is `balance`)<br>
        `accounts` is formatted like `paycheck+8 savings-5 $GOOG+8`<br>
        `dtstart` is formatted like "2025-12-31"<br>
        `rrule` is a RFC5445 (iCalendar) RRULE"""),
        title="Error: file has incorrect format",
        easy_close=True,
        footer=None,
    )

    @render.ui
    def load_example_csv_ui():
        if len(cashflow_series()) == 0:
            return ui.input_action_button(
                "load_example_csv", "Load example.csv", width="200px"
            )
        return None

    @reactive.effect
    @reactive.event(input.load_example_csv)
    def load_example_csv():
        cfs = get_cashflow_series_upload("example.csv")
        sort_cfs(cfs)
        cashflow_series.set(cfs)

    @reactive.effect
    def load_localstorage_cfs():
        # fired once
        localstorage_cfs = input.localstorage_cfs()
        logger.info(f"load_localstorage_cfs {len(localstorage_cfs)} char")
        if localstorage_cfs:
            cfs = get_cashflow_series_upload(localstorage_cfs, isfilepath=False)
            if cfs is not None:
                logger.info("load_localstorage_cfs recover from previous")
                # no need to sort_cfs(cfs)
                cashflow_series.set(cfs)
                return

    @reactive.effect
    async def set_localstorage_cfs():
        # set_localstorage_cfs is fired for the initial value of cashflow_series()
        # but this shouldn't affect load_localstorage_cfs because
        # input.localstorage_cfs is set before the CustomMessageHandler for
        # set_localstorage_cfs is added
        cfs = cashflow_series()
        logger.info(f"set_localstorage_cfs {len(cfs)} row")
        await session.send_custom_message(
            "set_localstorage_cfs",
            cfs.to_csv(index=False),
        )

    @render.data_frame
    def show_cashflow_series():
        # TODO edit via UI
        return render.DataGrid(cashflow_series(), editable=True, selection_mode="row")

    @show_cashflow_series.set_patch_fn
    def _(*, patch: render.CellPatch):
        cfs = cashflow_series().copy()
        orig_value = cfs.iat[patch["row_index"], patch["column_index"]]
        if patch["column_index"] == 0:  # desc
            if len(patch["value"]) > 0:
                cfs.iat[patch["row_index"], 0] = patch["value"]
                sort_cfs(cfs)
                cashflow_series.set(cfs)
            else:
                ui.notification_show(
                    ui.markdown("`desc` must not be empty"), type="error"
                )
                return orig_value
        elif patch["column_index"] == 1:  # accounts
            accs = split_accounts(patch["value"])
            if accs:
                cfs.iat[patch["row_index"], 1] = " ".join(
                    f"{name}{amt:+}" for name, amt in accs.items()
                )
                cashflow_series.set(cfs)
            else:
                ui.notification_show(
                    ui.markdown(
                        "`accounts` must be formatted like `paycheck+8 savings-5 $GOOG+8`"
                    ),
                    type="error",
                )
                return orig_value
        elif patch["column_index"] == 2:  # dtstart
            try:
                cfs.iat[patch["row_index"], 2] = date.fromisoformat(patch["value"])
                cashflow_series.set(cfs)
            except ValueError:
                ui.notification_show(
                    ui.markdown('`dtstart` must be formatted like "2025-12-31"'),
                    type="error",
                )
                return orig_value
        else:  # rrule
            if validate_rrule(patch["value"]) is None:
                cfs.iat[patch["row_index"], 3] = patch["value"]
                cashflow_series.set(cfs)
            else:
                ui.notification_show(
                    ui.markdown("`rrule` must be a RFC5545 (iCalendar) RRULE"),
                    type="error",
                )
                return orig_value
        return patch["value"]  # since we reset cashflow_series, return as is

    @render.download(filename=f"cashflow_series_{date.today().isoformat()}.csv")
    def download_cashflow_series():
        yield cashflow_series().to_csv(index=False)
        """
        // alternative client side js:
        if (cfs = localStorage.getItem("cashFlowSeries")) {
            const elem = window.document.createElement('a');
            elem.href = URL.createObjectURL(new Blob([cfs], {type: 'text/csv', oneTimeOnly: true}));
            elem.download = 'cashflow_series.csv';
            elem.display = 'none';
            document.body.appendChild(elem);
            elem.click();
            document.body.removeChild(elem);
        }
        """

    @reactive.effect
    @reactive.event(input.copy_data_as_url)
    def copy_data_as_url():
        message = urllib.parse.quote(cashflow_series().to_csv(index=False))
        logger.info(f"copy_data_as_url {len(message)}")
        if len(message) >= 1900:
            ui.notification_show(
                "Your data is too big to be encoded in URL. Please download as a csv file."
            )
        # javascript handles copying to clipboard

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
            cfs.drop(list(cfs_rows))
            sort_cfs(cfs)
            cashflow_series.set(cfs)

    @reactive.effect
    @reactive.event(input.upload_cashflow_series)
    def upload_cashflow_series():
        file: list[FileInfo] | None = input.upload_cashflow_series()
        if file is None:
            return
        cfs = get_cashflow_series_upload(file[0]["datapath"])
        if cfs is not None:
            sort_cfs(cfs)
            cashflow_series.set(cfs)
        else:
            ui.modal_show(invalid_upload)

    return show_cashflow_series  # TODO edit via UI
