import json
from typing import List
from .Criterion import Criterion


from dataclasses import dataclass


@dataclass
class RubricPart:
    question_part_id: str
    max_points: float
    criteria: List[Criterion]

    def get_criterion_by_id(self, id:str) -> Criterion:
        for cr in self.criteria:
            if cr.id == id:
                return cr
        return None
        # self.isValid = self._evaluate_validity()

    # def _get_max_positive_point(self, possible_points: List[str]) -> float:
    #     max_positive = 0.0
    #     for point_str in possible_points:
    #         try:
    #             point = float(point_str)
    #             if point > 0 and point > max_positive:
    #                 max_positive = point
    #         except ValueError:
    #             raise ValueError(f"Invalid point value '{point_str}' in possible_points.")
    #     return max_positive

    # def _evaluate_validity(self) -> bool:
    #     total_max_positive_points = 0.0
    #     for criterion in self.criteria:
    #         max_positive_point = self._get_max_positive_point(criterion.possible_points)
    #         total_max_positive_points += max_positive_point
    #     return total_max_positive_points >= self.max_points
# 
    # def to_json(self) -> str:
    #     data = {
    #         'questionPartId': self.question_part_id,
    #         'maxPoints': self.max_points,
    #         'criteria': [criterion.to_dict() for criterion in self.criteria],
    #         'isValid': self.isValid
    #     }
    #     return json.dumps(data, indent=2)

    # def __repr__(self):
    #     return (f"RubricPart(question_part_id='{self.question_part_id}', "
    #             f"max_points={self.max_points}, criteria={self.criteria}, isValid={self.isValid})")