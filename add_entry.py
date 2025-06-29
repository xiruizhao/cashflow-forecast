from constants import (
    question_circle_fill,
    BYSETPOS_CHOICES,
    BYMONTHDAY_MONTHLY_CHOICES,
    BYMONTHDAY_YEARLY_31_CHOICES,
    BYMONTHDAY_YEARLY_30_CHOICES,
    BYMONTHDAY_YEARLY_28_CHOICES,
    BYWEEKDAY_ABBR_CHOICES,
    BYWEEKDAY_CHOICES,
    BYMONTH_CHOICES,
    DEFAULT_ACC_NAMES,
)
from utils import generate_rrule, validate_rrule, required, sort_cfs

from datetime import date
from typing import NamedTuple

import pandas as pd
from shiny import module, ui, render, reactive, req
from shiny_validate import InputValidator


class AccountMod(NamedTuple):
    selector: str
    input_acc_name: reactive.Value[str]
    input_acc_amt: reactive.Value[int | float | None]
    input_validator: InputValidator


@module.ui
def account_ui(
    labelnum: int, cfs_acc_names: set[str], acc_names: set[str]
) -> tuple[ui.Tag, str]:
    """return ui.Tag and its selector
    Need to take cfs_acc_names and acc_names as input because
    there is no other way to trigger update_acc_name when account_ui
    is first created.
    """
    tag = ui.row(
        ui.tooltip(
            ui.input_selectize(
                "acc_name",
                f"Account {labelnum}",
                choices=sorted(list((DEFAULT_ACC_NAMES | cfs_acc_names) - acc_names)),
                width="50%",
                remove_button=True,
                options={"placeholder": "Account name", "create": True},
            ),
            "Type $TICKER to add a stock",
            placement="top",
        ),
        ui.input_numeric("acc_amt", f"Amount {labelnum}", 0, min=0, width="50%"),
        id=module.resolve_id("account_row"),
    )
    return tag, "#" + module.resolve_id("account_row")


@module.server
def account_server(
    input,
    output,
    session,
    cfs_acc_names: reactive.Value[set[str]],
    accountmods: list[AccountMod],
) -> tuple[reactive.Value[str], reactive.Value[int | float | None], InputValidator]:
    validator = InputValidator()
    validator.add_rule("acc_name", required)
    validator.add_rule("acc_amt", required)

    @reactive.calc
    def prior_acc_names() -> set[str]:
        return set(accountmod.input_acc_name() for accountmod in accountmods)

    def acc_name_dedup(acc_name: str):
        """Still need this dedup check because the user
        could manually type duplicate names."""
        if acc_name in prior_acc_names():
            return "Duplicate Account Name"
        return None

    validator.add_rule("acc_name", acc_name_dedup)

    @reactive.effect
    def update_acc_amt():
        ui.update_numeric(
            "acc_amt",
            label="Amount in shares"
            if input.account().startswith("$")
            else "Amount in USD",
        )

    @reactive.effect
    def update_acc_name():
        ui.update_selectize(
            "acc_name",
            choices=sorted(
                list(
                    (DEFAULT_ACC_NAMES | cfs_acc_names())
                    - set(accountmod.input_acc_name() for accountmod in accountmods)
                )
            ),
        )

    return input.acc_name, input.acc_amt, validator


def repeat_weekly_ui() -> ui.TagList:
    return ui.panel_conditional(
        "input.freq =='WEEKLY'",
        ui.input_checkbox_group(
            "byweekday_weekly",
            None,
            BYWEEKDAY_ABBR_CHOICES,
            inline=True,
        ),
    )


def repeat_monthly_ui() -> ui.TagList:
    return ui.panel_conditional(
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


def repeat_yearly_ui() -> ui.TagList:
    return ui.panel_conditional(
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
                "[ 'DAILY', 'WEEKLY', 'MONTHLY', 'YEARLY' ].includes( input.freq )",
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
            ui.input_action_button("add_account_ui", "+ account", width="50%"),
            ui.input_action_button(
                "delete_account_ui", "- account", disabled=True, width="50%"
            ),
            id=module.resolve_id("insert_account_ui_anchor"),
        ),
        # dtstart
        ui.input_date("dtstart", "Start Date"),
        # rrule
        repeat_ui(),
        ui.hr(),
        ui.input_action_button("add_cashflow_series", "Submit"),
    )


@module.server
def add_entry_server(
    input,
    output,
    session,
    cashflow_series: reactive.Value[pd.DataFrame],
    cfs_acc_names: reactive.Value[set[str]],
):
    accountmods: list[AccountMod] = []

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
    @reactive.event(input.add_account_ui, ignore_none=False)
    def add_account_ui():
        modid = f"account_{input.add_account_ui()}"
        tag, selector = account_ui(
            modid,
            len(accountmods) + 1,
            cfs_acc_names(),
            set([accountmod.input_acc_name() for accountmod in accountmods]),
        )
        ui.insert_ui(
            tag,
            "#" + module.resolve_id("insert_account_ui_anchor"),
            where="beforeBegin",
        )
        input_acc_name, input_acc_amt, input_validator = account_server(
            modid, cfs_acc_names, accountmods.copy()
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
        selector, _, _, _ = accountmods.pop()
        ui.remove_ui(selector)
        if len(accountmods) == 1:
            ui.update_action_button("delete_account_ui", disabled=True)
        elif len(accountmods) == 7:
            ui.update_action_button("add_account_ui", disabled=False)

    @reactive.effect
    @reactive.event(input.add_cashflow_series)
    def add_cashflow_series():
        cfs_validator = InputValidator()
        cfs_validator.enable()
        cfs_validator.add_rule("desc", required)
        cfs_validator.add_rule("dtstart", required)
        cfs_validator.add_rule("freq", required)
        req(cfs_validator.is_valid())
        if input.advanced_repeat():
            cfs_validator.add_rule("custom_rrule", validate_rrule)
            req(cfs_validator.is_valid())
            RRULE = input.custom_rrule()
        else:
            RRULE = generate_rrule(
                cfs_validator,
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
        for accountmod in accountmods:
            accountmod.input_validator.enable()
            req(accountmod.input_validator.is_valid())
        accounts = " ".join(
            f"{accountmod.input_acc_name()}{round(accountmod.input_acc_amt(), 2):+}"
            for accountmod in accountmods
        )  # format: checking+8 savings-5

        # add entry to cashflow_series
        cfs = cashflow_series()
        if input.desc().lower() == "balance":
            # drop previous balance
            cfs = cfs[cfs["desc"].str.lower() != "balance"]
        cfs = pd.concat(
            [
                cfs,
                pd.DataFrame(
                    {
                        "desc": [input.desc()],
                        "accounts": [accounts],
                        "dtstart": [input.dtstart()],
                        "rrule": [RRULE],
                    }
                ),
            ]
        )
        sort_cfs(cfs)
        cashflow_series.set(cfs)
        # reset ui
        ui.update_text("desc", value="")
        ui.update_selectize("account1", selected="checking")
        ui.update_numeric("amount1", value=0)
        for accountmod in accountmods:
            ui.remove_ui(accountmod.selector)
        accountmods.clear()
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
