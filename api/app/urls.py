import os
from django.contrib import admin
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, re_path, include
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView
from pathlib import Path
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from app.errors import error_response
from accounts.views import MeView, DebugTokenObtainPairView, RegisterView, ThrottledTokenObtainPairView
from rest_framework.routers import DefaultRouter
from proposals.views import ProposalViewSet
from proposals.views import SectionPromotionView
from orgs.views import OrganizationViewSet, OrgInviteAcceptView
from ai import views as ai_views
from exports import views as export_views
from files import views as files_views
from accounts.oauth import google_start, google_callback, github_start, github_callback, facebook_start, facebook_callback


def healthz(_request):
    return HttpResponse("ok")


@api_view(["GET"])
@permission_classes([AllowAny])
def api_healthz(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def api_health(_request):
    return Response({"status": "ok"})


@api_view(["GET"])
@permission_classes([AllowAny])
def api_ready(_request):
    db_ok = False
    cache_ok = False
    details = {}
    try:
        from django.db import connections
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        db_ok = True
    except Exception as exc:
        details["db_error"] = str(exc)[:200]
    try:
        from django.core.cache import cache
        test_key = "ready_probe"
        cache.set(test_key, "1", 5)
        val = cache.get(test_key)
        cache_ok = val == "1"
    except Exception as exc:
        details["cache_error"] = str(exc)[:200]
    status = "ok" if db_ok else "error"
    payload = {"status": status, "db": db_ok, "cache": cache_ok, "details": details}
    if status == "error":
        err = error_response("ready_check_failed", "One or more readiness checks failed", status=503, meta=payload)
        return err
    return Response(payload)


router = DefaultRouter()
router.register(r"proposals", ProposalViewSet, basename="proposal")
router.register(r"orgs", OrganizationViewSet, basename="org")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz", healthz),
    path("api/healthz", api_healthz),
    path("api/health", api_health),
    path("api/ready", api_ready),
    path("api/me", MeView.as_view()),
    path("api/register", RegisterView.as_view()),
    path("api/token", DebugTokenObtainPairView.as_view() if settings.DEBUG else ThrottledTokenObtainPairView.as_view()),
    path("api/token/refresh", TokenRefreshView.as_view()),
    path("api/oauth/google/start", google_start),
    path("api/oauth/google/callback", google_callback),
    path("api/oauth/github/start", github_start),
    path("api/oauth/github/callback", github_callback),
    path("api/oauth/facebook/start", facebook_start),
    path("api/oauth/facebook/callback", facebook_callback),
    path("api/exports", export_views.create_export),
    path("api/exports/<int:job_id>", export_views.get_export),
    path("api/exports/<int:job_id>/download", export_views.download_export),
    path("api/files", files_views.upload),
    path("api/ai/proposals/<int:proposal_id>/setup", ai_views.project_setup),
    path("api/ai/plan", ai_views.plan),
    path("api/ai/grill", ai_views.grill),
    path("api/ai/intake", ai_views.intake),
    path("api/ai/intake/grill", ai_views.intake_grill),
    path("api/ai/intake/consensus", ai_views.intake_consensus_view),
    path("api/ai/grant-packs/<int:version_id>/review", ai_views.grant_pack_review),
    path("api/ai/proposals/<int:proposal_id>/evidence-review", ai_views.proposal_evidence_review),
    path("api/ai/proposals/<int:proposal_id>/claim-decision", ai_views.proposal_claim_decision),
    path("api/ai/proposals/<int:proposal_id>/rule-pack-drafts", ai_views.proposal_rule_pack_draft),
    path("api/ai/claim-plan", ai_views.claim_plan),
    path("api/ai/claim-plan/confirm", ai_views.claim_plan_confirm),
    path("api/ai/sections/<int:section_id>/writer-context", ai_views.section_writer_context),
    path("api/ai/sections/<int:section_id>/review", ai_views.section_review),
    path("api/ai/sections/<int:section_id>/review-grill", ai_views.section_review_grill),
    path("api/ai/review-grill/answer", ai_views.review_grill_answer),
    path("api/ai/sections/<int:section_id>/review-revise", ai_views.section_review_revise),
    path("api/ai/workflow/run", ai_views.workflow_run),
    path("api/ai/human-tasks", ai_views.human_tasks),
    path("api/ai/human-tasks/<int:task_id>/pre-review", ai_views.human_task_pre_review),
    path("api/ai/human-tasks/<int:task_id>/decision", ai_views.human_task_decision),
    path("api/ai/proposals/<int:proposal_id>/full-draft", ai_views.full_draft),
    path("api/ai/write", ai_views.write),
    path("api/ai/sections/<int:section_id>/evidence", ai_views.section_evidence),
    path("api/ai/sections/<int:section_id>/draft", ai_views.save_section_draft),
    path("api/ai/sections/<int:section_id>/reopen", ai_views.reopen_section),
    path("api/ai/revise", ai_views.revise),
    path("api/ai/format", ai_views.format),
    path("api/ai/jobs/<int:job_id>", ai_views.job_status),
    path("api/ai/runs/<uuid:run_id>", ai_views.run_timeline),
    path("api/ai/metrics/recent", ai_views.metrics_recent),
    path("api/ai/metrics/summary", ai_views.metrics_summary),
    path("api/ai/memory/suggestions", ai_views.memory_suggestions),
    path("api/sections/<str:section_id>/promote", SectionPromotionView.as_view()),
    path("api/orgs/invites/accept", OrgInviteAcceptView.as_view({"post": "create"})),
    path("api/", include(router.urls)),
    re_path(r"^$", lambda r: _root_entrypoint(r)),
    re_path(r"^app/?$", lambda _r: _serve_spa_index()),
    re_path(r"^app/.*$", lambda _r: _serve_spa_index()),
]

if settings.DEBUG or os.getenv("SERVE_MEDIA", "0") == "1":
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


def _serve_spa_index():
    candidate_paths = [
        Path(settings.STATIC_ROOT) / "app" / "index.html",
        Path(settings.BASE_DIR) / "staticfiles" / "app" / "index.html",
    ]
    for p in candidate_paths:
        try:
            text = p.read_text(encoding="utf-8")
            return HttpResponse(text, content_type="text/html; charset=utf-8")
        except Exception:
            continue
    return HttpResponse("SPA not built yet. API is up.", content_type="text/plain; charset=utf-8")


def _serve_landing_index():
    candidate_paths = [
        Path(settings.STATIC_ROOT) / "index.html",
        Path(settings.BASE_DIR) / "staticfiles" / "index.html",
    ]
    for p in candidate_paths:
        try:
            text = p.read_text(encoding="utf-8")
            return HttpResponse(text, content_type="text/html; charset=utf-8")
        except Exception:
            continue
    return HttpResponse("Landing not bundled. API is up.", content_type="text/plain; charset=utf-8")


def _root_entrypoint(request):
    host = (request.get_host() or "").split(":")[0].lower()
    from django.conf import settings as _s
    if host and getattr(_s, "APP_HOSTS", None):
        if host in _s.APP_HOSTS:
            return HttpResponseRedirect("/app")
    return _serve_landing_index()
