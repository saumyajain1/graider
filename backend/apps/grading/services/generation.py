import json
import os
import re
import unicodedata
from pathlib import Path
from textwrap import dedent

from apps.assignments.models import Assignment, QuestionPart

from .openai_client import OpenAIChatService
from .schemas import (
    GeneratedQuestionPartSchema,
    GeneratedQuestionSetSchema,
    GeneratedReferenceAnswerSchema,
    GeneratedRubricSchema,
)

QUESTION_MODEL = os.getenv("OPENAI_QUESTION_MODEL", "gpt-6-luna")
ARTIFACT_MODEL = os.getenv("OPENAI_ARTIFACT_MODEL", "gpt-6-luna")

FOCUS_HINT_RE = re.compile(r"\b(?:q|question)\s*[-_ ]?(?P<number>\d{1,2})\b", re.IGNORECASE)
TOP_LEVEL_SECTION_RE = re.compile(
    r"(?m)^(?:question\s*)?(?P<number>\d+)(?!\.\d)(?:[.)-]\s+|\s+)(?P<body>[^\n]+)$",
    re.IGNORECASE,
)
BRACKETED_SUBQUESTION_RE = re.compile(r"(?m)^\s*\[(?P<label>\d+(?:\.\d+)+)\]\s*")
DECIMAL_SUBQUESTION_RE = re.compile(r"(?m)^\s*(?P<label>\d+(?:\.\d+)+)\s+")
ANSWER_PLACEHOLDER_RE = re.compile(r"(?im)^\s*Answer\s*:\s*.*$")
PAGE_NUMBER_RE = re.compile(r"(?m)^\s*\d+\s*$")
EACH_PART_MARKS_RE = re.compile(
    r"Each part is worth\s*\[?\s*(?P<points>\d+(?:\.\d+)?)\s*points?\s*\]?",
    re.IGNORECASE,
)
INLINE_MARKS_RE = re.compile(r"\[\s*(?P<points>\d+(?:\.\d+)?)\s*points?\s*\]", re.IGNORECASE)
CONTEXT_NOISE_RE = re.compile(
    r"(?im)^\s*(?:each part is worth.*|answer\s*:.*|page \d+.*|marks?\s*:.*)\s*$"
)
SHARED_REFERENCE_RE = re.compile(
    r"\b(?:from the previous (?:question|part)|previous (?:question|part)|last part|above|"
    r"same function|this function|that function|previous results|defined above)\b",
    re.IGNORECASE,
)
SHARED_STEM_HINT_RE = re.compile(
    r"\b(?:consider|suppose|let|assume|given|define|defined by|objective function|"
    r"the function|we have)\b",
    re.IGNORECASE,
)
SPECIFIC_LABEL_REFERENCE_RE = re.compile(
    r"\b(?:question|part)\s*\[?(?P<label>\d+(?:\.\d+)*)\]?",
    re.IGNORECASE,
)
PDF_ARTIFACT_RE = re.compile(
    r"(?:\x0c|\bnX\b|\bdX\b|wherex|[a-z]\([a-z]\)|\b[A-Za-z]+[A-Z][a-z]+|\b[A-Za-z]is\b)"
)

UNICODE_REPLACEMENTS = {
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\u00a0": " ",
}


def get_assignment_source_name(assignment: Assignment):
    source_file = getattr(assignment, "source_file", None)
    if not source_file:
        return ""
    return Path(str(source_file)).name


def derive_focus_question_number(assignment: Assignment):
    candidates = [
        getattr(assignment, "title", "") or "",
        getattr(assignment, "description", "") or "",
        get_assignment_source_name(assignment),
    ]
    for candidate in candidates:
        match = FOCUS_HINT_RE.search(candidate)
        if match:
            return match.group("number")
    return None


def normalize_source_label(value: str | None):
    if not value:
        return ""
    label = value.strip()
    label = label.strip("[]()")
    label = re.sub(r"\s+", "", label)
    return label


def parent_label_from_source_label(source_label: str | None):
    normalized = normalize_source_label(source_label)
    if "." in normalized:
        return normalized.split(".", 1)[0]
    return normalized


def normalize_assignment_text(raw_text: str):
    text = unicodedata.normalize("NFKC", raw_text or "")
    for old, new in UNICODE_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(
        r"(?<!\n)(\[\d+(?:\.\d+)+\])(?=\s*[A-Z(\"'])",
        r"\n\1",
        text,
    )
    text = PAGE_NUMBER_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def slice_text_to_focus_section(text: str, focus_question_number: str | None):
    if not focus_question_number:
        return text

    section_matches = get_top_level_section_matches(text)
    if not section_matches:
        return text

    for index, match in enumerate(section_matches):
        if match.group("number") != focus_question_number:
            continue
        start = match.start()
        end = section_matches[index + 1].start() if index + 1 < len(section_matches) else len(text)
        return text[start:end].strip()

    return text


