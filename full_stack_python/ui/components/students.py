import reflex as rx
from ...ui.base import base_page


def create_section_heading(heading_text):
    """Create a section heading with specified text."""
    return rx.heading(
        heading_text,
        font_weight="600",
        margin_bottom="1rem",
        font_size="1.25rem",
        line_height="1.75rem",
        as_="h3",
    )


def create_styled_text(
        text_color, font_size, line_height, text_content
):
    """Create styled text with specified color, font size, and line height."""
    return rx.text(
        text_content,
        font_weight="700",
        font_size=font_size,
        line_height=line_height,
        color=text_color,
    )


def create_action_button(
        hover_styles, bg_color, text_color, button_text
):
    """Create an action button with specified styles and text."""
    return rx.el.button(
        button_text,
        background_color=bg_color,
        transition_duration="300ms",
        _hover=hover_styles,
        padding_left="0.75rem",
        padding_right="0.75rem",
        padding_top="0.25rem",
        padding_bottom="0.25rem",
        border_radius="0.25rem",
        color=text_color,
        transition_property="background-color, border-color, color, fill, stroke, opacity, box-shadow, transform",
        transition_timing_function="cubic-bezier(0.4, 0, 0.2, 1)",
    )


def create_action_cell(
        hover_styles, bg_color, text_color, button_text
):
    """Create a table cell with an action button."""
    return rx.table.cell(
        create_action_button(
            hover_styles=hover_styles,
            bg_color=bg_color,
            text_color=text_color,
            button_text=button_text,
        ),
        padding="0.75rem",
    )


def create_action_link(
        hover_styles, bg_color, text_color, button_text, student_id
):
    """Create an action button as a link that navigates to the review page."""
    return rx.link(
        button_text,
        href=f"/students/{student_id}",  # Link to the review page with the student's ID
        style={
            "background_color": bg_color,
            "transition_duration": "300ms",
            "padding_left": "0.75rem",
            "padding_right": "0.75rem",
            "padding_top": "0.25rem",
            "padding_bottom": "0.25rem",
            "border_radius": "0.25rem",
            "color": text_color,
            "transition_property": "background-color, border-color, color, fill, stroke, opacity, box-shadow, transform",
            "transition_timing_function": "cubic-bezier(0.4, 0, 0.2, 1)",
            "_hover": hover_styles,
        }
    )

def create_action_cell(
        hover_styles, bg_color, text_color, button_text, student_id
):

    return rx.table.cell(
        create_action_link(
            hover_styles=hover_styles,
            bg_color=bg_color,
            text_color=text_color,
            button_text=button_text,
            student_id=student_id,  # Pass student_id to the action link
        ),
        padding="0.75rem",
    )


def create_table_body():
    """Create the table body with sample data rows."""
    return rx.table.body(
        rx.table.row(
            create_table_cell(cell_content="ST001"),
            create_table_cell(
                cell_content="Rishav Sidhu"
            ),
            create_table_cell(
                cell_content="-"
            ),
            create_status_cell(
                bg_color="#FDE68A",
                text_color="#92400E",
                status_text="Pending",
            ),
            create_action_cell(
                hover_styles={
                    "background-color": "#2563EB"
                },
                bg_color="#3B82F6",
                text_color="#ffffff",
                button_text="Review",
                student_id="ST001",  # Pass student ID here for the review page
            ),
            border_bottom_width="1px",
        ),
        rx.table.row(
            create_table_cell(cell_content="ST002"),
            create_table_cell(
                cell_content="Saumya Jain"
            ),
            create_table_cell(
                cell_content="91"
            ),
            create_status_cell(
                bg_color="#A7F3D0",
                text_color="#065F46",
                status_text="Graded",
            ),
            create_action_cell(
                hover_styles={
                    "background-color": "#9CA3AF"
                },
                bg_color="#D1D5DB",
                text_color="#1F2937",
                button_text="View",
                student_id="ST002",
            ),
            border_bottom_width="1px",
        ),
        rx.table.row(
            create_table_cell(cell_content="ST003"),
            create_table_cell(
                cell_content="Nabeel Ali"
            ),
            create_table_cell(
                cell_content="85"
            ),
            create_status_cell(
                bg_color="#FECACA",
                text_color="#991B1B",
                status_text="Late",
            ),
            create_action_cell(
                hover_styles={
                    "background-color": "#2563EB"
                },
                bg_color="#3B82F6",
                text_color="#ffffff",
                button_text="Review",
                student_id="ST003",
            ),
        ),
    )


def create_table_cell(cell_content):
    """Create a table cell with specified content."""
    return rx.table.cell(cell_content, padding="0.75rem")


def create_status_badge(bg_color, text_color, status_text):
    """Create a status badge with specified background color, text color, and status text."""
    return rx.text.span(
        status_text,
        background_color=bg_color,
        padding_left="0.5rem",
        padding_right="0.5rem",
        padding_top="0.25rem",
        padding_bottom="0.25rem",
        border_radius="9999px",
        font_size="0.875rem",
        line_height="1.25rem",
        color=text_color,
    )


