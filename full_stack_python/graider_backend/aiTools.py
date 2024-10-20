from typing import List, Optional
from .QuestionPart import QuestionPart
from .ReferenceAnswerPart import ReferenceAnswerPart
from .FeedbackPart import FeedbackPart
# Assuming RubricPart is defined elsewhere
from .RubricPart import RubricPart

"""
A static class containing AI-related utility functions for processing questions and answers.
"""
class aiTools:
    


    """
    Segregates a string containing all questions into individual QuestionPart instances.
        Args:
            questions_text (str): A string containing all the questions.
        Returns:
            List[QuestionPart]: A list of QuestionPart instances extracted from the input string.
    """
    @staticmethod
    def segrateQuestion(questions_text: str) -> List[QuestionPart]:

        prompt = "Your task is to extract each of the question parts from from the provided string.\
                    For each question part you have to extract an id, a text, and a marks field.\
                    The text in the initial part of the question is the context and is also represented as a question part and has 0 marks associated with it.\
                    For id, use the same question number in the provided document as closely as possible, and format it according to these rules:\
                    id rules: must be either leaf nodes or context nodes.\
                    # leaf nodes: example q1_a, must the most granular question part possible, i.e. if q1_a exists then id cannot be q1\
                    # context nodes: examples q1_context applies to each question part within q1 such as q1_a and q1_b\
                    # id must be unique\
                    # deep questions are not allowed i.e. q1_a is allowed, q1_a_1 (part within part) not allowed\
                    For text, use the given question for that part, i.e. QUOTE the extracted question. Do not make any changes to it at all.\
                    For marks, if the question part is a context, assign 0, otherwise extract the marks which may be within some type of parenthesis or at the end of the question.\
                    Your output should be a stringified JSON object which looks like this {\"question_parts\":[{\"id\":\"q1_context\",\"text\":\"France is an important country.\",\"marks\":0},{\"id\":\"q1_a\",\"text\":\"What is the capital of france?.\",\"marks\":10},{\"id\":\"q1_b\",\"text\":\"Who is the president of France?\",\"marks\":2},{\"id\":\"q2\",\"text\":\"Describe the process of impeachment.\",\"marks\":7}]}"
        pass  # Function implementation goes here


    """
    Generates a perfect reference answer for a given question part using the provided context.
        Args:
            question_part (QuestionPart): The question part for which to generate the reference answer.
            context (str): Additional context for the question part.
        Returns:
            ReferenceAnswerPart: The generated reference answer part.
    """
    @staticmethod
    def generateReferenceAnswerPart(question_part: QuestionPart, context: str) -> ReferenceAnswerPart:

        pass  # Function implementation goes here


    """
    Extracts key words from the perfect answer and generates two similar words for each key word.
        Args:
            perfect_answer (str): The perfect reference answer text.
            question_part (QuestionPart): The question part associated with the reference answer.
        Returns:
            List[str]: A list containing the key words and their similar words.
    """
    @staticmethod
    def extractKeyWordsFromReference(perfect_answer: str, question_part: QuestionPart) -> List[str]:
        
        pass  # Function implementation goes here

    """
    Extracts relevant sentences from a student's answers that answer the given question part.
        Args:
            answers_text (str): A string containing the student's answers to all question parts.
            question_part (QuestionPart): The specific question part to extract answers for.
            reference_answer_part (ReferenceAnswerPart): The reference answer part for comparison.
        Returns:
            List[str]: A list of sentences from the student's answers that are relevant to the question part.
    """
    @staticmethod
    def segregateAnswer(answers_text: str, question_part: QuestionPart, reference_answer_part: ReferenceAnswerPart) -> List[str]:

        pass  # Function implementation goes here


    """
    Generates a RubricPart object for a question part using the reference answer and an optional rough rubric.
        Args:
            question_part (QuestionPart): The question part for which to generate the rubric.
            reference_answer_part (ReferenceAnswerPart): The reference answer part to base the rubric on.
            rough_rubric (Optional[str]): An optional rough rubric provided by the teacher.
        Returns:
            RubricPart: The generated rubric part.
    """
    @staticmethod
    def generateRubricPart(
        question_part: QuestionPart,
        reference_answer_part: ReferenceAnswerPart,
        rough_rubric: Optional[str] = None
    ) -> RubricPart:

        pass  # Function implementation goes here


    """
    Evaluates a student's answer against a criterion and generates feedback.

        Args:
            answer_text (str): The student's answer text for a specific question part.
            criterion (str): The criterion to evaluate the answer against.
            question_part (QuestionPart): The question part associated with the answer.
            context_question_part (QuestionPart): Additional context question part for reference.

        Returns:
            FeedbackPart: The feedback generated for the student's answer.
    """
    @staticmethod
    def evaluateAnswer(
        answer_text: str,
        criterion: str,
        question_part: QuestionPart,
        context_question_part: QuestionPart
    ) -> FeedbackPart:
        pass  # Function implementation goes here