def clean_block_lines(text: str):
    cleaned_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1]:
                cleaned_lines.append("")
            continue
        line = re.sub(r"[ \t]+", " ", line)
        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return cleaned_lines


def clean_question_block(text: str):
    text = ANSWER_PLACEHOLDER_RE.sub("", text or "")
    text = PAGE_NUMBER_RE.sub("", text)
    lines = clean_block_lines(text)
    if not lines:
        return ""

    preserved = []
    for line in lines:
        if not line:
            if preserved and preserved[-1] != "":
                preserved.append("")
            continue
        preserved.append(line)

    text = "\n".join(preserved).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def clean_context_block(text: str):
    text = CONTEXT_NOISE_RE.sub("", text or "")
    text = PAGE_NUMBER_RE.sub("", text)
    lines = [line for line in clean_block_lines(text) if line]
    return "\n".join(lines).strip()


def parse_marks(value: str | None):
    return float(value) if value is not None else None


def get_subquestion_matches(text: str):
    matches = list(BRACKETED_SUBQUESTION_RE.finditer(text))
    if matches:
        return matches
    return list(DECIMAL_SUBQUESTION_RE.finditer(text))


def is_probable_section_heading(body: str):
    normalized = body.strip()
    if INLINE_MARKS_RE.search(normalized):
        return True
    if re.search(r"[=∥∈λΣ∑^_{}]", normalized):
        return False
    alpha_words = re.findall(r"[A-Za-z]{3,}", normalized)
    return len(alpha_words) >= 2


def get_top_level_section_matches(text: str):
    return [
        match
        for match in TOP_LEVEL_SECTION_RE.finditer(text)
        if is_probable_section_heading(match.group("body"))
    ]


def build_section_index(text: str):
    matches = get_top_level_section_matches(text)
    index = {}
    for position, match in enumerate(matches):
        number = match.group("number")
        section_end = matches[position + 1].start() if position + 1 < len(matches) else len(text)
        index[number] = {
            "match": match,
            "end": section_end,
        }
    return index


def should_copy_first_question_into_context(question_texts: list[str]):
    if len(question_texts) < 2:
        return False

    if not SHARED_REFERENCE_RE.search("\n".join(question_texts[1:])):
        return False

    return bool(SHARED_STEM_HINT_RE.search(question_texts[0]))


def append_context_part(parts, parent_label: str, context_chunks: list[str]):
    context_chunks = [chunk.strip() for chunk in context_chunks if chunk.strip()]
    if not context_chunks:
        return

    text = "\n\n".join(dict.fromkeys(context_chunks))
    parts.append(
        GeneratedQuestionPartSchema(
            part_type="context",
            source_label=parent_label,
            parent_key=parent_label,
            text=text,
            max_marks=0,
        )
    )


def parse_structured_pdf_questions(assignment: Assignment):
    normalized_text = normalize_assignment_text(getattr(assignment, "raw_assignment_text", ""))
    if not normalized_text:
        return None

    focus_question_number = derive_focus_question_number(assignment)
    focused_text = slice_text_to_focus_section(normalized_text, focus_question_number)
    subquestion_matches = get_subquestion_matches(focused_text)
    if not subquestion_matches:
        return None

    section_index = build_section_index(focused_text)
    grouped_matches = {}
    for match in subquestion_matches:
        label = normalize_source_label(match.group("label"))
        parent_label = parent_label_from_source_label(label)
        if focus_question_number and parent_label != focus_question_number:
            continue
        grouped_matches.setdefault(parent_label, []).append((label, match))

    if not grouped_matches:
        return None

    parts = []
    for parent_label, group_matches in grouped_matches.items():
        section_meta = section_index.get(parent_label)
        section_start = section_meta["match"].end() if section_meta else group_matches[0][1].start()
        section_end = section_meta["end"] if section_meta else (
            group_matches[-1][1].end() if len(group_matches) == 1 else group_matches[-1][1].start()
        )
        section_text = focused_text[section_start:section_end]
        shared_marks_match = EACH_PART_MARKS_RE.search(section_text)
        shared_marks = parse_marks(shared_marks_match.group("points")) if shared_marks_match else None

        context_chunks = []
        if section_meta:
            preamble = clean_context_block(
                focused_text[section_meta["match"].end():group_matches[0][1].start()]
            )
            if preamble:
                context_chunks.append(preamble)

        question_parts_for_group = []
        for index, (source_label, match) in enumerate(group_matches):
            start = match.end()
            end = (
                group_matches[index + 1][1].start()
                if index + 1 < len(group_matches)
                else (section_meta["end"] if section_meta else len(focused_text))
            )
            block = clean_question_block(focused_text[start:end])
            if not block:
                continue

            inline_marks_match = INLINE_MARKS_RE.search(block)
            max_marks = (
                parse_marks(inline_marks_match.group("points"))
                if inline_marks_match
                else shared_marks
            )
            if inline_marks_match:
                block = clean_question_block(INLINE_MARKS_RE.sub("", block))

            question_parts_for_group.append(
                GeneratedQuestionPartSchema(
                    part_type="question",
                    source_label=source_label,
                    parent_key=parent_label,
                    text=block,
                    max_marks=max_marks,
                )
            )

        if question_parts_for_group and should_copy_first_question_into_context(
            [part.text for part in question_parts_for_group]
        ):
            context_chunks.append(question_parts_for_group[0].text)

        append_context_part(parts, parent_label, context_chunks)
        parts.extend(question_parts_for_group)

    if not parts:
        return None

    return GeneratedQuestionSetSchema(parts=parts)


