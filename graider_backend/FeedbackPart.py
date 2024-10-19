from typing import Optional
import json

class FeedbackPart:
    def __init__(self, qid: str, criteria_id: str, feedbackText: str, marks_awarded: int):
        self._qid = qid  # Making qid read-only
        self._criteria_id = criteria_id  # Making criteria_id read-only
        self.feedbackText = feedbackText
        self.marks_awarded = marks_awarded

    # Getter for 'qid' (read-only property)
    @property
    def qid(self):
        return self._qid

    # Getter for 'criteria_id' (read-only property)
    @property
    def criteria_id(self):
        return self._criteria_id

    # Getter and Setter for 'feedbackText'
    def get_feedback_text(self):
        return self.feedbackText

    def set_feedback_text(self, feedbackText: str):
        self.feedbackText = feedbackText

    # Getter and Setter for 'marks_awarded'
    def get_marks_awarded(self):
        return self.marks_awarded

    def set_marks_awarded(self, marks_awarded: int):
        if marks_awarded < 0:
            raise ValueError("Marks awarded cannot be negative.")
        self.marks_awarded = marks_awarded

    # Method to convert the object to a dictionary
    def to_dict(self):
        return {
            'qid': self.qid,
            'criteria_id': self.criteria_id,
            'feedbackText': self.feedbackText,
            'marks_awarded': self.marks_awarded
        }

    # Method to convert the object to a JSON string
    def to_json(self):
        return json.dumps(self.to_dict())