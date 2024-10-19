import reflex as rx
from ...ui.base import base_page


def settings_page() -> rx.Component:
    # Welcome Page (Index)
    my_child = rx.vstack(
        rx.heading("Settings", size="9"),
        spacing="5",
        justify="center",
        text_align="centre",
        align="centre",
        min_height="85vh",
    )
    return base_page(my_child)
