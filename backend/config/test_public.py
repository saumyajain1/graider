from pathlib import Path

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


@override_settings(
    FRONTEND_DIST_DIR=Path("/nonexistent/frontend"),
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    },
)
class PublicPageTests(SimpleTestCase):
    def test_home_is_public_and_describes_the_app_without_javascript(self):
        response = self.client.get(reverse("public-home"))
        self.assertContains(response, "Grade thoughtfully.")
        self.assertContains(response, "Prepare an assignment")
        self.assertContains(response, 'href="/privacy/"')
        self.assertNotContains(response, "<script")

    def test_privacy_is_public_and_explains_google_data_and_deletion(self):
        response = self.client.get(reverse("privacy"))
        self.assertContains(response, "Google sign-in and account linking")
        self.assertContains(response, "does not request access to Gmail")
        self.assertContains(response, "Retention and deletion")
        self.assertContains(response, "mailto:saumyajain1403@gmail.com")
        self.assertNotContains(response, "{%")
