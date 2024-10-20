import copy
import reflex as rx
from typing import Any, List
from ...ui.base import base_page
from ...graider_backend.BackendManager import api
from ...graider_backend.QuestionPart import QuestionPart

def print_question_parts():
    """Print each QuestionPart object in api.question_parts."""
    print("\n")
    for question_part in api.question_parts:
        print(f"ID: {question_part.id}, Question: {question_part.text}, Points: {question_part.marks}")
    print("\n")


class DataEditorState_HP(rx.State):
    
    clicked_cell: str = "Cell clicked: "
    edited_cell: str = "Cell edited: "
    deleted: str = "Deleted: "

    cols: list[Any] = [
        {"title": "ID", "type": "int"},
        {
            "title": "Question",
            "type": "str",
            "group": "Data",
            "width": 300,
        },
        {
            "title": "Points",
            "type": "float",
            "group": "Data",
            "width": 150,
        }
    ]

    # Use a state variable for data so Reflex tracks it
    # data: list[List[Any]] = [
    #     [1, "What is Python?", 5],
    #     [2, "Explain OOP concepts.", 10],
    #     [3, "What is a list in Python?", 5],
    #     [4, "What is the use of decorators?", 8],
    #     [5, "Describe exception handling in Python.", 7],
    # ]

    data: list[List[Any]] = []

    def populate_data(self, question_parts: List[QuestionPart]) -> None:
        """Populate DataEditorState_HP with a list of QuestionPart objects."""
        self.data: list[List[Any]] = []

        if (question_parts != None): 
          for question in question_parts:
            # Append a row with [ID, Question Text, Points]
            self.data.append(QuestionPart(question["id"], question["text"], question["marks"]))  
    
    @rx.var
    def actual_data(self) -> list[list]:
        return [[question.id, question.text, question.marks] for question in self.data]

    def refresh_table(self):
        """Refresh the table by populating data from the current question parts in the API."""
        # self.populate_data(copy.deepcopy(api.question_parts))

        self.data: list[List[Any]] = []

        if (api.question_parts != None): 
          for question in api.question_parts:
            # Append a row with [ID, Question Text, Points]
            self.data.append(QuestionPart(question.id, question.text, question.marks)) 

    def click_cell(self, pos):
        col, row = pos
        yield self.get_clicked_data(pos)

    def get_clicked_data(self, pos):
        col, row = pos
        self.clicked_cell = f"Cell clicked: {pos}"
    
    def get_edited_data(self, pos, new_value):
        """
        Update the data in the DataEditorState and api.question_parts based on user edits.

        Parameters:
        pos (tuple): A tuple representing the (column, row) position of the edited cell.
        new_value (Any): The new value that was entered by the user.
        """
        col, row = pos

        # Check if the row is within bounds
        if 0 <= row < len(self.data):
            # Get the current QuestionPart for this row
            current_question_part = api.question_parts[row]
            
            # Create a new QuestionPart with updated values
            if col == 0:  # ID column
                # new_id = int(new_value)
                updated_question_part = QuestionPart(str(new_value['data']), current_question_part.text, current_question_part.marks)
                # self.data[row][0] = new_id
            elif col == 1:  # Question Text column
                # new_text = str(new_value)
                updated_question_part = QuestionPart(current_question_part.id, str(new_value['data']), current_question_part.marks)
                # self.data[row][1] = new_text
            elif col == 2:  # Points column
                # new_marks = float(new_value)
                updated_question_part = QuestionPart(current_question_part.id, current_question_part.text, float(new_value['data']))
                # self.data[row][2] = new_marks

            api.question_parts.remove(current_question_part)

            api.question_parts.append(updated_question_part)

            self.refresh_table()
      
    def get_deleted_item(self, selection):
        self.deleted = (
            f"Deleted cell: {selection['current']['cell']}"
        )

class QuestionState(rx.State):
    form_data: dict = {}
    did_submit: bool = False

    # data_editor = rx.get_state(DataEditorState_HP)

    def handle_submit(self, form_data: dict):
        """Handle form submission and update BackendManager."""
        self.form_data = form_data
        
        # Add question to BackendManager
        api.question_parts.append(QuestionPart(
            form_data.get('id'),
            form_data.get('ques'),
            float(form_data.get('pts'))
        ))

        # Set the did_submit flag to True
        self.did_submit = True

        # Refresh the table to reflect the new question
        return DataEditorState_HP.populate_data(api.question_parts)

