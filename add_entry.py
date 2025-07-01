from constants import (
    question_circle_fill,
    BYWEEKDAY_ORD_CHOICES,
    BYMONTHDAY_MONTHLY_CHOICES,
    BYMONTHDAY_YEARLY_31_CHOICES,
    BYMONTHDAY_YEARLY_30_CHOICES,
    BYMONTHDAY_YEARLY_28_CHOICES,
    BYWEEKDAY_ABBR_CHOICES,
    WEEKDAY_NUM_TO_ABBR_STR,
    BYWEEKDAY_CHOICES,
    BYMONTH_CHOICES,
    DEFAULT_ACC_NAMES,
    RRULE_FREQ_ENUM_TO_STR,
)
from utils import (
    generate_rrulestr,
    parse_rrulestr,
    validate_rrule,
    required,
    sort_cfs,
    split_accounts,
)

from datetime import date
from typing import NamedTuple
import logging

import pandas as pd
import shiny
from shiny import module, ui, render, reactive, req
from shiny_validate import InputValidator

logger = logging.getLogger(__file__)


class AccountMod(NamedTuple):
    selector: str
    input_acc_name: reactive.Value[str]
    input_acc_amt: reactive.Value[int | float | None]
    input_validator: InputValidator


@module.ui
def account_ui(
    name_label: str,
    name_choices: list[str],
    name_selected: str | None,
    amt_value: int | float,
) -> tuple[ui.Tag, str]:
    """return ui.Tag and its selector
    Need to take cfs_acc_names and acc_names as input because
    there is no other way to trigger update_acc_name when account_ui
    is first created.
    """
    logger.info(
        f"{module.resolve_id('account_ui')} {name_label} {name_choices} {name_selected} {amt_value}"
    )
    tag = ui.row(
        ui.tooltip(
            ui.input_selectize(
                "acc_name",
                name_label,
                choices=list(name_choices),
                selected=name_selected,
                width="48%",
                remove_button=True,
                options={"placeholder": "Account name", "create": True},
            ),
            "Type $TICKER to add a stock",
            placement="top",
        ),
        ui.input_numeric("acc_amt", "USD or shares", amt_value, min=0, width="48%"),
        id=module.resolve_id("account_row"),
    ).add_class("justify-content-center")
    return tag, "#" + module.resolve_id("account_row")


@module.server
def account_server(
    input: shiny.Inputs,
    output: shiny.Outputs,
    session: shiny.Session,
    cfs_acc_names: reactive.Calc_[set[str]],
    prior_accountmods: tuple[AccountMod, ...],
) -> tuple[reactive.Value[str], reactive.Value[int | float | None], InputValidator]:
    logger.info(f"{module.resolve_id('account_server')} {len(prior_accountmods)}")
    validator = InputValidator()
    validator.add_rule("acc_name", required)
    validator.add_rule("acc_amt", required)

    @reactive.calc
    def prior_acc_names() -> set[str]:
        logger.info(f"{module.resolve_id('prior_acc_names')} {len(prior_accountmods)}")
        return set(accountmod.input_acc_name() for accountmod in prior_accountmods)

    def acc_name_dedup(acc_name: str):
        """Make sure user does not submit duplicate account names."""
        logger.info(f"{module.resolve_id('acc_name_dedup')} {acc_name}")
        if acc_name in prior_acc_names():
            return "Duplicate Account Name"
        return None

    validator.add_rule("acc_name", acc_name_dedup)

    return input.acc_name, input.acc_amt, validator


def repeat_weekly_ui() -> ui.Tag:
    return ui.panel_conditional(
        "input.freq =='WEEKLY'",
        ui.input_checkbox_group(
            "byweekday_weekly",
            None,
            BYWEEKDAY_ABBR_CHOICES,
            inline=True,
        ),
    )