def question_set_needs_repair(question_set: GeneratedQuestionSetSchema):
    return any(PDF_ARTIFACT_RE.search(part.text) for part in question_set.parts)


def repair_generated_question_parts(
    assignment: Assignment,
    question_set: GeneratedQuestionSetSchema,
):
    if not question_set.parts or not question_set_needs_repair(question_set):
        return question_set

    try:
        service = OpenAIChatService()
        repaired = service.parse(
            user=assignment.teacher,
            operation="question_repair",
            model=QUESTION_MODEL,
            response_format=GeneratedQuestionSetSchema,
            system_prompt=dedent(
                """
                You are cleaning already-segmented assignment question parts extracted from a PDF.

                Rules:
                - Preserve the number of parts and keep them in the same order.
                - Preserve each part's source_label, parent_key, part_type, and max_marks.
                - Only repair obvious extraction artifacts: missing spaces, bad line wraps,
                  broken hyphenation, stray control characters, and malformed paragraph breaks.
                - Preserve mathematical meaning and notation. If a formula is ambiguous, leave it as-is.
                - Do not invent new content, marks, or labels.
                """
            ).strip(),
            user_prompt=dedent(
                f"""
                Assignment title: {assignment.title}
                Course: {assignment.course_name or "Not provided"}

                Return the same structure with cleaner text only:
                {json.dumps([part.model_dump() for part in question_set.parts], ensure_ascii=False)}
                """
            ).strip(),
        )
    except Exception:
        return question_set

    original_signature = [
        (part.part_type, normalize_source_label(part.source_label), part.parent_key or "")
        for part in question_set.parts
    ]
    repaired_signature = [
        (part.part_type, normalize_source_label(part.source_label), part.parent_key or "")
        for part in repaired.parts
    ]
    if original_signature != repaired_signature:
        return question_set

    return repaired


def format_question_label(question_part: QuestionPart):
    return question_part.source_label or question_part.part_key


def build_shared_context(question_part: QuestionPart):
    assignment = question_part.assignment
    group_key = question_part.parent_key or parent_label_from_source_label(question_part.source_label)
    blocks = []
    seen = set()

    def append_block(title: str, text: str):
        normalized = text.strip()
        if not normalized or normalized == question_part.text.strip():
            return
        if normalized in seen:
            return
        seen.add(normalized)
        blocks.append(f"{title}:\n{normalized}")

    if group_key:
        explicit_contexts = assignment.question_parts.filter(
            part_type=QuestionPart.PartType.CONTEXT,
            parent_key=group_key,
        ).exclude(id=question_part.id).order_by("display_order", "id")
        for context_part in explicit_contexts:
            append_block(f"Shared context {context_part.display_label}", context_part.text)

    question_text = question_part.text
    referenced_labels = {
        normalize_source_label(match.group("label"))
        for match in SPECIFIC_LABEL_REFERENCE_RE.finditer(question_text)
    }

    sibling_questions = assignment.question_parts.filter(
        part_type=QuestionPart.PartType.QUESTION,
    ).exclude(id=question_part.id)
    if group_key:
        sibling_questions = sibling_questions.filter(parent_key=group_key)
    sibling_questions = sibling_questions.order_by("display_order", "id")

    if referenced_labels:
        for sibling in sibling_questions:
            if normalize_source_label(sibling.source_label) in referenced_labels:
                append_block(f"Referenced question {sibling.display_label}", sibling.text)

    if SHARED_REFERENCE_RE.search(question_text) and group_key:
        previous_sibling = (
            assignment.question_parts.filter(
                part_type=QuestionPart.PartType.QUESTION,
                parent_key=group_key,
                display_order__lt=question_part.display_order,
            )
            .exclude(id=question_part.id)
            .order_by("-display_order", "-id")
            .first()
        )
        first_sibling = (
            assignment.question_parts.filter(
                part_type=QuestionPart.PartType.QUESTION,
                parent_key=group_key,
            )
            .exclude(id=question_part.id)
            .order_by("display_order", "id")
            .first()
        )
        if previous_sibling is not None:
            append_block(f"Previous part {previous_sibling.display_label}", previous_sibling.text)
        if first_sibling is not None:
            append_block(f"Shared group anchor {first_sibling.display_label}", first_sibling.text)

    return "\n\n".join(blocks).strip()


