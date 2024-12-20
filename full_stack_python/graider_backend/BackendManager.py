import os
import sys

current_directory = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_directory)


from typing import List, Optional
from Student import Student
from QuestionPart import QuestionPart
from Criterion import Criterion
from ReferenceAnswerPart import ReferenceAnswerPart
from RubricPart import RubricPart
from aiTools import aiTools
from FeedbackPart import FeedbackPart

class BackendManager:
    """
    Main class that manages the entire backend, including students, questions, rubrics, and reference answers.
    """
    def __init__(self) -> None:
        self.students: List[Student] = []
        self.question_parts: List[QuestionPart] = []
        self.reference_answer_parts: List[ReferenceAnswerPart] = []
        self.rubric_parts: List[RubricPart] = []

    def add_student(self, student: Student) -> None:
        self.students.append(student)

    def remove_student(self, student: Student) -> None:
        if student in self.students:
            self.students.remove(student)

    def sortQuestionParts(self) -> None:
        self.question_parts.sort(key=lambda x: x.id)
    
    def get_questionPart_by_id(self, id:str) -> QuestionPart:
        for qp in self.question_parts:
            if qp.id == id:
                return qp
        return None
    
    def get_refAnsPart_by_id(self, id:str) -> ReferenceAnswerPart:
        for ra in self.reference_answer_parts:
            if ra.id == id:
                return ra
        return None
    
    def get_rubricPart_by_id(self, id:str) -> RubricPart:
        for rp in self.rubric_parts:
            if rp.id == id:
                return rp
        return None
    
    def initialize_rubric_parts(self):
        for qp in self.question_parts:
            rp = RubricPart(qp.id, qp.marks, [])
            self.rubric_parts.append(rp)
    
    def add_criterion_to_rubric_part(self, qPartId: str,  criterion: Criterion) -> None:
        rp = self.get_rubricPart_by_id(qPartId)
        if rp == None:
            return
        else:
            self.remove_criterion_from_rubric_part(qPartId, criterion.criterion_id)
            rp.criteria.append(criterion)


    def remove_criterion_from_rubric_part(self, qPartId, critId) -> None:
        rp = self.get_rubricPart_by_id(qPartId)
        if rp == None:
            return
        else:
            crit = rp.get_criterion_by_id(critId)
            if(crit == None):
                return
            else:
                rp.criteria.remove(crit)

    def reset_everything(self) -> None:
        """
        Resets all data including students, questions, reference answers, rubrics, and student feedback.
        """
        self.reset_questions()
        self.students.clear()

    def reset_questions(self) -> None:
        """
        Resets questions and all dependent data: reference answers, rubrics, and student feedback.
        """
        self.question_parts.clear()
        self.reset_reference_answers()

    def reset_reference_answers(self) -> None:
        """
        Resets reference answers and dependent data: rubrics and student feedback.
        """
        self.reference_answer_parts.clear()
        self.reset_rubric_parts()

    def reset_rubric_parts(self) -> None:
        """
        Resets rubrics and student feedback.
        """
        self.rubric_parts.clear()
        for student in self.students:
            student.feedbackParts.clear()
            student.set_total_marks(0)
            student.set_is_graded(False)

    def generate_all_questions(self, questions_text: str) -> None:
        """
        Generates all question parts by segregating the provided questions text.
        """
        self.reset_questions()
        self.question_parts = aiTools.segregateQuestion(questions_text)

    def set_questions_manually(self, question_parts: List[QuestionPart]) -> None:
        """
        Manually sets the question parts.
        """
        self.reset_questions()
        self.question_parts = question_parts

    def generate_reference_answers(self) -> None:
        """
        Generates reference answers for all question parts.
        """
        self.reset_reference_answers()
        for question_part in self.question_parts:
            if not question_part.id.endswith("context"):
                context = self.get_questionPart_by_id(self.generate_context_id(question_part.id))
                reference_answer = aiTools.generateReferenceAnswerPart(question_part, context)
                self.reference_answer_parts.append(reference_answer)

    def generate_context_id(self, qid : str) -> str:
        context = qid.split('_')[0]+"_"+"context"
        return context
                

    def extract_keywords_from_references(self) -> None:
        """
        Extracts keywords from all reference answers.
        """
        for reference_answer in self.reference_answer_parts:
            question_part = next((q for q in self.question_parts if q.id == reference_answer.qid), None)
            if question_part:
                keywords = aiTools.extractKeyWordsFromReference(reference_answer.answer, question_part)
                reference_answer.keywords = keywords

    def generate_rubrics(self, rough_rubric: Optional[str] = None) -> None:
        """
        Generates rubrics for all question parts.
        """
        self.reset_rubric_parts()
        for question_part, reference_answer_part in zip(self.question_parts, self.reference_answer_parts):
            rubric_part = aiTools.generateRubricPart(question_part, reference_answer_part, rough_rubric)
            self.rubric_parts.append(rubric_part)

    def grade_student(self, student: Student) -> None:
        """
        Grades a single student by evaluating their answers.
        """
        for question_part in self.question_parts:
            answer_text = student.get_response_part(question_part.id)
            reference_answer_part = next((ra for ra in self.reference_answer_parts if ra.qid == question_part.id), None)
            if answer_text and reference_answer_part:
                feedback_part = aiTools.evaluateAnswer(
                    answer_text=answer_text,
                    criterion='',
                    question_part=question_part,
                    context_question_part=question_part
                )
                student.add_feedback_part(feedback_part)
        total_marks = sum(fp.marks_awarded for fp in student.get_feedback_parts())
        student.set_total_marks(total_marks)
        student.set_is_graded(True)

    def grade_all_students(self) -> None:
        """
        Grades all students.
        """
        for student in self.students:
            self.grade_student(student)

# Single instance of BackendManager
api = BackendManager()