import reflex as rx
from . import routes

class NavState(rx.State):
  def to_about(self):
    return rx.redirect(routes.HOME_ROUTE)
  def to_perf_ans(self):
    return rx.redirect(routes.PERF_ANS_ROUTE)
  def to_questions(self):
    return rx.redirect(routes.QUES_ROUTE)
  def to_rubric(self):
    return rx.redirect(routes.RUBRIC_ROUTE)
  def to_settings(self):
    return rx.redirect(routes.SETTINGS_ROUTE)
  def to_students(self):
    return rx.redirect(routes.STUDENTS_ROUTE)