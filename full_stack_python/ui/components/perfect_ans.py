import reflex as rx
from typing import Any, List
from typing import Any, List
from ...ui.base import base_page
from ...ui.base import base_page
from ...graider_backend.BackendManager import api
from ...graider_backend.Criterion import Criterion
from ...graider_backend.QuestionPart import QuestionPart
from ...graider_backend.RubricPart import RubricPart


class SelectState3(rx.State):
    values: list[str] = ["apple", "grape", "pear"]
    # values = [part.id for part in api.question_parts]

    value: str = "apple"
    

def perf_ans_page() -> rx.Component:
    # Welcome Page (Index)
    my_menu = rx.center(
        rx.select(
            SelectState.values,
            value=SelectState.value,
            on_change=SelectState.change_value,
            on_open_change=SelectState.refresh_ids()
        ),
        rx.badge(SelectState.value),
    )

    answer = SelectState.find_answer_by_qid(SelectState.value)

    my_answer = rx.text(
        str(answer)
    )

    my_child = rx.vstack(
        rx.heading("Reference Answers", size="9"),
        rx.box(rx.card("Questions"),
               my_menu,
               width="100%"),
        rx.divider(),
        rx.card("Perfect Answer"),
        my_answer,
        rx.button("Generate Answer from AI"),
        spacing="5",
        justify="center",
        text_align="centre",
        align="centre",
        min_height="85vh",
    )

    return base_page(my_child)
