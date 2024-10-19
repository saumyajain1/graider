import reflex as rx
from ...ui.base import base_page

def ques_page() -> rx.Component:
    # Welcome Page (Index)
    my_child = rx.vstack(
            rx.heading("Enter your questions here", size="9"),
            rx.input(
                placeholder="Type your question...",  # Placeholder text for the input field
                width="80%",  # Adjust width as needed
                padding="1em",  # Optional padding for better appearance
                font_size="1.2em",  # Optional font size
            ),
            spacing="5",
            justify="center",
            text_align="center",  # Fixed typo ("centre" to "center")
            align="center",  # Fixed typo ("centre" to "center")
            min_height="85vh",
        )
    return base_page(my_child)