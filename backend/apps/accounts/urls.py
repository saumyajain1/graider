from django.urls import path

from .views import (
    AuthOptionsView,
    DisconnectAccountView,
    GoogleStartView,
    LoginView,
    LogoutView,
    MeView,
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    ProfileUpdateView,
    RegisterView,
)

urlpatterns = [
    path("profile", ProfileUpdateView.as_view(), name="profile-update"),
    path("password/change", PasswordChangeView.as_view(), name="password-change"),
    path("password/reset", PasswordResetRequestView.as_view(), name="password-reset"),
    path(
        "password/reset/confirm", PasswordResetConfirmView.as_view(), name="password-reset-confirm"
    ),
    path("accounts/disconnect", DisconnectAccountView.as_view(), name="account-disconnect"),
    path("register", RegisterView.as_view(), name="register"),
    path("login", LoginView.as_view(), name="login"),
    path("logout", LogoutView.as_view(), name="logout"),
    path("me", MeView.as_view(), name="me"),
    path("options", AuthOptionsView.as_view(), name="auth-options"),
    path("google", GoogleStartView.as_view(), name="google-start"),
]
