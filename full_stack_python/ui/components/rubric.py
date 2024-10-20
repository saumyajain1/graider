import reflex as rx
from typing import Any, List
from ...ui.base import base_page
from ...graider_backend.BackendManager import api
from ...graider_backend.Criterion import Criterion
from ...graider_backend.QuestionPart import QuestionPart
from ...graider_backend.RubricPart import RubricPart

from dataclasses import dataclass
# from copy import copy, deepcopy
import copy

@dataclass
# Define a Reflex data model to store the question details
class Row(rx.Model): #NOT NEEDED
    question_part_id: str  # e.g., "q1_part1"
    max_points: int        # e.g., 5
    criterion_id: str      # e.g., "c1"
    description: str       # e.g., "Clarity of Explanation"
    points: str            # e.g., "+1, -0.5" !!!SHOULD BE LIST 

class DataEditor(rx.State):
    clicked_data: str = "Cell clicked: "

    # Define the columns for the data editor
    cols: list[Any] = [
        # {"title": "Question ID", "type": "str"},
        {"title": "Question Part ID", "type": "str", "group": "Data", "width": 150},
        {"title": "Max Points", "type": "int", "group": "Data", "width": 100},
        {"title": "Criterion ID", "type": "str", "group": "Criteria", "width": 100},
        {"title": "Description", "type": "str", "group": "Criteria", "width": 300},
        {"title": "Points", "type": "list", "group": "Criteria", "width": 100}, #changed type to list from str
    ]

    # # Define the data to populate the table
    # data = [
    #     ["q1_part1", 5, "c1", "Clarity of Explanation", "+1, -0.5"],
    #     ["q1_part1", 5, "c2", "Accuracy of Content", "-1, -0.5"],
    #     ["q1_part1", 5, "c3", "Use of Relevant Examples", "+0.5"],
    #     ["q1_part2", 4, "c1", "Completeness", "-0.5"],
    #     ["q1_part2", 4, "c2", "Depth of Analysis", "+2, -1"],
    # ]
    data: list[List[Any]] = []

    # class Question(rx.Model):
    # question_part_id: str  # e.g., "q1_part1"
    # max_points: int        # e.g., 5
    # criterion_id: str      # e.g., "c1"
    # description: str       # e.g., "Clarity of Explanation"
    # points: str            # e.g., "+1, -0.5"


    def populate_data(self, rubrics: List[RubricPart]) -> None:
        """Populate DataEditorState_HP with a list of QuestionPart objects."""
        self.data: list[List[Any]] = []

        if (rubrics != None): 
          for rubric_part in rubrics:
            # print(elem)
            criteria = rubric_part["criteria"]
            # print(criteria)
            if (criteria != None): 
                for criterion in criteria:
                    self.data.append([rubric_part["question_part_id"], rubric_part["max_points"], criterion["criterion_id"], criterion["description"], criterion["possible_points"]])  
    
    def refresh_table(self):
        """Refresh the table by populating data from the current question parts in the API."""
        # self.data: list[List[Any]] = []
        # self.populate_data(copy.deepcopy(api.rubric_parts))

        if (api.rubric_parts != None): 
          for rubric_part in api.rubric_parts:
            criteria = rubric_part.criteria
            if (criteria != None): 
                for criterion in criteria:
                    self.data.append([rubric_part["question_part_id"], rubric_part["max_points"], criterion["criterion_id"], criterion["description"], criterion["possible_points"]])  
    
    # @rx.var
    # def actual_data(self) -> list[list]:
    #     return [[row.question_part_id, row.max_points, row.criterion_id, row.description, row.points] for row in self.data]

    # Handle cell click events
    def click_cell(self, pos):
        col, row = pos
        self.clicked_data = f"Cell clicked: {col}, {row}"
        # yield self.get_clicked_data(pos)

    # Retrieve clicked data
    def get_clicked_data(self, pos) -> str:
        return self.clicked_data

