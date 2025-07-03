import calendar

from dateutil import rrule
from shiny import ui

question_circle_fill = ui.HTML(
    '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-question-circle-fill mb-1" viewBox="0 0 16 16"><path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0zM5.496 6.033h.825c.138 0 .248-.113.266-.25.09-.656.54-1.134 1.342-1.134.686 0 1.314.343 1.314 1.168 0 .635-.374.927-.965 1.371-.673.489-1.206 1.06-1.168 1.987l.003.217a.25.25 0 0 0 .25.246h.811a.25.25 0 0 0 .25-.25v-.105c0-.718.273-.927 1.01-1.486.609-.463 1.244-.977 1.244-2.056 0-1.511-1.276-2.241-2.673-2.241-1.267 0-2.655.59-2.75 2.286a.237.237 0 0 0 .241.247zm2.325 6.443c.61 0 1.029-.394 1.029-.927 0-.552-.42-.94-1.029-.94-.584 0-1.009.388-1.009.94 0 .533.425.927 1.01.927z"/></svg>'
)

BYWEEKDAY_ORD_CHOICES = {
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
WEEKDAY_NUM_TO_ABBR_STR = [day[:2].upper() for day in calendar.day_abbr]
BYWEEKDAY_CHOICES = {day[:2].upper(): day for day in calendar.day_name}
# drop the first (0, '') from month_abbr
BYMONTH_CHOICES = dict([(str(i), val) for i, val in enumerate(calendar.month_abbr)][1:])

DEFAULT_ACC_NAMES = set(
    [
        "checking",
        "savings",
        "retirement",
        "investment",
    ]
)

RRULE_FREQ_ENUM_TO_STR = {
    rrule.DAILY: "DAILY",
    rrule.WEEKLY: "WEEKLY",
    rrule.MONTHLY: "MONTHLY",
    rrule.YEARLY: "YEARLY",
}
