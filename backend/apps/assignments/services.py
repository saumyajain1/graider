import re
import unicodedata

from pypdf import PdfReader

SUPPORTED_TEXT_UPLOAD_EXTENSIONS = (".txt", ".pdf")

QUESTION_LABEL_LINE_RE = re.compile(
    r"^\s*(?:\[?\d+(?:\.\d+)*\]?|(?:question|q)\s*\d+)(?:[.)]|\s)",
    re.IGNORECASE,
)
MATH_HEAVY_LINE_RE = re.compile(r"(?:=|≥|≤|∈|∥|Σ|∑|λ|\^|[_{}]|[A-Za-z]\([^)]+\))")
PAGE_NUMBER_RE = re.compile(r"^\s*\d+\s*$")

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


def should_join_lines(previous_line: str, current_line: str):
    if not previous_line or not current_line:
        return False
    if QUESTION_LABEL_LINE_RE.match(current_line):
        return False
    if MATH_HEAVY_LINE_RE.search(previous_line) or MATH_HEAVY_LINE_RE.search(current_line):
        return False
    if previous_line.endswith((".", "?", "!", ":", "]")):
        return False
    if current_line[:1].islower():
        return True
    if previous_line[-1:].islower() and current_line[:1].islower():
        return True
    return False


def normalize_extracted_assignment_text(raw_text: str):
    text = unicodedata.normalize("NFKC", raw_text or "")
    for old, new in UNICODE_REPLACEMENTS.items():
        text = text.replace(old, new)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)

    normalized_lines = []
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if PAGE_NUMBER_RE.match(line or ""):
            continue
        if not line:
            if normalized_lines and normalized_lines[-1]:
                normalized_lines.append("")
            continue
        if normalized_lines and should_join_lines(normalized_lines[-1], line):
            normalized_lines[-1] = f"{normalized_lines[-1]} {line}"
            continue
        normalized_lines.append(line)

    while normalized_lines and normalized_lines[-1] == "":
        normalized_lines.pop()

    return "\n".join(normalized_lines).strip()


def extract_text_from_uploaded_file(uploaded_file):
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".txt"):
        uploaded_file.seek(0)
        extracted_text = uploaded_file.read().decode("utf-8", errors="ignore").strip()
        uploaded_file.seek(0)
        return normalize_extracted_assignment_text(extracted_text), ""

    if file_name.endswith(".pdf"):
        try:
            uploaded_file.seek(0)
            reader = PdfReader(uploaded_file)
            extracted_text = "\n\n".join(
                (page.extract_text() or "").strip()
                for page in reader.pages
                if (page.extract_text() or "").strip()
            ).strip()
            uploaded_file.seek(0)
            if extracted_text:
                return (
                    normalize_extracted_assignment_text(extracted_text),
                    "PDF text was normalized conservatively. Complex math may still need a manual pass.",
                )
            return "", "PDF upload succeeded, but no extractable text was found."
        except Exception as exc:  # pragma: no cover - defensive fallback
            uploaded_file.seek(0)
            return "", f"PDF extraction failed: {exc}"

    return "", "Only .txt and .pdf files are supported for assignment uploads."


def is_supported_text_upload(uploaded_file):
    return uploaded_file.name.lower().endswith(SUPPORTED_TEXT_UPLOAD_EXTENSIONS)
