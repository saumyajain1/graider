"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import reflex as rx

from .ui.base import base_page
from rxconfig import config
from .ui import components


class State(rx.State):
    """The app state."""

    ...

def index() -> rx.Component:
    # Welcome Page (Index)
    my_child = rx.vstack(
            rx.heading("Welcome to Reflex!", size="9"),
            rx.text(
                "Get started by editing ",
                rx.code(f"{config.app_name}/{config.app_name}.py"),
                size="5",
            ),
            rx.link(
                rx.button("Check out our docs!"),
                href="https://reflex.dev/docs/getting-started/introduction/",
                is_external=True,
            ),
            spacing="5",
            justify="center",
            text_align="centre",
            align="centre",
            min_height="85vh",
        )
    return base_page(my_child)


app = rx.App()
app.add_page(index)
app.add_page(components.about_page, route='/about')
app.add_page(components.ques_page, route='/questions')
