# Cash Flow Forecast

Short URL: xirui.me/cf

Full URL: https://xiruizhao-cf.share.connect.posit.cloud

## Use case

1.  Based on my income and expenses, when will I become a millionaire?
2.  Will my checking account be overdrawn next month, given the paycheck deposits and credit card withdrawals?

## User guide

1.  You can add these types of cash flows:
    1.  Recurring cash flows (a "cash flow series") such as paychecks, rent payments, credit card bills
    2.  One time cash flow such as an expected future expense
    3.  RSUs vesting
    4.  One time override whose name ends with `_override`, which overrides the cash flow with the same name
    5.  `balance` is a special entry. You can only have one `balance` entry and it sets the starting balance and forecast start date. Events prior to the forecast start date are ignored.
2.  Data storage and privacy
    1.  Your user data is saved in the [browser](https://en.wikipedia.org/wiki/Web_storage), so they should persist across sessions on the same browser.
    2.  You can export your data to another browser via `Copy Data as URL`. If your data is too big, you'll have to download it as a csv file and upload it in another browser.
    3.  Click a row to edit it on the sidebar or directly edit it in the table.
    4.  Your data is sent to the server for processing, but they are only accessed in memory and not saved to databases or files. When you close your browser window, nothing is preserved on the server.


### Caveats

Inflation rate, interest rate and investment yield are ignored.

## Technical

`cashflow_series.csv` format:

1.  columns: `desc`, `accounts`, `dtstart` and `rrule`
2.  `desc` must be nonempty
3.  `account` is like `checking+8 savings-16 $GOOG+5` (note that the unit for stocks is shares instead of USD)
4.  `dtstart` is the first occurrence date of the recurring series formatted like `2025-06-24`. The first date can be earlier than the forecast start date and events prior to the forecast start date are simply ignored. You only need to update the `dtstart` and `accounts` for the `balance` entry periodically to reflect your current balance.
5.  `rrule` is an RFC 5545 (iCalendar) RRULE specifying recurrent events.

Built with [Shiny for Python](https://shiny.posit.co/py/). Hosted on [Posit Connect Cloud](https://connect.posit.cloud)

### Server Processing of Cash Flow Series

1.  `rrule` column is expanded into a `date` column based on forecast start date (the start date of `balance`), `rrule` start date (first recurring event date), and forecast end date
2.  entries whose `desc` ends in `_override` will replace entries with the same `desc` and same `date`
3.  `accounts` column is expanded into columns for each account name.
4.  entries are ordered by `date` and `cumsum`ed. entries with duplicate `date`s are removed except the last entry.
5.  stock shares are converted to USD based on the last day close price.

### TODO

1.  Parse bank app screenshots to update `balance` and `*_override` https://github.com/tesseract-ocr
2.  [Shinylive](https://shiny.posit.co/py/get-started/shinylive.html) allows the python server to run completely in the browser, but yfinance/curl-cffi/quantmod are not available.
3.  More tests.