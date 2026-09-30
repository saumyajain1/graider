import logging
from contextlib import contextmanager
from pathlib import PurePath
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.http import FileResponse, Http404, HttpResponseRedirect
from django.urls import reverse
from django.utils.http import content_disposition_header
from rest_framework.exceptions import APIException

logger = logging.getLogger(__name__)


class UploadTooLarge(APIException):
    status_code = 413
    default_detail = "Upload exceeds the configured limit."
    default_code = "upload_too_large"


def original_name(uploaded_file):
    return PurePath(uploaded_file.name.replace("\\", "/")).name[:255]


def object_key(prefix, filename):
    extension = PurePath(filename).suffix.lower()
    return f"{prefix}/{uuid4().hex}{extension}"


def check_file_size(uploaded_file, limit, label="File"):
    if uploaded_file.size > limit:
        raise UploadTooLarge(f"{label} exceeds the {limit:,}-byte limit.")


def check_text_length(value, limit, label="Text"):
    if len(value) > limit:
        raise UploadTooLarge(f"{label} exceeds the {limit:,}-character limit.")


def check_submission_capacity(assignment, new_count=1):
    if assignment.submissions.count() + new_count > settings.GRAIDER_MAX_SUBMISSIONS_PER_ASSIGNMENT:
        raise UploadTooLarge(
            f"Assignment exceeds the {settings.GRAIDER_MAX_SUBMISSIONS_PER_ASSIGNMENT}-submission limit."
        )


@contextmanager
def stored_upload(field_file, uploaded_file):
    """Save an object before the DB write and remove it if that write fails."""
    requested_name = field_file.field.generate_filename(
        field_file.instance, original_name(uploaded_file)
    )
    saved_name = None
    try:
        saved_name = field_file.storage.save(
            requested_name, uploaded_file, max_length=field_file.field.max_length
        )
        field_file.name = saved_name
        field_file._committed = True
        setattr(field_file.instance, field_file.field.attname, saved_name)
        yield
    except Exception:
        cleanup_name = saved_name or requested_name
        try:
            field_file.storage.delete(cleanup_name)
        except Exception:
            logger.exception("Could not clean up failed upload %s", cleanup_name)
        raise


def delete_upload_after_commit(field_file):
    if field_file and field_file.name:
        delete_name_after_commit(field_file.storage, field_file.name)


def delete_name_after_commit(storage, name):
    if not name:
        return

    def delete():
        try:
            storage.delete(name)
        except Exception:
            logger.exception("Could not delete uploaded object %s", name)

    transaction.on_commit(delete)


def private_file_response(field_file, filename):
    if not field_file:
        raise Http404("File not found.")
    if settings.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage":
        url = field_file.storage.url(
            field_file.name,
            parameters={"ResponseContentDisposition": content_disposition_header(True, filename)},
        )
        return HttpResponseRedirect(url)
    return FileResponse(field_file.open("rb"), as_attachment=True, filename=filename)


def file_api_url(name, **kwargs):
    return reverse(name, kwargs=kwargs)
