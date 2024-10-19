import reflex as rx
from typing import Any, List
from ...ui.base import base_page


# class DataEditorState_HP(rx.State):

#     clicked_cell: str = "Cell clicked: "
#     edited_cell: str = "Cell edited: "
#     deleted: str = "Deleted: "

#     cols: list[Any] = [
#         {"title": "ID", "type": "int"},
#         {
#             "title": "Question",
#             "type": "str",
#             "group": "Data",
#             "width": 300,
#         },
#         {
#             "title": "Points",
#             "type": "float",
#             "group": "Data",
#             "width": 150,
#         }
#     ]

#     data = [
#         [1, "What is Python?", 5],
#         [2, "Explain OOP concepts.", 10],
#         [3, "What is a list in Python?", 5],
#         [4, "What is the use of decorators?", 8],
#         [5, "Describe exception handling in Python.", 7],
#     ]
    
#     def click_cell(self, pos):
#         col, row = pos
#         yield self.get_clicked_data(pos)

#     def get_clicked_data(self, pos) -> str:
#         self.clicked_cell = f"Cell clicked: {pos}"

#     def get_edited_data(self, pos, val) -> str:
#         col, row = pos
#         self.data[row][col] = val["data"]
#         self.edited_cell = f"Cell edited: {pos}, Cell value: {val["data"]}"

#     def get_deleted_item(self, selection):
#         self.deleted = (
#             f"Deleted cell: {selection['current']['cell']}"
#         )

# class Question(rx.Model, table=True):
#     """The question model."""

#     id: str
#     question: str
#     points: float


# class QuesTableState(rx.State):
#     questions: List[Question] = []
#     curr_question: Question = Question()

#     def load_entries(self) -> List[Question]:
#         """Get all questions from the database."""
#         with rx.session() as session:  # Assuming `rx.session()` returns an SQLAlchemy session
#             query = select(Question)  # Use the select function from SQLAlchemy
#             self.questions = session.execute(query).scalars().all()
#         return self.questions  # Optionally return the list of questions

def ques_page() -> rx.Component:
    # Welcome Page (Index)
    # my_editor = rx.data_editor(
    #     columns=DataEditorState_HP.cols,
    #     data=DataEditorState_HP.data,
    #     on_cell_clicked=DataEditorState_HP.click_cell,
    #     on_cell_edited=DataEditorState_HP.get_edited_data,
    # )

    my_child = rx.vstack(
            rx.heading("Enter your questions here", size="9"),
            # my_editor,
            rx.button("Click here to add a new question"),
            spacing="5",
            justify="center",
            text_align="center",  # Fixed typo ("centre" to "center")
            align="center",  # Fixed typo ("centre" to "center")
            min_height="85vh",
        )
    return base_page(my_child)
