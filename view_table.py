from utils import (
    get_cashflow_series_upload,
    split_accounts,
    validate_rrule,
    sort_cfs,
)

from datetime import date
import logging
from typing import Callable

import pandas as pd
import shiny
from shiny import module, ui, render, reactive, req
from shiny.types import FileInfo

logger = logging.getLogger(__file__)


def add_onclick(tag: ui.Tag, onclick: str) -> ui.Tag:
    tag.attrs["onclick"] = onclick
    return tag


@module.ui
def view_table_ui() -> ui.TagList:
    logger.info(module.resolve_id("view_table_ui"))
    return ui.TagList(
        ui.output_data_frame("cashflow_series_table"),
        ui.help_text("Hold CMD/CTRL and click to deselect a row"),
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
            add_onclick(
                ui.input_action_button(
                    "download_cashflow_series",
                    "Download",
                    width="200px",
                ),
                "downloadDataAsCsv()",
            ),
            add_onclick(
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
        ),
    )


@module.server
def view_table_server(
    input: shiny.Inputs,
    output: shiny.Outputs,
    session: shiny.Session,
    cashflow_series: reactive.Value[pd.DataFrame | None],
) -> render.data_frame[pd.DataFrame]:
    logger.info(module.resolve_id("view_table_server"))
    invalid_upload = ui.modal(
        ui.markdown(
            """The file should be a csv file with columns `desc`, `accounts`, `dtstart`, `rrule`<br>
        `desc` is a nonempty string (there should be exactly one entry whose `desc` is `balance`)<br>
        `accounts` is formatted like `paycheck+8 savings-5 $GOOG+8` (account name cannot be "desc", "accounts", "activity", "date", or "sum") <br>
        `dtstart` is formatted like "2025-12-31"<br>
        `rrule` is an RFC5545 (iCalendar) RRULE except SECONDLY, MINUTELY, HOURLY repeats are not allowed"""
        ),
        title="Error: file has incorrect format",
        easy_close=True,
        footer=None,
    )

    @render.ui
    def load_example_csv_ui():
        cfs = cashflow_series()
        req(cfs is not None and len(cfs) == 0)
        logger.info(module.resolve_id("load_example_csv_ui"))
        return ui.input_action_button(
            "load_example_csv", "Load example.csv", width="200px"
        )

    @reactive.effect
    @reactive.event(input.load_example_csv)
    def load_example_csv():
        logger.info(module.resolve_id("load_example_csv"))
        cfs = get_cashflow_series_upload("example.csv")
        assert cfs is not None
        sort_cfs(cfs)
        cashflow_series.set(cfs)

    @render.data_frame
    def cashflow_series_table():
        cfs = cashflow_series()
        req(cfs is not None)
        assert cfs is not None  # to please the type checker
        logger.info(module.resolve_id("cashflow_series_table"))
        return render.DataGrid(cfs, editable=True, selection_mode="row")

    @cashflow_series_table.set_patch_fn
    def edit_cell(*, patch: render.CellPatch):
        cfs = cashflow_series()
        req(cfs is not None and len(cfs) > 0)
        assert cfs is not None  # to please the type checker
        logger.info(f"{module.resolve_id('edit_cell')} {patch}")
        cfs = cfs.copy()
        orig_value = cfs.iat[patch["row_index"], patch["column_index"]]
        assert isinstance(patch["value"], str)  # to please the type checker
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

    # previous download_button reactor:
    # @render.download(filename=f"cashflow_series_{date.today().isoformat()}.csv")
    # def download_cashflow_series():
    #    cfs = cashflow_series()
    #    req(cfs is not None)
    #    logger.info(module.resolve_id("download_cashflow_series"))
    #    yield cfs.to_csv(index=False)

    @reactive.effect
    @reactive.event(input.delete_all_cashflow_series)
    def delete_all_cashflow_series():
        cfs = cashflow_series()
        req(cfs is not None and len(cfs) > 0)
        assert cfs is not None  # to please the type checker
        logger.info(module.resolve_id("delete_all_cashflow_series"))
        cashflow_series.set(cfs[0:0])

    @reactive.effect
    @reactive.event(input.delete_cashflow_series)
    def delete_cashflow_series():
        cfs = cashflow_series()
        cfs_rows = cashflow_series_table.cell_selection()["rows"]
        assert isinstance(cfs_rows, tuple) # tuple[int, ...]
        req(cfs is not None and len(cfs) > 0 and len(cfs_rows) > 0)
        assert cfs is not None  # to please the type checker
        logger.info(f"{module.resolve_id('delete_cashflow_series')} {cfs_rows}")
        cfs = cfs.drop(index=list(cfs_rows))  # create a copy
        sort_cfs(cfs)
        cashflow_series.set(cfs)

    @reactive.effect
    @reactive.event(input.upload_cashflow_series)
    def upload_cashflow_series():
        file: list[FileInfo] | None = input.upload_cashflow_series()
        req(file is not None)
        assert file is not None  # to please the type checker
        logger.info(module.resolve_id("upload_cashflow_series"))
        cfs = get_cashflow_series_upload(file[0]["datapath"])
        if cfs is not None:
            sort_cfs(cfs)
            cashflow_series.set(cfs)
        else:
            ui.modal_show(invalid_upload)

    return cashflow_series_table  # edit via UI
