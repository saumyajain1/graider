import json
import subprocess
import sys
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, SimpleTestCase, TestCase, override_settings
from drf_spectacular.generators import EndpointEnumerator, SchemaGenerator

from apps.assignments.models import Assignment
from apps.assignments.serializers import AssignmentSerializer


@override_settings(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
)
class GeneratedSchemaTests(SimpleTestCase):
    def setUp(self):
        self.schema = SchemaGenerator().get_schema(request=None, public=True)

    def test_every_api_handler_is_documented_without_database_or_ai(self):
        with patch("apps.grading.services.openai_client.OpenAI") as ai:
            call_command("spectacular", validate=True, fail_on_warn=True, stdout=StringIO())
            ai.assert_not_called()
        for path, path_regex, method, callback in EndpointEnumerator().get_api_endpoints():
            if path in ("/api/schema/", "/api/docs/"):
                continue
            with self.subTest(path=path, method=method):
                self.assertIn(method.lower(), self.schema["paths"][path])

    def test_response_fields_follow_runtime_serializer_and_separate_upload_inputs(self):
        components = self.schema["components"]["schemas"]
        serializer = AssignmentSerializer()
        expected = {name for name, field in serializer.fields.items() if not field.write_only}
        self.assertEqual(set(components["Assignment"]["properties"]), expected)
        upload = components["AssignmentRequest"]["properties"]["source_file"]
        self.assertEqual(upload["format"], "binary")
        self.assertNotIn("source_file", components["Assignment"]["properties"])
        self.assertNotIn("status", components["AssignmentRequest"]["properties"])
        self.assertEqual(
            components["Assignment"]["properties"]["question_count"]["type"], "integer"
        )
        self.assertTrue(components["LoginRequest"]["properties"]["password"]["writeOnly"])
        self.assertNotIn("password", components["User"]["properties"])

    def test_a_runtime_serializer_field_change_updates_the_schema(self):
        code = (
            "import django; django.setup(); "
            "from apps.assignments.serializers import AssignmentSerializer; "
            "AssignmentSerializer.Meta.fields += ('teacher',); "
            "from drf_spectacular.generators import SchemaGenerator; "
            "schema = SchemaGenerator().get_schema(request=None, public=True); "
            "assert 'teacher' in schema['components']['schemas']['Assignment']['properties']"
        )
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(
            "teacher", self.schema["components"]["schemas"]["Assignment"]["properties"]
        )

    def test_envelopes_binary_downloads_and_empty_requests_match_api(self):
        paths = self.schema["paths"]
        operation = paths["/api/assignments/{assignment_id}/grade-all"]["post"]
        self.assertNotIn("requestBody", operation)
        self.assertEqual(
            set(operation["responses"]), {"200", "400", "403", "404", "409", "429", "502", "503"}
        )
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]
        component = self.schema["components"]["schemas"][response["$ref"].rsplit("/", 1)[-1]]
        self.assertEqual(
            set(component["properties"]), {"graded_count", "failed_count", "submissions"}
        )
        download = paths["/api/assignments/{assignment_id}/export.csv"]["get"]
        self.assertEqual(
            download["responses"]["200"]["content"]["text/csv"]["schema"]["format"], "binary"
        )
        csv = paths["/api/assignments/{assignment_id}/submissions/import-csv"]["post"]
        self.assertIn("multipart/form-data", csv["requestBody"]["content"])
        self.assertEqual(
            paths["/api/auth/logout"]["post"]["responses"]["204"],
            {"description": "No response body"},
        )
        self.assertEqual(paths["/api/assignments/"]["get"]["security"], [{"cookieAuth": []}])

    def test_docs_are_public_with_local_assets_and_csrf_cookie(self):
        response = self.client.get("/api/docs/", HTTP_HOST="localhost")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)
        html = response.content.decode()
        self.assertIn("/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle", html)
        self.assertNotIn("cdn.jsdelivr", html)
        schema = self.client.get(
            "/api/schema/", HTTP_ACCEPT="application/json", HTTP_HOST="localhost"
        )
        self.assertEqual(schema.status_code, 200)
        self.assertEqual(schema.json()["info"]["title"], "Graider API")


@override_settings(
    STORAGES={"staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}
)
class SwaggerSessionTests(TestCase):
    def test_csrf_rotation_and_teacher_scope_apply_to_docs_requests(self):
        user = get_user_model().objects.create_user(
            email="docs@example.test", password="DocsTest2026!"
        )
        other = get_user_model().objects.create_user(
            email="other@example.test", password="DocsTest2026!"
        )
        foreign = Assignment.objects.create(
            teacher=other, title="Other teacher", raw_assignment_text="Q1"
        )
        client = Client(enforce_csrf_checks=True, HTTP_HOST="localhost")
        token = client.get("/api/docs/").cookies["csrftoken"].value
        login = client.post(
            "/api/auth/login",
            json.dumps({"email": user.email, "password": "DocsTest2026!"}),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login.status_code, 200)
        rotated_token = client.cookies["csrftoken"].value
        self.assertNotEqual(token, rotated_token)
        payload = json.dumps({"title": "Docs assignment", "raw_assignment_text": "Q1"})
        self.assertEqual(
            client.post("/api/assignments/", payload, content_type="application/json").status_code,
            403,
        )
        self.assertEqual(
            client.post(
                "/api/assignments/",
                payload,
                content_type="application/json",
                HTTP_X_CSRFTOKEN=token,
            ).status_code,
            403,
        )
        created = client.post(
            "/api/assignments/",
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=rotated_token,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(client.get(f"/api/assignments/{foreign.id}").status_code, 404)
        self.assertEqual(
            client.get("/api/schema/", HTTP_ACCEPT="application/json").status_code, 200
        )