def generate_question_parts(assignment: Assignment):
    deterministic_result = parse_structured_pdf_questions(assignment)
    if deterministic_result is not None:
        return repair_generated_question_parts(assignment, deterministic_result)

    service = OpenAIChatService()
    focus_question_number = derive_focus_question_number(assignment)
    source_name = get_assignment_source_name(assignment) or "Not provided"
    normalized_text = normalize_assignment_text(assignment.raw_assignment_text)

    return service.parse(
        user=assignment.teacher,
        operation="question_generation",
        model=QUESTION_MODEL,
        response_format=GeneratedQuestionSetSchema,
        system_prompt=dedent(
            """
            You convert assignment text into structured grading question parts.

            Goals:
            - Preserve the original hierarchy and numbering.
            - Produce shared context entries when multiple subparts rely on the same setup.
            - Be conservative and literal with math-heavy documents.

            Rules:
            - Never invent sections, questions, context, or marks that are not present.
            - Keep the source numbering in source_label exactly as closely as possible, such as
              1, 1.1, 1.2, (a), or (b). Do not flatten 1.1 and 1.2 into 1 and 2.
            - Use parent_key for the shared top-level group, such as 1 for 1.1 and 1.2.
            - Create a context part when there is shared setup, notation, definitions, or a stem
              that later subparts depend on.
            - If the first subpart introduces a shared object like a function, matrix, dataset, or
              optimization problem that later parts reference, keep that shared setup accessible by
              emitting a context part for the parent group.
            - Do not create context entries for due dates, submission instructions, section titles,
              or notes like "each part is worth 3 points".
            - Remove answer blanks such as "Answer: TODO".
            - If marks are shared across subparts, assign that shared mark value to each graded part.
            - Repair obvious PDF extraction artifacts conservatively: fix broken spacing, line wraps,
              and hyphenation, but preserve mathematical meaning.
            - Prefer fewer, high-precision question parts over many speculative ones.
            """
        ).strip(),
        user_prompt=dedent(
            f"""
            Assignment title: {assignment.title}
            Course: {assignment.course_name or "Not provided"}
            Description: {assignment.description or "Not provided"}
            Source filename: {source_name}
            Focus hint: {f"Extract only top-level question {focus_question_number} and its subparts." if focus_question_number else "No explicit focus hint."}

            Raw assignment text:
            {normalized_text}
            """
        ).strip(),
    )


def generate_reference_answer(assignment: Assignment, question_part: QuestionPart):
    service = OpenAIChatService()
    shared_context = build_shared_context(question_part)
    question_label = format_question_label(question_part)
    return service.parse(
        user=assignment.teacher,
        operation="reference_answer",
        model=ARTIFACT_MODEL,
        response_format=GeneratedReferenceAnswerSchema,
        system_prompt=dedent(
            """
            You write concise, high-quality model answers for instructor grading workflows.
            Produce a reference answer that would help a teacher grade strong student work.
            Keep it structured, focused, and proportional to the available marks.
            """
        ).strip(),
        user_prompt=dedent(
            f"""
            Assignment title: {assignment.title}
            Course: {assignment.course_name or "Not provided"}
            Question label: {question_label}
            Internal key: {question_part.part_key}
            Question text:
            {question_part.text}

            Shared context for this question group:
            {shared_context or "None"}

            Max marks: {question_part.max_marks if question_part.max_marks is not None else "Not specified"}
            """
        ).strip(),
    )


def generate_rubric_criteria(question_part: QuestionPart, reference_answer_text: str):
    service = OpenAIChatService()
    shared_context = build_shared_context(question_part)
    question_label = format_question_label(question_part)
    return service.parse(
        user=question_part.assignment.teacher,
        operation="rubric_generation",
        model=ARTIFACT_MODEL,
        response_format=GeneratedRubricSchema,
        system_prompt=dedent(
            """
            You produce concise grading criteria for a single question part.
            Create criteria that are concrete, instructor-friendly, and suitable for an MVP grading tool.
            If max marks are provided, keep the total criterion points aligned as closely as possible.
            """
        ).strip(),
        user_prompt=dedent(
            f"""
            Question label: {question_label}
            Internal key: {question_part.part_key}
            Question text:
            {question_part.text}

            Shared context for this question group:
            {shared_context or "None"}

            Max marks: {question_part.max_marks if question_part.max_marks is not None else "Not specified"}

            Reference answer:
            {reference_answer_text}
            """
        ).strip(),
    )