class DeleteState(rx.State):
    form_data: dict = {}
    did_submit: bool = False

    # data_editor = rx.get_state(DataEditorState_HP)

    def handle_delete(self, form_data: dict):
        """Handle form submission and update BackendManager."""
        self.form_data = form_data
        
        # Add question to BackendManager
        qp_to_delete = api.get_questionPart_by_id(form_data.get('id'))
        api.question_parts.remove(qp_to_delete)
            # form_data.get('ques'),
            # float(form_data.get('pts'))

        # Set the did_submit flag to True
        self.did_submit = True

        # Refresh the table to reflect the new question
        return DataEditorState_HP.populate_data(api.question_parts)


class FormState(rx.State):
    form_data: str
    did_submit: bool = False

    def handle_submit_gen(self, form_data: str):
        """Handle form submission and update BackendManager."""
        self.form_data = form_data
        
        # Set the did_submit flag to True
        self.did_submit = True

        # print(form_data.get('ques'))

        api.generate_all_questions(form_data.get('ques'))
        # # Refresh the table to reflect the new question
        # DataEditorState_HP.refresh_table()

def ques_page() -> rx.Component:
    # Populate the table initially with question parts from the API
    DataEditorState_HP.populate_data(api.question_parts)

    # Data editor with cell editing functionality
    my_editor = rx.data_editor(
        # rx.button("Delete", on_click=DataEditorState_HP.delete_question),
        columns=DataEditorState_HP.cols,  # Access class attribute directly
        data=DataEditorState_HP.actual_data,  # Access instance attribute directly
        on_cell_clicked=DataEditorState_HP.get_clicked_data,  # Access instance method directly
        on_cell_edited=DataEditorState_HP.get_edited_data,  # Access instance method directly
        row_height=80,
        smooth_scroll_x=True,
        smooth_scroll_y=True,
        width="100%",
        column_select="single",
        height="30vh"
    )

    # Form for inputting new questions
    my_form = rx.form(
        rx.vstack(
            rx.hstack(
                rx.input(
                    placeholder="ID",
                    name="id",
                    type="string",
                    required=True,
                    width="100%"
                ),
                rx.input(
                    placeholder="Points",
                    name="pts",
                    type="float",
                    required=True,
                    width="100%"  
                ),
                width="100%"
            ),
            rx.input(
                placeholder="Question",
                name="ques",
                type="str",
                required=True,
                width="100%"
            ),
            rx.button("Submit", type="submit"),
            align="center"
        ),
        on_submit=lambda form_data: QuestionState.handle_submit(form_data),  # Directly call handle_submit
        reset_on_submit=True,
    )

    # Form for inputting new questions
    my_delete_form = rx.form(
        rx.vstack(rx.input(
                    placeholder="ID",
                    name="id",
                    type="string",
                    required=True,
                    width="100%"
                ),
            rx.button("Delete", type="submit"),
            align="center"
        ),
        on_submit=lambda form_data: DeleteState.handle_delete(form_data),  # Directly call handle_submit
        reset_on_submit=True,
    )

    # Form for generating new questions
    my_gen_form = rx.form(
        rx.vstack(
            rx.input(
                placeholder="Enter bulk questions",
                name="ques",
                type="str",
                required=True,
                width="100%"
            ),
            rx.button("Submit", type="submit"),
            align="center"
        ),
        on_submit=lambda form_data: FormState.handle_submit_gen(form_data),  # Directly call handle_submit
        reset_on_submit=True,
    )

    # Subheadings
    form_subheading = rx.heading("Submit New Question", size="5")
    delete_form_subheading = rx.heading("Delete Question", size="5")
    gen_form_subheading = rx.heading("Generate Questions from AI", size="5")



    # Page layout: Display both forms and the editor without condition
    my_child = rx.vstack(
        rx.heading("Enter your questions here", size="9"),
        my_editor,  # Always display the data editor
        form_subheading,  # Subheading for my_form
        my_form,  # Always display the individual question form
        delete_form_subheading,
        my_delete_form,
        gen_form_subheading,  # Subheading for my_gen_form
        my_gen_form,  # Always display the bulk question form
        justify="center",
        text_align="center",
        align="center",
        min_height="85vh",
    )

    return base_page(my_child)

