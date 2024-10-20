import reflex as rx
from ...ui.base import base_page


# Event handler to process the student's answer submission
def handle_answer_submission(answer: str):
    """Process the student's answer submission."""
    # Here you can add logic to store the answer or send it to the backend
    # For now, let's print the answer or display a confirmation message
    print(f"Answer submitted: {answer}")
    # You could also return a message or state update for feedback to the user
    return rx.text(f"Answer submitted: {answer}", color="green")


def render_header():
    """Render the header section with student ID and name aligned to the left."""
    return rx.box(
        rx.heading(
            "ST001",
            font_weight="700",
            font_size="2.25rem",
            line_height="2.5rem",
            color="#2563EB",
            as_="h1",
        ),
        rx.heading(
            "Rishav Sidhu",
            font_size="1.5rem",
            line_height="2rem",
            color="#374151",
            as_="h2",
        ),
        rx.box(
            rx.text(
                "Pending",
                font_size="1.25rem",
                line_height="2rem",
                color="#92400E",
            ),
            background_color="#FDE68A",  # Yellow background
            padding_left="0.75rem",
            padding_right="0.75rem",
            padding_top="0.25rem",
            padding_bottom="0.25rem",
            border_radius="9999px",  # Fully rounded corners
            display="inline-block",  # Fit to text size
        ),
        margin_bottom="2.5rem",
        text_align="left",  # Ensure the text is aligned to the left
        display="flex",
        flex_direction="column",  # Stack the headings on top of each other
        align_items="flex-start",  # Align the content to the start (left)
    )


def render_header():
    """Render the header section with student ID and name aligned to the left."""
    return rx.box(
        rx.heading(
            "ST001",
            font_weight="700",
            font_size="2.25rem",
            line_height="2.5rem",
            color="#2563EB",
            as_="h1",
        ),
        rx.heading(
            "Rishav Sidhu",
            font_size="1.5rem",
            line_height="2rem",
            color="#374151",
            as_="h2",
        ),
        rx.box(
            rx.text(
                "Pending",
                font_size="1.25rem",
                line_height="2rem",
                color="#92400E",
            ),
            background_color="#FDE68A",  # Yellow background
            padding_left="0.75rem",
            padding_right="0.75rem",
            padding_top="0.25rem",
            padding_bottom="0.25rem",
            border_radius="9999px",  # Fully rounded corners
            display="inline-block",  # Fit to text size
        ),
        margin_bottom="2.5rem",
        text_align="left",  # Ensure the text is aligned to the left
        display="flex",
        flex_direction="column",  # Stack the headings on top of each other
        align_items="flex-start",  # Align the content to the start (left)
    )


