from playwright.sync_api import Page

from shiny.playwright import controller
from shiny.pytest import create_app_fixture
from shiny.run import ShinyAppProc

app = create_app_fixture("./app.py")


def test_app(page: Page, app: ShinyAppProc):

    page.goto(app.url)
    upload = controller.InputFile(page, "upload_cashflow_series")
    #set_localstorage_cfs = controller.OutputUi(page, "set_localstorage_cfs")
    #upload.set("example.csv")
    #upload.expect_complete(5)
    #set_localstorage_cfs.expect("")
    # Add test code here
