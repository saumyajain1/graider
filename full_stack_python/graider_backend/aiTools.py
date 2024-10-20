import json
from typing import List, Optional
from groq import Groq
import requests
import json

from QuestionPart import QuestionPart
from ReferenceAnswerPart import ReferenceAnswerPart
from FeedbackPart import FeedbackPart
# Assuming RubricPart is defined elsewhere
from RubricPart import RubricPart

from dotenv import load_dotenv

from Criterion import Criterion

load_dotenv(".env")

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

        system_prompt = "Your task is to extract each of the question parts from from the provided string.\
                    For each question part you have to extract an id, a text, and a marks field.\
                    The text in the initial part of the question is the context and is also represented as a question part and has 0 marks associated with it.\
                    For id, use the same question number in the provided document as closely as possible, and format it according to these rules:\
                    id rules: must be either leaf nodes or context nodes.\
                    # leaf nodes: example q1_a, must the most granular question part possible, i.e. if q1_a exists then id cannot be q1\
                    # context nodes: examples q1_context applies to each question part within q1 such as q1_a and q1_b\
                    # id must be unique\
                    # deep questions are not allowed i.e. q1_a is allowed, q1_a_1 (part within part) not allowed\
                    For text, extract the text portion from the given question for that part, i.e. QUOTE the extracted question. Do not make any changes to it at all.\
                    For marks, if the question part is a context, assign 0, otherwise extract the marks which may be within some type of parenthesis or at the end of the question.\
                    Your output should be a stringified JSON object which looks like this {\"question_parts\":[{\"id\":\"q1_context\",\"text\":\"France is an important country.\",\"marks\":0},{\"id\":\"q1_a\",\"text\":\"What is the capital of france?.\",\"marks\":10},{\"id\":\"q1_b\",\"text\":\"Who " \
                 "is the president of France?\",\"marks\":2},{\"id\":\"q2\",\"text\":\"Describe the process of impeachment.\",\"marks\":7}]}"
        
        client = Groq()
        completion = client.chat.completions.create(
            model="llama-3.2-90b-text-preview",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": questions_text
                }
            ],
            temperature=0.6,
            max_tokens=2500,
            top_p=0.4,
            stream=False,
            response_format={"type": "json_object"},
            stop=None,
        )

        # print(completion.choices[0].message.content)
        ai_response = completion.choices[0].message.content

        parsed_data = json.loads(ai_response)
        # Step 3: Convert the parsed dictionary to a list of QuestionPart objects
        question_parts_list = [
            QuestionPart(id=part['id'], text=part['text'], marks=part['marks'])
            for part in parsed_data['question_parts']
        ]

        # return []
        return question_parts_list
            # pass  # Function implementation goes here

    """
    Generates a perfect reference answer for a given question part using the provided context.
        Args:
            question_part (QuestionPart): The question part for which to generate the reference answer.
            context (QuestionPart): Additional context for the question part.
        Returns:
            ReferenceAnswerPart: The generated reference answer part.
    """

    @staticmethod
    def generateReferenceAnswerPart(question_part: QuestionPart, context: QuestionPart) -> ReferenceAnswerPart:
        quest = question_part.text
        context_text = context.text
        prompt = "Your task is to generate the ideal reference answer for the given question part, using the provided context if available.\n" \
                 "\n" \
                 "Instructions:\n" \
                 "- For the given question part, generate a comprehensive and detailed answer that fully addresses the question.\n" \
                 "- If a context is provided, incorporate relevant information from the context into your answer.\n" \
                 "- The reference answer should be clear and follow logical steps to reach the final conclusion.\n" \
                 "- The answer should cover all aspects and include technical terms (keywords) if applicable that the question is testing, as it will be used to evaluate student answers.\n" \
                 "\n" \
                 "Output Format:\n" \
                 "Your output should be a stringified JSON object and no other text accompanying it, in the following format:\n" \
                 "Example:\n"
        "Given:\n"
        "question_part = \"Explain the process of photosynthesis.\"\n"
        "context = \"Plants use sunlight to produce energy.\"\n"
        "\n"
        "Your output should be:\n"
        "{"
        "\"reference_answer\" : \"Photosynthesis is the process by which green plants use sunlight to synthesize nutrients from carbon dioxide and water. It involves chlorophyll in the leaves absorbing light energy, which is then used to convert carbon dioxide from the air and water from the soil into glucose and oxygen. The glucose provides energy for the plant's growth, while the oxygen is released into the atmosphere.\""
        "}"



        

        ret_val_from_AI = ""
        ref_ans = json.loads(ret_val_from_AI)["reference_answer"]
        ref_ans_part = ReferenceAnswerPart(question_part.id, ref_ans)
        return ref_ans_part

        # "- The answer should be self-contained and not refer to previous parts or external information.\n" \

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
    prompt = "Your task is to go through the perfect answer generated and the question part provided and " \
             "retrieve all the important keywords which make up the important details of the answer and " \
             "that are needed to sufficiently answer what is being asked by the specific question part." \
             "Based on the reference answer generated you should return a list of keywords in stringified JSON " \
             "which are vital for the answer to be correct."
    '{\\"reference_keywords\\" : \'["photosynthesis", "green plants", "sunlight", "synthesize", "nutrients", "carbon dioxide", "water", "chlorophyll", "leaves", "absorb", "light energy", "glucose", "oxygen", "energy", "growth", "atmosphere", "air", "soil"]\'}'

    # pass  # Function implementation goes here

    ret_val_from_AI = ""
    parsed_data = json.loads(ret_val_from_AI)

    return parsed_data["reference_keywords"]