def render_question_paper(answer_state: rx.State):
    """Render the question paper display area with text input for student answers."""
    return rx.box(
        rx.text(
            "Student's answer:",
            color="#6B7280",
            font_size="1.25rem",
            line_height="1.75rem",
            margin_bottom="1rem",
        ),
        rx.el.textarea(
            placeholder="Type your answer here...",
            rows=10,  # Adjust the number of rows for a bigger text area
            border_width="1px",
            border_color="#E5E7EB",
            padding="0.75rem",
            width="100%",  # Make the text area take the full width of the box
            border_radius="0.25rem",
            _focus={
                "outline-style": "none",
                "box-shadow": "var(--tw-ring-inset) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color)",
                "--ring-color": "#3B82F6",
            },
            # Bind the textarea value to answer_state
            value=answer_state.value,
            on_change=answer_state.set_value,  # Update the state when the textarea changes
        ),
        rx.el.button(
            "Submit Answer",
            on_click=lambda: handle_answer_submission(answer_state.value),
            background_color="#3B82F6",
            color="white",
            padding="0.5rem 1rem",
            border_radius="0.25rem",
            _hover={"background_color": "#2563EB"},
            margin_top="1rem",
        ),
        class_name="h-[calc(100vh-200px)]",
        background_color="#ffffff",
        display="flex",
        flex_direction="column",
        padding="1.5rem",
        border_radius="0.5rem",
        box_shadow="0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    )


def render_file_upload():
    """Render file upload section for student answer sheets."""
    return rx.box(
        rx.text(
            "Upload Answer Sheets",
            font_size="1.25rem",
            margin_bottom="0.5rem",
        ),
        rx.el.input(
            type="file",
            multiple=False,  # To allow a single file at a time
            accept=".pdf,.jpg,.png",  # Accepting PDF, JPG, and PNG files
            padding="0.5rem",
            border="1px solid #E5E7EB",
            border_radius="0.25rem",
        ),
        margin_bottom="1.5rem",
    )


def render_message_input():
    """Render the input field for user messages."""
    return rx.el.input(
        type="text",
        placeholder="Type your message...",
        border_width="1px",
        flex_grow="1",
        _focus={
            "outline-style": "none",
            "box-shadow": "var(--tw-ring-inset) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color)",
            "--ring-color": "#3B82F6",
        },
        padding_left="0.5rem",
        padding_right="0.5rem",
        padding_top="0.25rem",
        padding_bottom="0.25rem",
        border_top_left_radius="0.25rem",
        border_bottom_left_radius="0.25rem",
    )


def render_file_upload():
    """Render file upload section for student answer sheets."""
    return rx.box(
        rx.text(
            "Upload Answer Sheets",
            font_size="1.25rem",
            margin_bottom="0.5rem",
        ),
        rx.el.input(
            type="file",
            multiple=False,  # To allow a single file at a time
            accept=".pdf,.jpg,.png",  # Accepting PDF, JPG, and PNG files
            padding="0.5rem",
            border="1px solid #E5E7EB",
            border_radius="0.25rem",
        ),
        margin_bottom="1.5rem",
    )


def render_send_button():
    """Render the send button for the chat interface."""
    return rx.el.button(
        rx.icon(
            alt="Send",
            tag="send",
            height="1.25rem",
            display="inline-block",
            width="1.25rem",
        ),
        background_color="#3B82F6",
        _focus={
            "outline-style": "none",
            "box-shadow": "var(--tw-ring-inset) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color)",
            "--ring-color": "#3B82F6",
        },
        _hover={"background-color": "#2563EB"},
        padding_left="1rem",
        padding_right="1rem",
        padding_top="0.25rem",
        padding_bottom="0.25rem",
        border_top_right_radius="0.25rem",
        border_bottom_right_radius="0.25rem",
        color="#ffffff",
    )


# Event handler to process the student's answer submission
def handle_answer_submission(answer: str):
    """Process the student's answer submission."""
    # Here you can add logic to store the answer or send it to the backend
    # For now, let's print the answer or display a confirmation message
    print(f"Answer submitted: {answer}")
    # You could also return a message or state update for feedback to the user
    return rx.text(f"Answer submitted: {answer}", color="green")


def render_header():
    """Render the header section with student ID and name aligned to the left."""
    return rx.box(
        rx.heading(
            "ST001",
            font_weight="700",
            font_size="2.25rem",
            line_height="2.5rem",
            color="#2563EB",
            as_="h1",
        ),
        rx.heading(
            "Rishav Sidhu",
            font_size="1.5rem",
            line_height="2rem",
            color="#374151",
            as_="h2",
        ),
        rx.box(
            rx.text(
                "Pending",
                font_size="1.25rem",
                line_height="2rem",
                color="#92400E",
            ),
            background_color="#FDE68A",  # Yellow background
            padding_left="0.75rem",
            padding_right="0.75rem",
            padding_top="0.25rem",
            padding_bottom="0.25rem",
            border_radius="9999px",  # Fully rounded corners
            display="inline-block",  # Fit to text size
        ),
        margin_bottom="2.5rem",
        text_align="left",  # Ensure the text is aligned to the left
        display="flex",
        flex_direction="column",  # Stack the headings on top of each other
        align_items="flex-start",  # Align the content to the start (left)
    )


def render_question_paper():
    """Render the question paper display area with text input for student answers."""
    return rx.box(
        rx.text(
            "Student's answer:",
            color="#6B7280",
            font_size="1.25rem",
            line_height="1.75rem",
            margin_bottom="1rem",
        ),
        rx.el.textarea(
            placeholder="Type your answer here...",
            rows=10,  # Adjust the number of rows for a bigger text area
            border_width="1px",
            border_color="#E5E7EB",
            padding="0.75rem",
            width="100%",  # Make the text area take the full width of the box
            border_radius="0.25rem",
            _focus={
                "outline-style": "none",
                "box-shadow": "var(--tw-ring-inset) 0 0 0 calc(2px + var(--tw-ring-offset-width)) var(--tw-ring-color)",
                "--ring-color": "#3B82F6",
            },
            # Bind the textarea value to answer_state
            # value=answer_state.value,
            # on_change=answer_state.set_value,  # Update the state when the textarea changes
        ),
        rx.el.button(
            "Submit Answer",
            # on_click=lambda: handle_answer_submission(answer_state.value),
            background_color="#3B82F6",
            color="white",
            padding="0.5rem 1rem",
            border_radius="0.25rem",
            _hover={"background_color": "#2563EB"},
            margin_top="1rem",
        ),
        class_name="h-[calc(100vh-200px)]",
        background_color="#ffffff",
        display="flex",
        flex_direction="column",
        padding="1.5rem",
        border_radius="0.5rem",
        box_shadow="0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    )


def render_file_upload():
    """Render file upload section for student answer sheets."""
    return rx.box(
        rx.text(
            "Upload Answer Sheets",
            font_size="1.25rem",
            margin_bottom="0.5rem",
        ),
        rx.el.input(
            type="file",
            multiple=False,  # To allow a single file at a time
            accept=".pdf,.jpg,.png",  # Accepting PDF, JPG, and PNG files
            padding="0.5rem",
            border="1px solid #E5E7EB",
            border_radius="0.25rem",
        ),
        margin_bottom="1.5rem",
    )


def render_chatbot_messages():
    """Render the area where chatbot messages will be displayed."""
    return rx.box(
        rx.text(
            "Your grading feedback will appear here.",
            color="#4B5563",
        ),
        class_name="h-[calc(100%-60px)]",
        border_width="1px",
        border_color="#E5E7EB",
        margin_bottom="1rem",
        overflow_y="auto",
        padding="0.5rem",
        border_radius="0.25rem",
    )


def render_chatbot_interface():
    """Render the complete chatbot interface including messages, input, and send button."""
    return rx.box(
        rx.heading(
            "Analysis Chatbot",
            font_weight="600",
            margin_bottom="1rem",
            font_size="1.125rem",
            line_height="1.75rem",
            as_="h3",
        ),
        render_chatbot_messages(),
        rx.flex(
            render_message_input(),
            render_send_button(),
            display="flex",
        ),
        class_name="h-[calc(100vh-200px)]",
        background_color="#ffffff",
        padding="2.75rem",
        border_radius="0.5rem",
        box_shadow="0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
    )


def review_page() -> rx.Component:
    """Display the student's submission and allow grading."""
    # Retrieve student_id from kwargs
    # student_id = kwargs.get('student_id', 'Unknown')
    student_id = "ST001"
    # print(student_id)

    child_page = rx.box(
        render_header(),
        rx.flex(
            rx.box(
                render_question_paper(),
                render_file_upload(),  # Include file upload section here
                padding_right="1.5rem",
                width="95%",
            ),
            rx.box(render_chatbot_interface(), width="55%"),
            display="flex",
        ),
        width="100%",
        style=rx.breakpoints(
            {
                "640px": {"max-width": "640px"},
                "768px": {"max-width": "768px"},
                "1024px": {"max-width": "1024px"},
                "1280px": {"max-width": "1280px"},
                "1536px": {"max-width": "1536px"},
            }
        ),
        margin_left="auto",
        margin_right="auto",
        padding="1.5rem",
    )
    return base_page(child_page)
