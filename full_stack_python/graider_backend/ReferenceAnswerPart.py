from typing import List
import json

class ReferenceAnswerPart:
    def __init__(self, qid: str, answer: str):
        self._qid = qid  # Use a private variable to store qid
        self.answer = answer
        self.keywords = []

    # Getter for 'qid' (read-only property)
    @property
    def qid(self):
        return self._qid

    # Note: No setter for 'qid', so it's read-only

    # Getter and Setter for 'answer'
    def get_answer(self):
        return self.answer

    def set_answer(self, answer: str):
        self.answer = answer

    # Getter and Setter for 'keywords'
    def get_keywords(self):
        return self.keywords

    def set_keywords(self, keywords: List[str]):
        self.keywords = keywords

    # Method to convert the object to a dictionary
    def to_dict(self):
        return {
            'qid': self.qid,
            'answer': self.answer,
            'keywords': self.keywords
        }

    # Method to convert the object to a JSON string
    def to_json(self):
        return json.dumps(self.to_dict())
