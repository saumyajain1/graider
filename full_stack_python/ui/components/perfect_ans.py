import reflex as rx
from typing import Any, List
from ...ui.base import base_page
from ...ui.base import base_page
from ...graider_backend.BackendManager import api
from ...graider_backend.ReferenceAnswerPart import ReferenceAnswerPart
from ...graider_backend.QuestionPart import QuestionPart



class SelectState(rx.State):
    value: str = "apple"
    values: List[str] = []

    def refresh_ids(self):
        self.values = []
        for part in api.question_parts:
            # print(str(part.id))
            self.values.append(str(part.id))

    @staticmethod
    def find_answer_by_qid(qid: str) -> str:
        for part in api.reference_answer_parts:
            if part.qid == qid:
                return part.get_answer()
        return None  # Return None if no match is found

    def change_value(self, value: str):
        """Change the select value var."""
        self.value = value
        print(self.value)


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
