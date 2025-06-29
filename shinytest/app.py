from urllib.parse import urlparse
from shiny import *

app_ui = ui.page_fluid(
    ui.output_text_verbatim("out"),
)


def server(input, output, session):
    @output()
    @render.text
    def out():
        #breakpoint()
        return (
            session.input[".clientdata_url_search"]()
            + "\n"
            + session.input[".clientdata_url_hash"]()
            + "\n"
            + session.input[".clientdata_url_hash_initial"]()
        )


app = App(app_ui, server)
