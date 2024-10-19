import reflex as rx
from .. import navigation

def sidebar_item(
    text: str, icon: str, href: str
) -> rx.Component:
    return rx.link(
        rx.hstack(
            rx.icon(icon),
            rx.text(text, size="4"),
            width="100%",
            padding_x="0.5rem",
            padding_y="0.75rem",
            align="center",
            style={
                "_hover": {
                    "bg": rx.color("accent", 4),
                    "color": rx.color("accent", 11),
                },
                "border-radius": "0.5em",
            },
        ),
        href=href,
        underline="none",
        weight="medium",
        width="100%",
    )


def sidebar_items() -> rx.Component:
    return rx.vstack(
        sidebar_item("Questions", "layout-dashboard", navigation.routes.ABOUT_ROUTE),
        sidebar_item("Rubric", "square-library", navigation.routes.RUBRIC_ROUTE),
        sidebar_item("Perfect Answer", "bar-chart-4", navigation.routes.PERF_ANS_ROUTE),
        sidebar_item("Grade Settings", "mail", navigation.routes.SETTINGS_ROUTE),
        sidebar_item("Students", "mail", navigation.routes.STUDENTS_ROUTE),
        spacing="1",
        width="100%",
    )


def sidebar() -> rx.Component:
    return rx.box(
        rx.desktop_only(
            rx.vstack(
                rx.hstack(
                    # rx.image(
                    #     src="/logo.jpg",
                    #     width="2.25em",
                    #     height="auto",
                    #     border_radius="25%",
                    # ),
                    rx.heading(
                        "graider",
                        size="7",
                        weight="bold",
                        on_click=lambda: rx.redirect("/about"),  # Use rx.redirect to navigate
                        cursor="pointer",  # Change cursor to pointer for better UX
                    ),
                    align="center",
                    justify="start",
                    padding_x="0.5rem",
                    width="100%",
                ),
                sidebar_items(),
                spacing="5",
                # position="fixed",
                left="0px",
                # top="0px",
                # z_index="5",
                padding_x="1em",
                padding_y="1.5em",
                bg=rx.color("accent", 3),
                align="start",
                height="120vh",
                # height="650px",
                width="16em",
            ),
        ),
        rx.mobile_and_tablet(
            rx.drawer.root(
                rx.drawer.trigger(
                    rx.icon("align-justify", size=30)
                ),
                rx.drawer.overlay(z_index="5"),
                rx.drawer.portal(
                    rx.drawer.content(
                        rx.vstack(
                            rx.box(
                                rx.drawer.close(
                                    rx.icon("x", size=30)
                                ),
                                width="100%",
                            ),
                            sidebar_items(),
                            spacing="5",
                            width="100%",
                        ),
                        top="auto",
                        right="auto",
                        height="100vh",
                        width="20em",
                        padding="1.5em",
                        bg=rx.color("accent", 2),
                    ),
                    width="100%",
                ),
                direction="left",
            ),
            padding="1em",
        ),
    )
