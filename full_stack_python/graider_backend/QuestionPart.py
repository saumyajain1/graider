# IDEAL id rules: must be either leaf nodes or context nodes.
# leaf nodes: example q1_a, must the most granular question possible, i.e. if q1_a exists then cannot be q1
# context nodes: examples q1_context applies to each question part within q1 such as q1_a and q1_b
# id must be unique
# deep questions are not allowed i.e. q1_a is allowed, q1_a_1 not allowed


from dataclasses import dataclass


@dataclass
class QuestionPart:
    id: str
    text: str
    marks: float
