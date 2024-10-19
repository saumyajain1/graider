import reflex as rx
from ...ui.base import base_page


def review_page() -> rx.Component:
    """Display the student's submission and allow grading."""
    # Retrieve student_id from kwargs
    # student_id = kwargs.get('student_id', 'Unknown')
    student_id = "ST001"
    print(student_id)

    child_page = rx.vstack(
        rx.heading(f"Review Submission for {student_id}", size="9"),
        rx.text(f"Submission details for student {student_id} will be shown here."),
        rx.text_area(
            placeholder="Enter your feedback...",
            width="100%",
            height="10rem",
            margin_bottom="1rem",
            resize="vertical",
        ),
        rx.button(
            "Submit Grade",
            background_color="#3B82F6",
            color="white",
            _hover={"background_color": "#2563EB"},
            margin_top="1rem",
        ),
    )
    return base_page(child_page)
