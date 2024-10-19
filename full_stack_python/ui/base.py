import reflex as rx
from .side import sidebar

def base_page(child: rx.Component, *args, **kwargs) -> rx.Component:
    return rx.fragment(
        rx.hstack(
            sidebar(),
            rx.center(  # This will center the content within the available space
                rx.box(
                    child,
                    *args,
                    rx.logo(),
                    # bg=rx.color("accent", 3),
                    padding="1em",
                    max_width="100%",  # Optional: Set a max width to keep it responsive
                    text_align="center",  # Center the text content
                ),
                width="100%",  # Allow it to take the remaining width
                justify="center",  # Center it horizontally
                align="center",  # Center it vertically
                min_height="85vh",  # Adjust to fill the available space
            ),
        ),
        rx.color_mode.button(position="top-right"),
    )