"""
Extracts relevant sentences from a student's answers that answer the given question part and are similar to the reference answer in complicated cases.
    Args:
        answers_text (str): A string containing the student's answers to all question parts.
        question_part (QuestionPart): The specific question part to extract answers for.
        reference_answer_part (ReferenceAnswerPart): The reference answer part for comparison.
    Returns:
        List[str]: A list of sentences from the student's answers that are relevant to the question part.
"""


@staticmethod
def segregateAnswer(answers_text: str, question_part: QuestionPart, reference_answer_part: ReferenceAnswerPart) -> \
        List[str]:
    prompt = (
        "Your task is to extract relevant sentences from the student's answers that directly address the given question part.\n"
        "\n"
        "Instructions:\n"
        "- Ensure that the extracted sentences are direct quotations from the student's answers. Do not modify the sentences in any manner"
        "- Students often submit poorly formatted answers and may not label the answer parts or order the parts correctly. When they do label and order it, it is easier to extract relevant portions, otherwise its not."
        "- Carefully read the provided question part to understand what is being asked.\n"
        "- Review the reference answer part to grasp the ideal response.\n"
        "- Thoroughly go through the student's answers.\n"
        "- Identify and compile a list of sentences from the student's answers that are most relevant to the question part and its reference answer.\n"
        "- Students are expected to provide thorough explanations for each question part unless the question specifically asks for a brief, one-word, or numerical answer, or instructs not to explain.\n"
        "\n"
        "Output Format:\n"
        "Your output should be a list of sentences extracted from the student's answers that are relevant to the reference answer of the provided question part.\n"
        "\n"
        "Example:\n"
        "Given:\n"
        "question_part = {\"id\": \"q4\", \"text\": \"Describe the process of photosynthesis.\", \"marks\": 10}\n"
        "reference_answer_part = {\"id\": \"q4\", \"answer\": \"Photosynthesis is the process by which green plants use sunlight to synthesize foods from carbon dioxide and water.\"}\n"
        "answers_text = \"Plants make their own food using sunlight. This process is called photosynthesis. It involves converting carbon dioxide and water into glucose and oxygen.\"\n"
        "\n"
        "Your output should be:\n"
        "[\n"
        "  \"Plants make their own food using sunlight.\",\n"
        "  \"This process is called photosynthesis.\",\n"
        "  \"It involves converting carbon dioxide and water into glucose and oxygen.\"\n"
        "]"
    )
    ret_val_from_AI = ""
    parsed_data = json.loads(ret_val_from_AI)

    return parsed_data["answers_text"]






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
    prompt = (
        "Your task is to create a RubricObject instance for the given question part using the provided reference answer.\n"
        "Instructions:\n"
        "- Generate a rubric in a tabular form consisting of several criteria based on the total marks available for the question part.\n"
        "- Each criterion should reflect the key points addressed in the reference answer and be as concise as possible.\n"
        "- Assign a range of marks for each criterion, clearly explaining the expectations to achieve those marks.\n"
        "- Ensure that each criterion aligns with the learning objectives demonstrated in the reference answer and does not include content outside the syllabus.\n"
        "- Do not assign negative marks; the minimum mark for any criterion should be zero.\n")
    pass  # Function implementation goes here

    ret_val_from_AI = ""
    parsed_data = json.loads(ret_val_from_AI)

    criterion = ret_val_from_AI

    rubric_list = RubricPart(
        id = question_part['id'], max_points= question_part['marks'], criteria=criterion,
        isValid= evaluateAnswer(reference_answer_part, criterion, question_part)
    )

    return rubric_list




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
        criterion: Criterion,
        question_part: QuestionPart,
        context_question_part: QuestionPart
) -> FeedbackPart:
    crit_desc = criterion.description
    crit_poss_points = criterion.possible_points
    system_prompt = f"You are an experienced assignment/exam grader. Your task is to allocate marks and provide feedback to a provided student answer for the provided question and question context but evaluate based on the following criterion ONLY: {crit_desc}" \
                    f"The marks allotted must be one of the items in the list: {crit_poss_points}" \
                    f"Question Context: {context_question_part} \n Question: {question_part}" \
                    "Remember that there are other granular criterion which are being evaluated separately so only to evaluate based on the current criterion" \
                    "Thoroughly analyze the answer to output feedback on the answer provided and to evaluate which of the possible points in the list should be allotted based on how well that criterion was covered in the answer.  " \
                    "The feedback of the reasoning should be brief (1-3 sentences) of why the student's answer was given the particular score for that criteria and what was subsequently missing." \
                    "While considering the allocation of the criterion by the system you should never award points based on unnecessary information but only relevant to the specific question part and criterion." \
                    "Your output should be in Json: {\"feedback\": \"Great explanation, but needs more clarity on the second point.\", \"marks\": 8.5}"

    client = Groq()
    completion = client.chat.completions.create(
        model="llama-3.2-90b-text-preview",
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": answer_text
            }
        ],
        temperature=0.6,
        max_tokens=2500,
        top_p=0.4,
        stream=False,
        response_format={"type": "json_object"},
        stop=None,
    )

    # print(completion.choices[0].message.content)
    ai_response = completion.choices[0].message.content

    parsed_data = json.loads(ai_response)

    return FeedbackPart(question_part.id, crit_desc, parsed_data['feedback'], parsed_data['marks'])