def repeat_monthly_ui() -> ui.Tag:
    return ui.panel_conditional(
        "input.freq == 'MONTHLY'",
        ui.input_radio_buttons(
            "onday_monthly",
            None,
            {"monthday": "on day of month", "weekday": "on day of week"},
            inline=True,
        ),
        ui.panel_conditional(
            "input.onday_monthly == 'monthday'",
            ui.input_selectize(
                "bymonthday_monthly",
                None,
                BYMONTHDAY_MONTHLY_CHOICES,
            ),
        ),
        ui.panel_conditional(
            "input.onday_monthly == 'weekday'",
            ui.row(
                ui.input_selectize(
                    "byweekday_ord_monthly",
                    None,
                    BYWEEKDAY_ORD_CHOICES,
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


def repeat_yearly_ui() -> ui.Tag:
    return ui.panel_conditional(
        "input.freq == 'YEARLY'",
        ui.input_radio_buttons(
            "onday_yearly",
            None,
            {"monthday": "on day of month", "weekday": "on day of week"},
            inline=True,
        ),
        ui.panel_conditional(
            "input.onday_yearly == 'monthday'",
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
            "input.onday_yearly == 'weekday'",
            ui.row(
                ui.input_selectize(
                    "byweekday_ord_yearly",
                    None,
                    BYWEEKDAY_ORD_CHOICES,
                    width="31%",
                ),
                ui.input_selectize(
                    "byweekday_yearly",
                    None,
                    BYWEEKDAY_ABBR_CHOICES,
                    width="31%",
                ),
                "of",
                ui.input_selectize(
                    "bymonth_byweekday_yearly",
                    None,
                    BYMONTH_CHOICES,
                    width="31%",
                ),
            ),
        ),
    )


def repeat_end_ui() -> ui.TagList:
    return ui.TagList(
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


def repeat_ui() -> ui.TagList:
    """RRULE supported by repeat_ui:
    INTERVAL, COUNT, UNTIL
    FREQ=DAILY
    FREQ=WEEKLY
        BYDAY (multiple, no ord)
    FREQ=MONTHLY
        BYDAY (one, ord=1 to 4, -2, -1)
        BYMONTHDAY(one, ord=1 to 28, -2, -1)
    FREQ=YEARLY
        BYMONTH (one)
            BYDAY (one, ord=1 to 4, -2, -1)
            BYMONTHDAY (one, ord=1 to 31 or 1 to 30 or 1 to 28)

    not supported:
    WKST, BYSETPOS, BYYEARDAY, BYWEEKNO
    """
    return ui.TagList(
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
                "!['', 'NEVER'].includes(input.freq)",
                ui.row(
                    ui.div("every", style="width:33%;"),
                    ui.input_numeric("interval", None, 1, min=1, width="33%"),
                    ui.div(
                        ui.output_text("freq_selected", inline=True), style="width:33%;"
                    ),
                ),
            ),
            repeat_weekly_ui(),
            repeat_monthly_ui(),
            repeat_yearly_ui(),
            repeat_end_ui(),
        ),
        ui.panel_conditional(
            "input.advanced_repeat",
            ui.input_text("custom_rrule", "Input RFC5545 (iCalendar) RRULE here"),
        ),
        ui.input_switch("advanced_repeat", "Advanced Repeat", False),
    )


@module.ui
def add_entry_ui() -> ui.TagList:
    logger.info(module.resolve_id("add_entry_ui"))
    return ui.TagList(
        # desc
        ui.input_text(
            "desc",
            ui.popover(
                ui.span("Description ", question_circle_fill),
                ui.markdown(
                    "`balance` is a required entry that sets the forecast start date. "
                    "`*_override`s are special entries that override entries with the same name."
                ),
            ),
            placeholder="balance",
        ),
        # accounts
        ui.row(
            ui.input_action_button("add_account_ui", "+ account", width="47%"),
            ui.input_action_button(
                "delete_account_ui", "- account", disabled=True, width="47%"
            ),
            id=module.resolve_id("insert_account_ui_anchor"),
        ).add_class("justify-content-center"),
        # dtstart
        ui.input_date("dtstart", "Start Date"),
        # rrule
        repeat_ui(),
        ui.hr(),
        ui.input_action_button("add_cashflow_series", "Submit"),
        ui.input_action_button("reset_ui", "Reset Form"),
    )


@module.server
def add_entry_server(
    input: shiny.Inputs,
    output: shiny.Outputs,
    session: shiny.Session,
    cashflow_series: reactive.Value[pd.DataFrame | None],
    cfs_acc_names: reactive.Calc_[set[str]],
    cashflow_series_table,
    add_entry_sidebar_open: reactive.Value[bool],
):
    logger.info(module.resolve_id("add_entry_server"))
    accountmods: list[AccountMod] = []

    @render.text
    def freq_selected() -> str:
        logger.info(module.resolve_id("freq_selected"))
        return {
            "": "",
            "NEVER": "",
            "DAILY": " days",
            "WEEKLY": " weeks",
            "MONTHLY": " months",
            "YEARLY": " years",
        }[input.freq()]

    @reactive.effect
    def update_bymonthday_yearly():
        req(input.freq() == "YEARLY" and input.onday_yearly() == "monthday")
        logger.info(module.resolve_id("update_bymonthday_yearly"))
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
    @reactive.event(input.add_account_ui, ignore_none=False)
    def add_account_ui():
        logger.info(module.resolve_id("add_account_ui"))
        _add_account_ui_server()

    def _add_account_ui_server(
        name_selected: str | None = None, amt_value: int | float = 0
    ):
        logger.info(
            f"{module.resolve_id('_add_account_ui_server')} {name_selected} {amt_value} {len(accountmods)}"
        )
        modid = f"account_{len(accountmods)}"
        tag, selector = account_ui(
            modid,
            name_label=f"Account {len(accountmods) + 1}",
            name_choices=sorted(list(DEFAULT_ACC_NAMES | cfs_acc_names())),
            name_selected=name_selected,
            amt_value=amt_value,
        )
        ui.insert_ui(
            tag,
            "#" + module.resolve_id("insert_account_ui_anchor"),
            where="beforeBegin",
        )
        input_acc_name, input_acc_amt, input_validator = account_server(
            modid, cfs_acc_names, tuple(accountmods)
        )  # accountmods.copy because we only want later account uis to react to earlier account uis
        accountmods.append(
            AccountMod(
                selector,
                input_acc_name,
                input_acc_amt,
                input_validator,
            )
        )
        if len(accountmods) == 2:
            ui.update_action_button("delete_account_ui", disabled=False)
        elif len(accountmods) == 8:  # max 8 accounts
            ui.update_action_button("add_account_ui", disabled=True)

    @reactive.effect
    @reactive.event(input.delete_account_ui)
    def delete_account_ui():
        logger.info(module.resolve_id("delete_account_ui"))
        ui.remove_ui(accountmods.pop().selector)
        if len(accountmods) == 1:
            ui.update_action_button("delete_account_ui", disabled=True)
        elif len(accountmods) == 7:
            ui.update_action_button("add_account_ui", disabled=False)

    @reactive.effect
    @reactive.event(input.reset_ui)
    async def reset_ui():
        logger.info(module.resolve_id("reset_ui"))
        _reset_ui()
        if cashflow_series_table.cell_selection()["rows"]:
            await cashflow_series_table.update_cell_selection(None)

    @reactive.effect
    @reactive.event(input.add_cashflow_series)
    def add_cashflow_series():
        cfs = cashflow_series()
        req(cfs is not None)
        logger.info(module.resolve_id("add_cashflow_series"))

        cfs_validator = InputValidator()
        cfs_validator.enable()
        cfs_validator.add_rule("desc", required)
        cfs_validator.add_rule("dtstart", required)
        cfs_validator.add_rule("freq", required)
        req(cfs_validator.is_valid())
        if input.advanced_repeat():
            cfs_validator.add_rule("custom_rrule", validate_rrule)
            req(cfs_validator.is_valid())
            rrule_ = input.custom_rrule()
        else:
            rrule_ = generate_rrulestr(
                validator=cfs_validator,
                freq=input.freq(),
                interval=input.interval(),
                byweekday_weekly=input.byweekday_weekly(),
                onday_monthly=input.onday_monthly(),
                byweekday_ord_monthly=input.byweekday_ord_monthly(),
                byweekday_monthly=input.byweekday_monthly(),
                bymonthday_monthly=input.bymonthday_monthly(),
                onday_yearly=input.onday_yearly(),
                byweekday_ord_yearly=input.byweekday_ord_yearly(),
                byweekday_yearly=input.byweekday_yearly(),
                bymonth_byweekday_yearly=input.bymonth_byweekday_yearly(),
                bymonth_yearly=input.bymonth_yearly(),
                bymonthday_yearly=input.bymonthday_yearly(),
                end=input.end(),
                until=input.until(),
                count=input.count(),
            )
        for accountmod in accountmods:
            accountmod.input_validator.enable()
            req(accountmod.input_validator.is_valid())
        accounts = " ".join(
            f"{accountmod.input_acc_name()}{round(accountmod.input_acc_amt(), 2):+}"
            for accountmod in accountmods
        )  # format: checking+8 savings-5

        # add entry to cashflow_series
        selected_row: tuple[int, ...] = cashflow_series_table.cell_selection()["rows"]
        if input.desc().lower() == "balance":
            logger.info(
                module.resolve_id("add_cashflow_series") + " drop previous balance"
            )
            cfs = cfs[cfs["desc"].str.lower() != "balance"]
        elif selected_row:
            # row number is index
            logger.info(
                f"{module.resolve_id('add_cashflow_series')} drop selected row {selected_row}"
            )
            cfs = cfs.drop(selected_row[0])
            # no need to update_cell_selection since table will be refreshed
        cfs = pd.concat(
            [
                cfs,
                pd.DataFrame(
                    {
                        "desc": [input.desc()],
                        "accounts": [accounts],
                        "dtstart": [input.dtstart()],
                        "rrule": [rrule_],
                    }
                ),
            ]
        )
        sort_cfs(cfs)
        cashflow_series.set(cfs)
        _reset_ui()
        cfs_validator.disable()

    def _reset_ui(create_account0: bool = True):
        logger.info(module.resolve_id("reset_ui"))
        ui.update_text("desc", value="")
        for accountmod in accountmods:
            ui.remove_ui(accountmod.selector)
        accountmods.clear()
        if create_account0:
            _add_account_ui_server()
        ui.update_action_button("delete_account_ui", disabled=True)
        ui.update_date("dtstart", value=date.today())
        ui.update_selectize("freq", selected="NEVER")
        ui.update_numeric("interval", value=1)
        ui.update_checkbox("byweekday_weekly", value=tuple())
        ui.update_radio_buttons("onday_monthly", selected="monthday")
        ui.update_selectize("bymonthday_monthly", selected="1")
        ui.update_selectize("byweekday_ord_monthly", selected="1")
        ui.update_selectize("byweekday_monthly", selected="MO")
        ui.update_radio_buttons("onday_yearly", selected="monthday")
        ui.update_selectize("bymonth_yearly", selected="1")
        ui.update_selectize("bymonthday_yearly", selected="1")
        ui.update_selectize("byweekday_ord_yearly", selected="1")
        ui.update_selectize("byweekday_yearly", selected="MO")
        ui.update_selectize("bymonth_byweekday_yearly", selected="1")
        ui.update_radio_buttons("end", selected="NEVER")
        ui.update_switch("advanced_repeat", value=False)
        ui.update_text("custom_rrule", value="")

    @reactive.effect
    @reactive.event(cashflow_series_table.cell_selection, add_entry_sidebar_open)
    def edit_row():
        cfs = cashflow_series()
        req(cfs is not None and len(cfs) > 0 and add_entry_sidebar_open())

        row_index: tuple[int, ...] = cashflow_series_table.cell_selection()["rows"]

        if not row_index:
            logger.info(module.resolve_id("edit_row") + " deselct")
            _reset_ui()
        else:
            req(len(row_index) == 1)
            logger.info(f"{module.resolve_id('edit_row')} {row_index}")
            _reset_ui(create_account0=False)
            row = cfs.iloc[row_index[0]]
            # desc
            ui.update_text("desc", value=row["desc"])
            # accounts
            for name, amt in split_accounts(row["accounts"]).items():
                logger.info(f"proceessing0 {name} {amt}")
                _add_account_ui_server(
                    name_selected=name,
                    amt_value=amt,
                )
            # dtstart
            ui.update_date("dtstart", value=row["dtstart"])
            # rrule
            if row["rrule"] == "FREQ=DAILY;COUNT=1":
                # ui.update_selectize("freq", selected="NEVER")
                return
            rrule_obj, rrule_type = parse_rrulestr(row["rrule"])
            if rrule_type == "advanced_repeat":
                ui.update_switch("advanced_repeat", value=True)
                ui.update_text("custom_rrule", value=row["rrule"])
                return
            ui.update_selectize(
                "freq", selected=RRULE_FREQ_ENUM_TO_STR[rrule_obj._freq]
            )
            ui.update_numeric("interval", value=rrule_obj._interval)
            if rrule_obj._count:
                ui.update_radio_buttons("end", selected="COUNT")
                ui.update_numeric("count", value=rrule_obj._count)
            elif rrule_obj._until:
                ui.update_radio_buttons("end", selected="UNTIL")
                ui.update_date("until", value=rrule_obj._until)
            else:
                ui.update_radio_buttons("end", selected="NEVER")

            if rrule_type == "byweekday_weekly":
                ui.update_checkbox(
                    "byweekday_weekly",
                    value=[
                        WEEKDAY_NUM_TO_ABBR_STR[day] for day in rrule_obj._byweekday
                    ],
                )
            elif rrule_type == "bymonthday_monthly":
                # ui.update_radio_buttons("onday_monthly", selected="monthly")
                monthday = (
                    str(rrule_obj._bymonthday[0])
                    if rrule_obj._bymonthday
                    else str(rrule_obj._bynmonthday[0])
                )
                ui.update_selectize("bymonthday_monthy", selected=monthday)
            elif rrule_type == "byweekday_monthly":
                ui.update_radio_buttons("onday_monthly", selected="weekday")
                ui.update_selectize(
                    "byweekday_ord_monthly",
                    selected=str(rrule_obj._bynweekday[0][1]),
                )
                ui.update_selectize(
                    "byweekday_monthly",
                    selected=WEEKDAY_NUM_TO_ABBR_STR[rrule_obj._bynweekday[0][0]],
                )
            elif rrule_type == "bymonthday_yearly":
                # ui.update_radio_buttons("onday_yearly", selected="monthday")
                ui.update_selectize(
                    "bymonth_yearly", selected=str(rrule_obj._bymonth[0])
                )
                ui.update_selectize(
                    "bymonthday_yearly", selected=str(rrule_obj._bymonthday[0])
                )
            else:  # byweekday_yearly
                ui.update_radio_buttons("onday_yearly", selected="weekday")
                ui.update_selectize(
                    "byweekday_ord_yearly",
                    selected=str(rrule_obj._bynweekday[0][1]),
                )
                ui.update_selectize(
                    "byweekday_yearly",
                    selected=WEEKDAY_NUM_TO_ABBR_STR[rrule_obj._bynweekday[0][0]],
                )
                ui.update_selectize(
                    "bymonth_byweekday_yearly",
                    selected=str(rrule_obj._bymonth[0]),
                )
