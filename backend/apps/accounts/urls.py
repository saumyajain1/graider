from django.urls import path

from .views import AuthOptionsView, GoogleStartView, LoginView, LogoutView, MeView, RegisterView

urlpatterns = [
    path("register", RegisterView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
    path("options", AuthOptionsView.as_view(), name="auth-options"),
    path("google", GoogleStartView.as_view(), name="google-start"),
]