def create_status_cell(bg_color, text_color, status_text):
    """Create a table cell with a status badge."""
    return rx.table.cell(
        create_status_badge(
            bg_color=bg_color,
            text_color=text_color,
            status_text=status_text,
        ),
        padding="0.75rem",
    )


def create_stat_box(
        title, value_color, value
):
    """Create a stat box with a title and colored value."""
    return rx.box(
        create_section_heading(heading_text=title),
        create_styled_text(
            text_color=value_color,
            font_size="2.25rem",
            line_height="2.5rem",
            text_content=value,
        ),
        background_color="#ffffff",
        padding="1.5rem",
        border_radius="0.5rem",
        box_shadow="0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
    )


def create_table_header_cell(cell_content):
    """Create a table header cell with specified content."""
    return rx.table.column_header_cell(
        cell_content, padding="0.75rem", text_align="left"
    )


def create_submissions_table():
    """Create the submissions table with header and body."""
    return rx.table.root(
        rx.table.header(
            rx.table.row(
                create_table_header_cell(
                    cell_content="Student ID"
                ),
                create_table_header_cell(
                    cell_content="Student Name"
                ),
                create_table_header_cell(
                    cell_content="Score"
                ),
                create_table_header_cell(
                    cell_content="Status"
                ),
                create_table_header_cell(
                    cell_content="Action"
                ),
                background_color="#F3F4F6",
            )
        ),
        create_table_body(),
        width="100%",
    )


def create_label_text(
        text_color, font_size, line_height, label_text
):
    """Create label text with specified color, font size, and line height."""
    return rx.text(
        label_text,
        color=text_color,
        font_size=font_size,
        line_height=line_height,
    )


def create_accuracy_display():
    """Create the AI grading accuracy display."""
    return rx.box(
        rx.text(
            "80%",
            font_weight="700",
            font_size="1.875rem",
            line_height="2.25rem",
        ),
        create_label_text(
            text_color="#6B7280",
            font_size="0.875rem",
            line_height="1.25rem",
            label_text="Mean",
        ),
        class_name="transform",
        transform="translateY(-50%) translateX(-50%)",
        position="absolute",
        left="50%",
        text_align="center",
        top="50%",
    )


def create_time_saved_display():
    """Create the grading time saved display."""
    return rx.flex(
        rx.box(
            create_styled_text(
                text_color="#059669",
                font_size="3rem",
                line_height="1",
                text_content="18.5",
            ),
            create_label_text(
                text_color="#4B5563",
                font_size="1.25rem",
                line_height="1.75rem",
                label_text="Hours",
            ),
            rx.text(
                "This month",
                margin_top="0.5rem",
                color="#6B7280",
                font_size="0.875rem",
                line_height="1.25rem",
            ),
            text_align="relative",
        ),
        display="flex",
        height="16rem",
        align_items="center",
        justify_content="center",
    )


def students_page() -> rx.Component:
    # Welcome Page (Index)
    my_child = rx.vstack(
        rx.heading("Students Database", size="9"),
        rx.box(
            rx.box(
                create_stat_box(
                    title="Total Students",
                    value_color="#2563EB",
                    value="28",
                ),
                create_stat_box(
                    title="No. of Students Graded",
                    value_color="#059669",
                    value="13",
                ),
                create_stat_box(
                    title="Pending Grading Left",
                    value_color="#B22222",
                    value="15",
                ),
                gap="1.5rem",
                display="grid",
                grid_template_columns=rx.breakpoints(
                    {
                        "0px": "repeat(1, minmax(0, 1fr))",
                        "768px": "repeat(3, minmax(0, 1fr))",
                    }
                ),
                margin_bottom="2rem",
            ),
            rx.box(
                create_section_heading(
                    heading_text="Submissions"
                ),
                create_submissions_table(),
                background_color="#ffffff",
                margin_bottom="2rem",  # Ensure there’s enough margin at the bottom
                padding="1.5rem",
                border_radius="0.5rem",
                box_shadow="0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
            ),
            rx.box(
                create_section_heading(
                    heading_text="Grading At a Glance"
                ),
                rx.flex(
                    rx.box(
                        create_section_heading(
                            heading_text="Class Mean"
                        ),
                        create_accuracy_display(),
                        height="12rem",
                        position="relative",
                        width="12rem",
                        text_align="center",  # Center-align the content within the box
                        margin_right="2rem",  # Add spacing between the two boxes
                    ),
                    rx.box(
                        create_section_heading(
                            heading_text="AI Grading Accuracy"
                        ),
                        create_time_saved_display(),  # Your custom function to display time saved
                        height="12rem",
                        position="relative",
                        width="12rem",
                        text_align="center",  # Center-align the content within the box
                    ),
                    display="flex",
                    justify_content="center",  # Centers the boxes horizontally
                    align_items="center",  # Ensures both boxes are vertically aligned
                    gap="3rem",  # Adds space between the two boxes
                ),
                background_color="#ffffff",
                padding="1.5rem",
                margin_top="1rem",  # Add margin to separate it from previous boxes
                border_radius="0.5rem",
                box_shadow="0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)",
            ),
        )
    ),
    return base_page(my_child)
