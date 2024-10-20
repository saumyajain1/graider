"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import reflex as rx

from .ui.base import base_page
from rxconfig import config
from .ui import components
from . import navigation

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
app.add_page(components.about_page, route=navigation.routes.ABOUT_ROUTE)
app.add_page(components.ques_page, route=navigation.routes.QUES_ROUTE)
app.add_page(components.rubric_page, route=navigation.routes.RUBRIC_ROUTE)
app.add_page(components.perf_ans_page, route=navigation.routes.PERF_ANS_ROUTE)
app.add_page(components.settings_page, route=navigation.routes.SETTINGS_ROUTE)
app.add_page(components.students_page, route=navigation.routes.STUDENTS_ROUTE)
# app.add_page(components.students_page().)
# Route for the students page (list of students)
# app.add_page(components.review_page, route='/students/ST001')
app.add_page(components.review_page, route='/students/ST001')
# app.add_page(lambda student_id: components.review_page(student_id), route='/students/{student_id}')
# Instantiate ReviewPage and add it to the route
# review_page_instance = components.ReviewPage()
# app.add_page(review_page_instance, route='/students/{student_id}')
# Dynamic route for reviewing a student's submission
# app.add_page(lambda student_id: components.review_page(student_id), route='/review/{student_id}')

