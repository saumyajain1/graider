from typing import List

class Criterion:
    def __init__(self, criterion_id: str, description: str, possible_points: List[str]):
        self.criterion_id = criterion_id
        self.description = description
        self.possible_points = possible_points  # List of strings like "+1", "+0.5", etc.

    def to_dict(self):
        return {
            'criterionId': self.criterion_id,
            'description': self.description,
            'possible_points': self.possible_points
        }