class QuestionState(rx.State):
    form_data: dict = {}
    did_submit: bool = False

    # data_editor = rx.get_state(DataEditorState_HP)

    def handle_submit(self, form_data: dict):
        """Handle form submission and update BackendManager."""
        self.form_data = form_data

        # print(form_data)
        # {'qid': '456', 'max pts': '4567', 'criterion': 'fcnvgm', 'description': 'nv b', 'pts': 'cfnvg'}
        
        # # Add rubric to BackendManager
        criteria: List[Criterion] = []
        criteria.append(Criterion(form_data.get('criterion'), form_data.get('description'), [s.strip() for s in form_data.get('pts').split(',')]))
        print(len(api.question_parts))

    # def add_criterion_to_question_part(self, Criterion, qPartId) -> None:

    


        # api.rubric_parts.append(RubricPart(form_data.get('qid'), form_data.get('max pts'), criteria))

    # # Rubric Part
    # def __init__(self, question_part_id: str, max_points: float, criteria: List[Criterion]):
    #     self.question_part_id = question_part_id
    #     self.max_points = max_points
    #     self.criteria = criteria  # List of Criterion instances
    #     self.isValid = self._evaluate_validity()
    
    # # Backend
    # def __init__(self) -> None:
    #     self.students: List[Student] = []
    #     self.question_parts: List[QuestionPart] = []
    #     self.reference_answer_parts: List[ReferenceAnswerPart] = []
    #     self.rubric_parts: List[RubricPart] = []

    # # Criterion
    # def __init__(self, criterion_id: str, description: str, possible_points: List[str]):
    #     self.criterion_id = criterion_id
    #     self.description = description
    #     self.possible_points = possible_points  # List of strings like "+1", "+0.5", etc.

        # Set the did_submit flag to True
        self.did_submit = True

        # Refresh the table to reflect the new question
        return DataEditor.populate_data(api.rubric_parts)

class DeleteState(rx.State):
    form_data: dict = {}
    did_submit: bool = False

    # data_editor = rx.get_state(DataEditorState_HP)

    def handle_delete(self, form_data: dict):
        """Handle form submission and update BackendManager."""
        self.form_data = form_data
        
        # # Add question to BackendManager
        # qp_to_delete = api.get_questionPart_by_id(form_data.get('id'))
        # api.question_parts.remove(qp_to_delete)
        
        
        # Set the did_submit flag to True
        self.did_submit = True

        # def remove_criterion_from_question_part(self, qPartId, critId) -> None:
        # self.question_parts

        # Refresh the table to reflect the new question
        return DataEditor.populate_data(api.rubric_parts)

def rubric_page() -> rx.Component:
    # Welcome Page (Index)
    # Form for inputting new questions
    # my_form = rx.form(
    #     rx.vstack(
    #         rx.hstack(
    #             rx.input(
    #                 placeholder="Question ID",
    #                 name="qid",
    #                 type="string",
    #                 required=True,
    #                 width="100%"
    #             ),
    #             rx.input(
    #                 placeholder="Max Points",
    #                 name="max pts",
    #                 type="float",
    #                 required=True,
    #                 width="100%"  
    #             ),
    #             width="100%"
    #         ),
    #         rx.input(
    #             placeholder="Criterion ID",
    #             name="criterion",
    #             type="str",
    #             required=True,
    #             width="100%"
    #         ),
    #         rx.input(
    #             placeholder="Description",
    #             name="description",
    #             type="str",
    #             required=True,
    #             width="100%"
    #         ),
    #         rx.input(
    #             placeholder="Points",
    #             name="pts",
    #             type="str",
    #             required=True,
    #             width="100%"
    #         ),
    #         rx.button("Submit", type="submit"),
    #         align="center"
    #     ),
    #     on_submit=lambda form_data: QuestionState.handle_submit(form_data),  # Directly call handle_submit
    #     reset_on_submit=True,
    # )

    DataEditor.populate_data(api.rubric_parts)

    my_form = rx.form(
        rx.vstack(
            rx.input(
                placeholder="Question ID",
                name="qid",
                type="string",
                required=True,
                width="100%"
            ),
            rx.input(
                placeholder="Max Points",
                name="max pts",
                type="float",
                required=True,
                width="100%"  
            ),
            rx.input(
                placeholder="Criterion ID",
                name="criterion",
                type="string",
                required=True,
                width="100%"
            ),
            rx.input(
                placeholder="Description",
                name="description",
                type="string",
                required=True,
                width="100%"
            ),
            rx.input(
                placeholder="Points",
                name="pts",
                type="string",
                required=True,
                width="100%"
            ),
            rx.button("Submit", type="submit"),
            align="center"
        ),
        on_submit=lambda form_data: QuestionState.handle_submit(form_data),  # Directly call handle_submit
        reset_on_submit=True,
    )

    my_editor = rx.data_editor(
        columns=DataEditor.cols,
        data=DataEditor.data,
        on_cell_clicked=DataEditor.click_cell,
    )

    # Subheadings
    form_subheading = rx.heading("Submit New Rubric", size="5")
    delete_form_subheading = rx.heading("Delete Rubric", size="5")



    # Page layout: Display both forms and the editor without condition
    my_child = rx.vstack(
        rx.heading("Enter your questions here", size="9"),
        my_editor,  # Always display the data editor
        form_subheading,  # Subheading for my_form
        my_form,  # Always display the individual question form
        delete_form_subheading,
        # my_delete_form,
        justify="center",
        text_align="center",
        align="center",
        min_height="85vh",
    )
    return base_page(my_child)