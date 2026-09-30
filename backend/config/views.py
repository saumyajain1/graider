from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.views.decorators.http import require_safe


@require_safe
def health(request):
    response = JsonResponse({"status": "ok"})
    response["Cache-Control"] = "no-store"
    return response


@require_safe
def spa_index(request):
    index_path = settings.FRONTEND_DIST_DIR / "index.html"
    if not index_path.is_file():
        raise Http404("Frontend build is unavailable.")
    response = FileResponse(index_path.open("rb"), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-store"
    return response
