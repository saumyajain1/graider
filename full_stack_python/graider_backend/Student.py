import json
from typing import List, Dict, Optional
from .FeedbackPart import FeedbackPart  # Import the FeedbackPart class
from .QuestionPart import QuestionPart  # Import the QuestionPart class

class Student:
    def __init__(self, question_parts: List[QuestionPart]) -> None:
        self.response: str = ''
        self.total_marks: int = 0
        self.isGraded: bool = False
        self.responseParts: Dict[str, str] = {q.id: '' for q in question_parts}
        self.feedbackParts: List[FeedbackPart] = []

    # Getter and setter for 'response'
    def get_response(self) -> str:
        return self.response

    def set_response(self, response: str) -> None:
        self.response = response

    # Getter and setter for 'total_marks'
    def get_total_marks(self) -> int:
        return self.total_marks

    def set_total_marks(self, total_marks: int) -> None:
        self.total_marks = total_marks

    # Getter and setter for 'isGraded'
    def get_is_graded(self) -> bool:
        return self.isGraded

    def set_is_graded(self, is_graded: bool) -> None:
        self.isGraded = is_graded

    # Getter and setter for responseParts
    def get_response_part(self, qID: str) -> Optional[str]:
        return self.responseParts.get(qID)

    def set_response_part(self, qID: str, response: str) -> None:
        if qID in self.responseParts:
            self.responseParts[qID] = response
        else:
            raise KeyError(f"Question ID '{qID}' not found in responseParts")

    # Method to add a FeedbackPart to feedbackParts list
    def add_feedback_part(self, feedback_part: FeedbackPart) -> None:
        if feedback_part.qid in self.responseParts:
            self.feedbackParts.append(feedback_part)
        else:
            raise KeyError(f"Question ID '{feedback_part.qid}' not found in responseParts")

    # Method to get all FeedbackPart instances
    def get_feedback_parts(self) -> List[FeedbackPart]:
        return self.feedbackParts

    # Method to get FeedbackPart instances for a specific qID
    def get_feedback_parts_by_qid(self, qID: str) -> List[FeedbackPart]:
        return [fp for fp in self.feedbackParts if fp.qid == qID]

    # Function to convert the object's data to JSON
    def convertToJson(self) -> str:
        data = {
            'response': self.response,
            'total_marks': self.total_marks,
            'isGraded': self.isGraded,
            'responseParts': self.responseParts,
            'feedbackParts': [
                {
                    'qid': fp.qid,
                    'criteria_id': fp.criteria_id,
                    'feedbackText': fp.feedbackText,
                    'marks_awarded': fp.marks_awarded
                } for fp in self.feedbackParts
            ]
        }
        return json.dumps(data)