from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, BasePermission
from rest_framework.response import Response
from django.conf import settings
from .sanitize import sanitize_text, sanitize_url, sanitize_answers, sanitize_file_refs
import time
from .models import AIJob, AIMetric, AIJobContext, WorkflowRun, EvidenceUsage, HumanApprovalTask
from .section_pipeline import get_section
from .tasks import run_plan, run_write, run_revise, run_format
from .provider import get_provider
from .diff_engine import diff_texts
from .validators import SchemaError, invalid_output_error, section_draft, validate_role_output
from .workflow import persist_graph_result, resolve_run_id
from django.db.models import QuerySet
from typing import Optional
from orgs.models import Organization
from billing.quota import get_subscription_for_scope
from django.utils import timezone
from .decorators import ai_protected
from django.db import models
from app.common.keys import t
from proposals.models import Proposal, ProposalSection
from proposals.finalization import SectionsNotApproved, build_approved_markdown
from .writer_evidence import parse_writer_result, persist_evidence_usage, render_writer_contexts, retrieve_writer_evidence
from .query_router import persist_dual_retrieval_trace
from .services import ServiceError, finalize_service, plan_service, revise_service, write_service
from .grill import answer as answer_grill, confirm as confirm_grill, get_session, planning_context, serialize as serialize_grill
from .grill import finish as finish_grill
from .intake import answer_node, consensus as intake_consensus, next_node, question_card, start_intake, work_plan_preview
from .claim_planning import confirm_claim_plan, create_claim_plan, serialize_claim_plan
from .reviewing import answer_review_grill, apply_local_revision, prepare_writer_run, run_review, start_review_grill
from .models import ClaimPlan, GrillSession, ProposalIntakeProfile, GrantPackVersion
from .phase12 import create_custom_pack_draft, decide_claim, serialize_evidence_review, serialize_pack_review, update_evidence_review, update_pack_review
from .proposal_graph import run_proposal_graph
from .hitl import HUMAN_ACTIONS, HUMAN_NODES, resume_human_task, start_human_task
from django.db import transaction
import logging


logger = logging.getLogger(__name__)


def _get_accessible_proposal(request, proposal_id: int) -> Optional[Proposal]:
    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return None
    qs = Proposal.objects.filter(id=proposal_id).filter(
        models.Q(org__admin=user) | models.Q(org__memberships__user=user)
    )
    org_id = request.META.get('HTTP_X_ORG_ID', '')
    if org_id and str(org_id).isdigit():
        qs = qs.filter(org_id=int(org_id))
    return qs.distinct().first()


class DebugOrAuthPermission(BasePermission):
    """Allow all when DEBUG is True; otherwise require authentication.

    This avoids import-time binding of settings.DEBUG in decorators so tests
    that override settings can influence permission evaluation.
    """

    def has_permission(self, request, view):  # type: ignore[override]
        # Allow anonymous in DEBUG or when test-open flag is enabled
        if settings.DEBUG or getattr(settings, 'AI_TEST_OPEN', False):
            return True
        return IsAuthenticated().has_permission(request, view)


def _compute_rate_limits(tier: str) -> int:
    """Return max requests per minute for the given tier.

    Defaults:
      - free: 0 (blocked by gating already)
      - pro: 20 rpm
      - enterprise: 60 rpm
    Overridable via settings: AI_RATE_PER_MIN_FREE/PRO/ENTERPRISE
    """
    tier_key = (tier or 'pro').lower()
    if tier_key == 'enterprise':
        return int(getattr(settings, 'AI_RATE_PER_MIN_ENTERPRISE', 60) or 60)
    if tier_key == 'free':
        return int(getattr(settings, 'AI_RATE_PER_MIN_FREE', 0) or 0)
    return int(getattr(settings, 'AI_RATE_PER_MIN_PRO', 20) or 20)


def _rate_limit_check(request, endpoint_type: str) -> Optional[Response]:
    """Enforce AI usage limits (rpm + daily requests + monthly tokens) by tier.

    Order:
      1. Skip if DEBUG and no explicit enforcement.
      2. Per-minute rate limit (existing behavior).
      3. Daily request cap (if configured).
      4. Monthly token cap (if configured) - evaluated on write/revise/format only.

    Returns Response(429) when any limit exceeded; else None.
    """
    # Allow explicit enforcement in DEBUG when AI_ENFORCE_RATE_LIMIT_DEBUG=1
    if settings.DEBUG and not getattr(settings, 'AI_ENFORCE_RATE_LIMIT_DEBUG', False):
        return None
    user = getattr(request, 'user', None)
    if not getattr(user, 'is_authenticated', False):
        return None  # gating handles unauthorized
    # Determine org scope for tier
    org: Optional[Organization] = None
    org_id = request.META.get('HTTP_X_ORG_ID', '')
    if org_id and str(org_id).isdigit():
        try:
            org = Organization.objects.filter(id=int(org_id)).first()
        except Exception:
            org = None
    tier, _status = get_subscription_for_scope(user, org)
    limit = _compute_rate_limits(tier)
    if limit <= 0:
        # No per-minute limit, still enforce daily/monthly caps below
        pass
    # Fast cache precheck (token bucket style approximate counter)
    if limit > 0:
        try:
            from django.core.cache import cache

            uid = getattr(user, 'id', None)
            if uid is not None:
                bucket_key = f'ai_rl:{endpoint_type}:{uid}:{int(time.time()//60)}'
                current = cache.get(bucket_key)
                if current is None:
                    cache.add(bucket_key, 0, 65)  # expire slightly over 60s window
                    current = 0
                if isinstance(current, int) and current >= limit:
                    resp = Response(
                        {
                            'error': 'rate_limited',
                            'retry_after': 30,
                            'message': t('errors.ai.rate_limited', retry_after=30),
                        },
                        status=429,
                    )
                    resp['Retry-After'] = '30'
                    resp['X-Rate-Limit-Limit'] = str(limit)
                    resp['X-Rate-Limit-Remaining'] = '0'
                    return resp
                # Increment optimistically (best-effort; ignore race conditions)
                try:
                    cache.incr(bucket_key)
                except Exception:
                    cache.set(bucket_key, int(current) + 1, 65)
        except Exception:
            pass  # fallback silently to DB metric counting
    # Count metrics in the last 60 seconds for this user and endpoint type
    from .models import AIMetric

    now = timezone.now()
    one_min_ago = now - timezone.timedelta(seconds=60)
    if limit > 0:
        recent = AIMetric.objects.filter(
            created_by=user,
            type=endpoint_type,
            created_at__gte=one_min_ago,
        ).count()
        if recent >= limit:
            retry_after = 30
            resp = Response(
                {
                    'error': 'rate_limited',
                    'retry_after': retry_after,
                    'message': t('errors.ai.rate_limited', retry_after=retry_after),
                },
                status=429,
            )
            resp['Retry-After'] = str(retry_after)
            resp['X-Rate-Limit-Limit'] = str(limit)
            resp['X-Rate-Limit-Remaining'] = '0'
            return resp
        # Attach remaining header for observability
        remaining = max(limit - recent - 1, 0)
        request.META['AI_RATE_LIMIT_REMAINING'] = remaining  # can be surfaced later if needed

    # --- Daily request cap ---
    # Settings: AI_DAILY_REQUEST_CAP_FREE/PRO/ENTERPRISE (None/0 => disabled)
    start_day = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tier_lower = tier.lower()
    daily_cap_setting = None
    if tier_lower == 'free':
        daily_cap_setting = getattr(settings, 'AI_DAILY_REQUEST_CAP_FREE', None)
    elif tier_lower == 'enterprise':
        daily_cap_setting = getattr(settings, 'AI_DAILY_REQUEST_CAP_ENTERPRISE', None)
    else:
        daily_cap_setting = getattr(settings, 'AI_DAILY_REQUEST_CAP_PRO', None)
    try:
        daily_cap = int(daily_cap_setting) if daily_cap_setting not in (None, '') else None
    except Exception:
        daily_cap = None
    if daily_cap and daily_cap > 0:
        day_count = AIMetric.objects.filter(created_by=user, created_at__gte=start_day).count()
        if day_count >= daily_cap:
            resp = Response(
                {
                    'error': 'quota_exceeded',
                    'reason': 'ai_daily_request_cap',
                    'retry_after': 3600,
                    'message': t('errors.ai.quota_daily_reached'),
                },
                status=429,
            )
            resp['X-AI-Daily-Cap'] = str(daily_cap)
            resp['X-AI-Daily-Used'] = str(day_count)
            return resp

    # --- Monthly token cap --- (write/revise/format only; planning negligible)
    if endpoint_type in ('write', 'revise', 'format'):
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_cap_setting = None
        if tier_lower == 'enterprise':
            monthly_cap_setting = getattr(settings, 'AI_MONTHLY_TOKENS_CAP_ENTERPRISE', None)
        else:  # pro & free (free already blocked elsewhere)
            monthly_cap_setting = getattr(settings, 'AI_MONTHLY_TOKENS_CAP_PRO', None)
        try:
            monthly_cap = int(monthly_cap_setting) if monthly_cap_setting not in (None, '') else None
        except Exception:
            monthly_cap = None
        if monthly_cap and monthly_cap > 0:
            token_sum = (
                AIMetric.objects.filter(created_by=user, created_at__gte=month_start)
                .aggregate(total=models.Sum('tokens_used'))  # type: ignore[name-defined]
                .get('total')
                or 0
            )
            if token_sum >= monthly_cap:
                resp = Response(
                    {
                        'error': 'quota_exceeded',
                        'reason': 'ai_monthly_tokens_cap',
                        'message': t('errors.ai.quota_monthly_tokens_reached'),
                    },
                    status=429,
                )
                resp['X-AI-Monthly-Token-Cap'] = str(monthly_cap)
                resp['X-AI-Monthly-Token-Used'] = str(token_sum)
                return resp
    return None


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
@ai_protected('plan', plan_gate=False)
def plan(request):
    # Sanitize inputs to reduce prompt-injection vectors and invalid URLs
    grant_url = sanitize_url(request.data.get('grant_url'))
    text_spec = sanitize_text(request.data.get('text_spec'), max_len=4000)
    proposal_id_raw = request.data.get('proposal_id')
    if proposal_id_raw is None:
        return Response({'error': 'proposal_id_required'}, status=400)
    try:
        proposal_id = int(proposal_id_raw)
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    planning_session = dict((proposal.content or {}).get('grill', {}).get('planning') or {})
    if planning_session and not planning_session.get('confirmed'):
        return Response({'error': 'grill_confirmation_required'}, status=409)
    confirmed_context = planning_context(proposal)
    if confirmed_context:
        text_spec = '\n\n[confirmed_grill_answers]\n' + confirmed_context + ('\n\n' + text_spec if text_spec else '')
    run_id = resolve_run_id(request.data.get('run_id'), proposal_id=proposal.id, org_id=request.META.get('HTTP_X_ORG_ID', ''), provider=getattr(settings, 'AI_PROVIDER', ''))
    async_enabled = getattr(settings, 'AI_ASYNC', False) and settings.CELERY_BROKER_URL
    if async_enabled:
        job = AIJob.objects.create(
            type='plan',
            input_json={
                'proposal_id': proposal.id,
                'grant_url': grant_url or None,
                'text_spec': text_spec or None,
            },
            created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
            org_id=request.META.get('HTTP_X_ORG_ID', ''),
            run_id=run_id,
        )
        run_plan.delay(job.id)  # type: ignore[attr-defined]
        return Response({'job_id': job.id, 'status': job.status, 'run_id': str(run_id)})  # type: ignore[attr-defined]
    provider = get_provider(getattr(settings, 'AI_PROVIDER', None))
    t0 = time.time()
    try:
        plan_result = provider.plan(grant_url=grant_url or None, text_spec=text_spec or None)
    except Exception:  # noqa: BLE001
        logger.exception('AI provider.plan failed')
        return Response(
            {
                'error': 'ai_provider_error',
                'message': t('errors.ai.provider_failed'),
            },
            status=502,
        )
    try:
        validate_role_output('plan', plan_result)
    except SchemaError as error:
        return Response({'error': invalid_output_error(error).as_dict()}, status=502)
    dt_ms = int((time.time() - t0) * 1000)
    from .models import AIMetric

    blueprint = plan_result['sections']
    created_sections: list[str] = []
    if blueprint:
        try:
            created_sections = plan_service(proposal_id=proposal.id, blueprint=blueprint)
        except Exception as e:  # pragma: no cover
            created_sections = ['error:' + str(e)]
    AIMetric.objects.create(
        type='plan',
        model_id='planner.v1',
        duration_ms=dt_ms,
        tokens_used=0,
        created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
        org_id=request.META.get('HTTP_X_ORG_ID', ''),
        success=True,
        run_id=run_id,
    )
    return Response(
        {
            'schema_version': plan_result.get('schema_version', 'v1') if isinstance(plan_result, dict) else 'v1',
            'sections': blueprint,
            'created_sections': created_sections,
            'run_id': str(run_id),
        }
    )


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def grill(request):
    proposal_id_raw = request.query_params.get('proposal_id') if request.method == 'GET' else request.data.get('proposal_id')
    try:
        proposal_id = int(proposal_id_raw)
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    data = request.query_params if request.method == 'GET' else request.data
    mode = data.get('mode', 'planning')
    if mode not in ('planning', 'revision'):
        return Response({'error': 'grill_mode_invalid'}, status=400)
    section_key = sanitize_text(data.get('section_key'), max_len=128) if mode == 'revision' else ''
    section = None
    if mode == 'revision':
        section = get_section(section_key, proposal_id=proposal.id)
        if section is None:
            return Response({'error': 'section_not_found'}, status=404)
    session = get_session(proposal, mode=mode, section_key=section_key)
    if request.method == 'POST':
        if data.get('finish'):
            finish_grill(session)
        else:
            raw_answers = data.get('answers') or {}
            if not isinstance(raw_answers, dict):
                return Response({'error': 'grill_answers_invalid'}, status=400)
            answers = {str(key): sanitize_text(value, max_len=1000) for key, value in raw_answers.items()}
            answer_grill(session, answers, skip=bool(data.get('skip')))
        if data.get('confirm'):
            confirm_grill(session)
        proposal.save(update_fields=['content', 'last_edited'])
    else:
        proposal.save(update_fields=['content', 'last_edited'])
    draft = (section.draft_content or section.approved_content) if section is not None else ''
    return Response(serialize_grill(session, draft=draft))


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def intake(request):
    data = request.query_params if request.method == 'GET' else request.data
    if request.method == 'GET':
        try:
            session_id = int(data.get('session_id'))
        except (TypeError, ValueError):
            return Response({'error': 'session_id_invalid'}, status=400)
        session = GrillSession.objects.select_related('proposal', 'profile', 'policy').filter(pk=session_id).first()
        if session is None or _get_accessible_proposal(request, session.proposal_id) is None:
            return Response({'error': 'intake_session_not_found'}, status=404)
        return Response({'session_id': session.id, 'status': session.status, 'work_plan_preview': work_plan_preview(session), 'question_card': question_card(next_node(session))})
    try:
        proposal_id = int(data.get('proposal_id'))
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    task_mode = data.get('task_mode')
    quality_level = data.get('quality_level')
    if task_mode not in dict(ProposalIntakeProfile.TASK_MODE_CHOICES) or quality_level not in dict(ProposalIntakeProfile.QUALITY_LEVEL_CHOICES):
        return Response({'error': 'task_mode_or_quality_level_invalid'}, status=400)
    inputs = data.get('inputs') or {}
    overrides = data.get('user_overrides') or {}
    if not isinstance(inputs, dict) or not isinstance(overrides, dict):
        return Response({'error': 'intake_inputs_invalid'}, status=400)
    session = start_intake(proposal, task_mode=task_mode, quality_level=quality_level, inputs=inputs, user_overrides=overrides)
    return Response({'session_id': session.id, 'status': session.status, 'work_plan_preview': work_plan_preview(session), 'question_card': question_card(next_node(session))}, status=201)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def intake_grill(request):
    try:
        session_id = int(request.data.get('session_id'))
    except (TypeError, ValueError):
        return Response({'error': 'session_id_invalid'}, status=400)
    session = GrillSession.objects.select_related('proposal', 'profile', 'policy').filter(pk=session_id).first()
    if session is None or _get_accessible_proposal(request, session.proposal_id) is None:
        return Response({'error': 'intake_session_not_found'}, status=404)
    try:
        _, created = answer_node(
            session,
            node_id=sanitize_text(request.data.get('node_id'), max_len=64),
            action=request.data.get('action'),
            answer=sanitize_text(request.data.get('answer'), max_len=4000),
            idempotency_key=sanitize_text(request.data.get('idempotency_key'), max_len=128),
            user=request.user,
        )
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    session.refresh_from_db()
    return Response({'idempotent_replay': not created, 'status': session.status, 'question_card': question_card(next_node(session)), 'consensus_summary': intake_consensus(session)})


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def intake_consensus_view(request):
    data = request.query_params if request.method == 'GET' else request.data
    try:
        session_id = int(data.get('session_id'))
    except (TypeError, ValueError):
        return Response({'error': 'session_id_invalid'}, status=400)
    session = GrillSession.objects.select_related('proposal', 'profile', 'policy').filter(pk=session_id).first()
    if session is None or _get_accessible_proposal(request, session.proposal_id) is None:
        return Response({'error': 'intake_session_not_found'}, status=404)
    try:
        summary = intake_consensus(session, confirm=bool(data.get('confirm')) if request.method == 'POST' else False)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response(summary)


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def grant_pack_review(request, version_id):
    version = GrantPackVersion.objects.select_related('pack').filter(pk=version_id).first()
    if version is None:
        return Response({'error': 'grant_pack_version_not_found'}, status=404)
    organization_id = request.META.get('HTTP_X_ORG_ID', '')
    if version.pack.organization_id and version.pack.organization_id != str(organization_id):
        return Response({'error': 'grant_pack_not_found'}, status=404)
    if request.method == 'GET':
        return Response(serialize_pack_review(version))
    try:
        return Response(update_pack_review(version, request.data, request.user))
    except ValueError as error:
        return Response({'error': str(error)}, status=409)


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def proposal_evidence_review(request, proposal_id):
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    if request.method == 'GET':
        return Response(serialize_evidence_review(proposal))
    try:
        return Response(update_evidence_review(proposal, request.data, request.user))
    except ValueError as error:
        return Response({'error': str(error)}, status=409)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def proposal_claim_decision(request, proposal_id):
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    try:
        return Response(decide_claim(proposal, request.data))
    except ValueError as error:
        return Response({'error': str(error)}, status=409)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def proposal_rule_pack_draft(request, proposal_id):
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    try:
        return Response(create_custom_pack_draft(proposal, request.data), status=201)
    except (ValueError, TypeError) as error:
        return Response({'error': str(error)}, status=409)


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def claim_plan(request):
    if request.method == 'GET':
        try:
            plan_id = int(request.query_params.get('claim_plan_id'))
        except (TypeError, ValueError):
            return Response({'error': 'claim_plan_id_invalid'}, status=400)
        plan = ClaimPlan.objects.select_related('proposal').filter(pk=plan_id).first()
        if plan is None or _get_accessible_proposal(request, plan.proposal_id) is None:
            return Response({'error': 'claim_plan_not_found'}, status=404)
        return Response(serialize_claim_plan(plan))
    try:
        proposal_id = int(request.data.get('proposal_id'))
        pack_version_id = int(request.data.get('pack_version_id'))
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_or_pack_version_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    try:
        plan = create_claim_plan(proposal, pack_version_id=pack_version_id)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response(serialize_claim_plan(plan), status=201)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def claim_plan_confirm(request):
    try:
        plan_id = int(request.data.get('claim_plan_id'))
    except (TypeError, ValueError):
        return Response({'error': 'claim_plan_id_invalid'}, status=400)
    plan = ClaimPlan.objects.select_related('proposal').filter(pk=plan_id).first()
    if plan is None or _get_accessible_proposal(request, plan.proposal_id) is None:
        return Response({'error': 'claim_plan_not_found'}, status=404)
    try:
        plan = confirm_claim_plan(plan)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response(serialize_claim_plan(plan))


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def section_writer_context(request, section_id):
    section = ProposalSection.objects.select_related('proposal').filter(pk=section_id).first()
    if section is None or _get_accessible_proposal(request, section.proposal_id) is None:
        return Response({'error': 'section_not_found'}, status=404)
    try:
        run, _, _ = prepare_writer_run(section)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response({'writer_run_id': run.id, 'writing_mode': run.writing_mode, 'rule_evidence_ids': run.rule_context, 'user_evidence_ids': run.user_evidence_context, 'protected_facts': run.protected_facts, 'missing_evidence': run.missing_evidence})


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def section_review(request, section_id):
    section = ProposalSection.objects.select_related('proposal').filter(pk=section_id).first()
    if section is None or _get_accessible_proposal(request, section.proposal_id) is None:
        return Response({'error': 'section_not_found'}, status=404)
    try:
        issues = run_review(section)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response({'issues': [{'id': item.id, 'category': item.category, 'code': item.code, 'severity': item.severity, 'status': item.status, 'auto_fixable': item.auto_fixable} for item in issues]})


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def section_review_grill(request, section_id):
    section = ProposalSection.objects.select_related('proposal').filter(pk=section_id).first()
    if section is None or _get_accessible_proposal(request, section.proposal_id) is None:
        return Response({'error': 'section_not_found'}, status=404)
    try:
        session = start_review_grill(section)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response({'session_id': session.id, 'question_card': question_card(next_node(session))}, status=201)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def review_grill_answer(request):
    try:
        session = GrillSession.objects.select_related('proposal').get(pk=int(request.data.get('session_id')))
    except (TypeError, ValueError, GrillSession.DoesNotExist):
        return Response({'error': 'review_session_not_found'}, status=404)
    if _get_accessible_proposal(request, session.proposal_id) is None:
        return Response({'error': 'review_session_not_found'}, status=404)
    try:
        _, created = answer_review_grill(session, node_id=sanitize_text(request.data.get('node_id'), max_len=64), action=request.data.get('action'), answer=sanitize_text(request.data.get('answer'), max_len=4000), idempotency_key=sanitize_text(request.data.get('idempotency_key'), max_len=128), user=request.user)
    except ValueError as error:
        return Response({'error': str(error)}, status=409)
    return Response({'idempotent_replay': not created, 'question_card': question_card(next_node(session))})


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def section_review_revise(request, section_id):
    section = ProposalSection.objects.select_related('proposal').filter(pk=section_id).first()
    if section is None or _get_accessible_proposal(request, section.proposal_id) is None:
        return Response({'error': 'section_not_found'}, status=404)
    issue = section.review_issues.filter(pk=request.data.get('issue_id')).first() if request.data.get('issue_id') else None
    try:
        diff = apply_local_revision(section, revised_text=sanitize_text(request.data.get('revised_text'), max_len=20000, neutralize_injection=False), issue=issue, user_id=request.user.id if request.user.is_authenticated else None)
    except (ValueError, ServiceError) as error:
        return Response({'error': str(error)}, status=409)
    return Response({'diff': diff})


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def workflow_run(request):
    try:
        proposal_id = int(request.data.get('proposal_id'))
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    section_key = sanitize_text(request.data.get('section_key'), max_len=128)
    if not section_key:
        return Response({'error': 'section_key_required'}, status=400)
    plan = request.data.get('plan') or []
    if not isinstance(plan, list):
        return Response({'error': 'plan_invalid'}, status=400)
    if plan:
        try:
            validate_role_output('plan', {'schema_version': 'v1', 'sections': plan})
        except SchemaError as error:
            return Response({'error': invalid_output_error(error).as_dict()}, status=400)
    review_queue = request.data.get('review_queue') or []
    if not isinstance(review_queue, list) or not all(isinstance(item, dict) for item in review_queue):
        return Response({'error': 'review_queue_invalid'}, status=400)
    run_id = resolve_run_id(
        request.data.get('run_id'),
        proposal_id=proposal.id,
        org_id=request.META.get('HTTP_X_ORG_ID', ''),
    )
    state = run_proposal_graph({
        'run_id': str(run_id),
        'thread_id': sanitize_text(request.data.get('thread_id'), max_len=128) or f'proposal-{proposal.id}',
        'organization_id': str(proposal.org_id),
        'proposal_id': proposal.id,
        'section_key': section_key,
        'plan': plan,
        'answers': sanitize_answers(request.data.get('answers') or {}),
        'evidence_ids': [str(item)[:128] for item in (request.data.get('evidence_ids') or [])[:20]],
        'draft': sanitize_text(request.data.get('draft'), max_len=20000, neutralize_injection=False),
        'review': request.data.get('review') if isinstance(request.data.get('review'), dict) else {},
        'review_queue': review_queue[:5],
        'max_revisions': max(1, min(int(request.data.get('max_revisions', 2) or 2), 5)),
        'resume_after_approval': bool(request.data.get('resume_after_approval')),
    })
    persist_graph_result(run_id, state)
    return Response({
        'run_id': state['run_id'],
        'status': state['status'],
        'review': state.get('review') or {},
        'error': state.get('error') or '',
        'trace': state['trace'],
        'final_markdown': state.get('final_markdown') or '',
    })


def _human_task_payload(task):
    return {
        'id': task.id,
        'thread_id': task.thread_id,
        'node': task.node,
        'status': task.status,
        'input': task.input_json,
        'model_output': task.model_output_json,
        'decision': task.decision_json,
    }


@api_view(['GET', 'POST'])
@permission_classes([DebugOrAuthPermission])
def human_tasks(request):
    if request.method == 'GET':
        try:
            proposal_id = int(request.query_params.get('proposal_id'))
        except (TypeError, ValueError):
            return Response({'error': 'proposal_id_invalid'}, status=400)
        if _get_accessible_proposal(request, proposal_id) is None:
            return Response({'error': 'proposal_not_found'}, status=404)
        tasks = HumanApprovalTask.objects.filter(proposal_id=proposal_id, status='pending').order_by('created_at')
        return Response({'tasks': [_human_task_payload(task) for task in tasks]})
    try:
        proposal_id = int(request.data.get('proposal_id'))
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    node = sanitize_text(request.data.get('node'), max_len=64)
    if node not in HUMAN_NODES:
        return Response({'error': 'human_node_invalid'}, status=400)
    run_id = resolve_run_id(request.data.get('run_id'), proposal_id=proposal.id, org_id=str(proposal.org_id))
    thread_id = sanitize_text(request.data.get('thread_id'), max_len=128) or f'{run_id}:{node}'
    task, created = HumanApprovalTask.objects.get_or_create(
        thread_id=thread_id,
        defaults={
            'workflow_run': WorkflowRun.objects.get(run_id=run_id),
            'proposal_id': proposal.id,
            'node': node,
            'input_json': request.data.get('input') if isinstance(request.data.get('input'), dict) else {},
            'model_output_json': request.data.get('model_output') if isinstance(request.data.get('model_output'), dict) else {},
        },
    )
    if not created:
        return Response(_human_task_payload(task))
    start_human_task({
        'thread_id': thread_id,
        'human_node': node,
        'human_input': task.input_json,
        'model_output': task.model_output_json,
    })
    return Response(_human_task_payload(task), status=201)


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
def human_task_decision(request, task_id: int):
    with transaction.atomic():
        task = HumanApprovalTask.objects.select_for_update().filter(id=task_id).first()
        if task is None or _get_accessible_proposal(request, task.proposal_id) is None:
            return Response({'error': 'human_task_not_found'}, status=404)
        if task.status != 'pending':
            return Response({'error': 'human_task_already_decided'}, status=409)
        thread_id = sanitize_text(request.data.get('thread_id'), max_len=128)
        if thread_id != task.thread_id:
            return Response({'error': 'thread_id_mismatch'}, status=400)
        action = sanitize_text(request.data.get('action'), max_len=16)
        if action not in HUMAN_ACTIONS:
            return Response({'error': 'human_action_invalid'}, status=400)
        edited_input = request.data.get('edited_input') if isinstance(request.data.get('edited_input'), dict) else {}
        result = resume_human_task(task.thread_id, {'action': action, 'edited_input': edited_input})
        task.status = result['status']
        task.decision_json = {'action': action, 'edited_input': edited_input}
        task.decided_by = request.user if request.user.is_authenticated else None
        task.decided_at = timezone.now()
        task.save(update_fields=['status', 'decision_json', 'decided_by', 'decided_at'])
    return Response(_human_task_payload(task))


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
@ai_protected('write', plan_gate=True)
def write(request):
    section_id = sanitize_text(request.data.get('section_id'), max_len=128)
    proposal_id = None
    try:
        if request.data.get('proposal_id') is not None:
            proposal_id = int(request.data.get('proposal_id'))
    except Exception:
        proposal_id = None
    section = None
    if proposal_id is not None:
        proposal = _get_accessible_proposal(request, proposal_id)
        if proposal is None:
            return Response({'error': 'proposal_not_found'}, status=404)
        section = get_section(section_id, proposal_id=proposal.id)
        if section is None:
            return Response({'error': 'section_not_found'}, status=404)
        if section.locked:
            return Response({'error': 'section_locked'}, status=409)
    run_id = resolve_run_id(request.data.get('run_id'), proposal_id=proposal_id, org_id=request.META.get('HTTP_X_ORG_ID', ''), provider=getattr(settings, 'AI_PROVIDER', ''))
    answers = sanitize_answers(request.data.get('answers', {}))
    file_refs = sanitize_file_refs(request.data.get('file_refs', []))
    async_enabled = getattr(settings, 'AI_ASYNC', False) and settings.CELERY_BROKER_URL
    if async_enabled:
        job = AIJob.objects.create(
            type='write',
            input_json={
                'proposal_id': proposal_id,
                'section_id': section_id,
                'answers': answers,
                'file_refs': file_refs,
            },
            created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
            org_id=request.META.get('HTTP_X_ORG_ID', ''),
            run_id=run_id,
        )
        # Ensure background path does not break test expecting second call limited (guard already set)
        try:  # pragma: no cover - safety
            run_write.delay(job.id)  # type: ignore[attr-defined]
        except Exception:
            # Fallback: run synchronously if Celery misconfigured in test
            provider = get_provider(getattr(settings, 'AI_PROVIDER', None))
            provider.write(section_id=section_id, answers=answers, file_refs=file_refs or None)
        return Response({'job_id': job.id, 'status': job.status, 'run_id': str(run_id)})  # type: ignore[attr-defined]
    provider = get_provider(getattr(settings, 'AI_PROVIDER', None))
    t0 = time.time()
    # Fetch memory suggestions (user or org scope) to enrich context (not persisted provider-side yet)
    # (Memory suggestions reserved hook: intentionally skipped until provider contract extended)
    # For now don't mutate answers type contract; future: provider may accept context param.
    # Enrich with memory suggestions (non-persisted prompt context) under reserved key
    try:
        from .models import AIMemory  # local import to avoid cycles

        org_scope = request.META.get('HTTP_X_ORG_ID', '')
        if request.user.is_authenticated:
            mem_items = AIMemory.suggestions(user=request.user, org_id=org_scope, section_id=section_id or None, limit=3)
            if mem_items:
                context_lines = [f"{m['key']}: {m['value'][:400]}" for m in mem_items]
                # Use reserved underscore key so it is ignored for memory recording (see record loop below)
                answers['_memory_context'] = '[context:memory]\n' + '\n'.join(context_lines)
    except Exception:
        pass
    # Deterministic sampling: allow request override; default from settings
    deterministic_setting = getattr(settings, 'AI_DETERMINISTIC_SAMPLING', True)
    try:
        deterministic_default = bool(False if str(deterministic_setting) in ('0', 'false', 'False') else deterministic_setting)
    except Exception:
        deterministic_default = True
    deterministic_req = request.data.get('deterministic') if isinstance(request.data, dict) else None
    if deterministic_req is not None:
        try:
            deterministic = bool(False if str(deterministic_req) in ('0', 'false', 'False') else deterministic_req)
        except Exception:
            deterministic = deterministic_default
    else:
        deterministic = deterministic_default
    if section is not None:
        review_evidence = list(EvidenceUsage.objects.filter(proposal_section=section, role='writer', used_in_prompt=True).order_by('-created_at', 'rank')[:5])
        if review_evidence:
            change_request += '\n\n[review_evidence]\n' + '\n'.join(
                f'[{item.chunk_id}] {item.document_name_snapshot} p.{item.page_start_snapshot}-{item.page_end_snapshot}: {item.snapshot_text}'
                for item in review_evidence
            )
    try:
        writer_run = None
        if section is not None:
            try:
                writer_run, rule_context, user_evidence_context = prepare_writer_run(section)
                answers['_protected_facts'] = '\n'.join(writer_run.protected_facts)
                answers['_missing_evidence'] = '\n'.join(writer_run.missing_evidence)
                answers['_pack_version_id'] = str(writer_run.section_plan.claim_plan.pack_version_id)
                answers['_year'] = str(writer_run.section_plan.claim_plan.pack_version.year)
            except ValueError:
                writer_run = None
        contexts = retrieve_writer_evidence(
            section_id,
            answers=answers,
            organization_id=request.META.get('HTTP_X_ORG_ID', ''),
            proposal_id=proposal_id,
        )
        if writer_run is None:
            rule_context, user_evidence_context = render_writer_contexts(contexts)
        workflow_run = WorkflowRun.objects.filter(run_id=run_id).first()
        persist_dual_retrieval_trace(workflow_run, contexts.result)
        res = provider.write(
            section_id=section_id,
            answers=answers,
            file_refs=file_refs or None,
            deterministic=deterministic,
            rule_context=rule_context,
            user_evidence_context=user_evidence_context,
        )  # type: ignore[arg-type]
    except Exception:
        logger.exception('AI provider.write failed')
        return Response({'error': 'ai_provider_error', 'message': t('errors.ai.provider_failed')}, status=502)
    try:
        draft = parse_writer_result(section_id, res.text, contexts.allowed_chunk_ids)
    except SchemaError as error:
        return Response({'error': invalid_output_error(error).as_dict()}, status=502)
    if section is not None:
        write_service(section=section, draft_markdown=draft['draft_markdown'], answers=answers)
        persist_evidence_usage(
            section=section,
            job=None,
            run=workflow_run,
            role='writer',
            query=contexts.query,
            candidates=contexts.rule_candidates + contexts.user_evidence_candidates,
            cited_chunk_ids=draft['evidence_ids'],
            retrieval_run_id=contexts.result.retrieval_run_id,
        )
    # (single-write marker already set at entry)
    dt_ms = int((time.time() - t0) * 1000)
    from .models import AIMetric

    # Persist answer memory (best-effort; ignore failures)
    try:  # pragma: no cover - side effect; minimal tests may stub
        from .models import AIMemory

        org_scope = request.META.get('HTTP_X_ORG_ID', '')
        if request.user.is_authenticated:
            for k, v in answers.items():
                if not k.startswith('_') and v:
                    AIMemory.record(user=request.user, org_id=org_scope, section_id=section_id or '', key=k, value=str(v)[:2000])
    except Exception:
        pass
    AIMetric.objects.create(
        type='write',
        model_id=res.model_id,
        duration_ms=dt_ms,
        tokens_used=res.usage_tokens,
        proposal_id=proposal_id,
        section_id=section_id,
        created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
        org_id=request.META.get('HTTP_X_ORG_ID', ''),
        success=True,
        run_id=run_id,
    )
    evidence = [{
        'chunk_id': item['chunk_id'],
        'rank': item['final_rank'],
        'document_name': item['document_name'],
        'page_start': item['page_start'],
        'page_end': item['page_end'],
        'section_title': item['section_title'],
        'text': item['text'],
        'cited_by_model': item['chunk_id'] in draft['evidence_ids'],
    } for item in contexts.rule_candidates + contexts.user_evidence_candidates]
    return Response({'draft_text': draft['draft_markdown'], 'assets': [], 'tokens_used': res.usage_tokens, 'evidence_ids': draft['evidence_ids'], 'missing_evidence': draft['missing_evidence'], 'evidence': evidence, 'run_id': str(run_id)})


@api_view(['GET'])
@permission_classes([DebugOrAuthPermission])
def section_evidence(request, section_id: int):
    section = ProposalSection.objects.select_related('proposal').filter(id=section_id).first()
    if section is None or _get_accessible_proposal(request, section.proposal_id) is None:
        return Response({'error': 'section_not_found'}, status=404)
    usages = EvidenceUsage.objects.filter(proposal_section=section, role='writer').order_by('-created_at', 'rank')
    return Response({
        'section_id': section.id,
        'evidence': [{
            'chunk_id': usage.chunk_id,
            'rank': usage.rank,
            'used_in_prompt': usage.used_in_prompt,
            'cited_by_model': usage.cited_by_model,
            'document_name': usage.document_name_snapshot,
            'page_start': usage.page_start_snapshot,
            'page_end': usage.page_end_snapshot,
            'section_title': usage.section_title_snapshot,
            'text': usage.snapshot_text,
        } for usage in usages],
    })


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
@ai_protected('revise', plan_gate=True)
def revise(request):
    change_request = sanitize_text(request.data.get('change_request', ''), max_len=4000)
    base_text = sanitize_text(request.data.get('base_text', ''), max_len=20000, neutralize_injection=False)
    section_id = sanitize_text(request.data.get('section_id'), max_len=128)
    proposal_id = None
    try:
        if request.data.get('proposal_id') is not None:
            proposal_id = int(request.data.get('proposal_id'))
    except Exception:
        proposal_id = None
    section = None
    if proposal_id is not None:
        proposal = _get_accessible_proposal(request, proposal_id)
        if proposal is None:
            return Response({'error': 'proposal_not_found'}, status=404)
        section = get_section(section_id, proposal_id=proposal.id)
        if section is None:
            return Response({'error': 'section_not_found'}, status=404)
    elif section_id:
        section = get_section(section_id)
    if section is not None and section.locked:
        return Response({'error': 'section_locked'}, status=409)
    run_id = resolve_run_id(request.data.get('run_id'), proposal_id=proposal_id, org_id=request.META.get('HTTP_X_ORG_ID', ''), provider=getattr(settings, 'AI_PROVIDER', ''))
    file_refs = sanitize_file_refs(request.data.get('file_refs', []))
    async_enabled = getattr(settings, 'AI_ASYNC', False) and settings.CELERY_BROKER_URL
    if async_enabled:
        job = AIJob.objects.create(
            type='revise',
            input_json={
                'proposal_id': proposal_id,
                'section_id': section_id,
                'base_text': base_text,
                'change_request': change_request,
                'file_refs': file_refs,
            },
            created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
            org_id=request.META.get('HTTP_X_ORG_ID', ''),
            run_id=run_id,
        )
        run_revise.delay(job.id)  # type: ignore[attr-defined]
        return Response({'job_id': job.id, 'status': job.status, 'run_id': str(run_id)})  # type: ignore[attr-defined]
    provider = get_provider(getattr(settings, 'AI_PROVIDER', None))
    # --- Revision cap pre-check (sync path only; async handled in task) ---
    if section is not None:
        try:
            cap_raw = getattr(settings, 'PROPOSAL_SECTION_REVISION_CAP', 5)
            try:
                cap_val = int(cap_raw) if cap_raw not in (None, '') else 5
            except Exception:
                cap_val = 5
            if cap_val <= 0:
                cap_val = 5
            current_count = len(section.revisions or [])
            if current_count >= cap_val:
                from .models import AIMetric

                try:
                    AIMetric.objects.create(
                        type='revise',
                        model_id='revision_cap_blocked',
                        duration_ms=0,
                        tokens_used=0,
                        success=False,
                        created_by=(request.user if request.user.is_authenticated else None),
                        org_id=request.META.get('HTTP_X_ORG_ID', ''),
                        section_id=section_id,
                        error_text='revision_cap_reached',
                    )
                except Exception:
                    pass
                return Response(
                    {
                        'error': 'revision_cap_reached',
                        'message': t('errors.revision.cap_reached', count=current_count, limit=cap_val),
                        'remaining_revision_slots': 0,
                    },
                    status=409,
                )
        except Exception:
            pass  # fall through on errors
    t0 = time.time()
    # (Memory suggestions reserved hook: intentionally skipped until provider contract extended)
    # Include memory context as additional signal appended to change_request (non-persistent)
    try:
        from .models import AIMemory

        org_scope = request.META.get('HTTP_X_ORG_ID', '')
        if request.user.is_authenticated:
            mem_items = AIMemory.suggestions(user=request.user, org_id=org_scope, section_id=section_id or None, limit=3)
            if mem_items:
                ctx = '\n'.join(f"{m['key']}: {m['value'][:400]}" for m in mem_items)
                addition = '\n\n[context:memory]\n' + ctx if change_request else '[context:memory]\n' + ctx
                change_request = change_request + addition
    except Exception:
        pass
    deterministic_setting = getattr(settings, 'AI_DETERMINISTIC_SAMPLING', True)
    try:
        deterministic_default = bool(False if str(deterministic_setting) in ('0', 'false', 'False') else deterministic_setting)
    except Exception:
        deterministic_default = True
    deterministic_req = request.data.get('deterministic') if isinstance(request.data, dict) else None
    if deterministic_req is not None:
        try:
            deterministic = bool(False if str(deterministic_req) in ('0', 'false', 'False') else deterministic_req)
        except Exception:
            deterministic = deterministic_default
    else:
        deterministic = deterministic_default
    try:
        res = provider.revise(
            base_text=base_text,
            change_request=change_request,
            file_refs=file_refs or None,
            deterministic=deterministic,
        )  # type: ignore[arg-type]
    except Exception:
        logger.exception('AI provider.revise failed')
        return Response({'error': 'ai_provider_error', 'message': t('errors.ai.provider_failed')}, status=502)
    diff_res = diff_texts(base_text, res.text)
    if section is not None:
        revise_service(
            section=section,
            revised_text=res.text,
            user_id=getattr(request.user, 'id', None),
            from_text=base_text,
            diff=diff_res,
        )
    dt_ms = int((time.time() - t0) * 1000)
    from .models import AIMetric

    # Record change_request as memory snippet (tagged by section)
    try:  # pragma: no cover
        from .models import AIMemory

        org_scope = request.META.get('HTTP_X_ORG_ID', '')
        if request.user.is_authenticated and change_request:
            AIMemory.record(
                user=request.user,
                org_id=org_scope,
                section_id=section_id or '',
                key='change_request',
                value=change_request[:2000],
            )
    except Exception:
        pass
    AIMetric.objects.create(
        type='revise',
        model_id=res.model_id,
        duration_ms=dt_ms,
        tokens_used=res.usage_tokens,
        proposal_id=proposal_id,
        section_id=section_id,
        created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
        org_id=request.META.get('HTTP_X_ORG_ID', ''),
        success=True,
        run_id=run_id,
    )
    return Response({'draft_text': res.text, 'diff': diff_res, 'run_id': str(run_id)})


@api_view(['POST'])
@permission_classes([DebugOrAuthPermission])
@ai_protected('format', plan_gate=True)
def format(request):
    # Final formatting across the whole composed text; optional template hint
    template_hint = sanitize_text(request.data.get('template_hint', None), max_len=256) if request.data else None
    proposal_id_raw = request.data.get('proposal_id')
    if proposal_id_raw is None:
        return Response({'error': 'proposal_id_required'}, status=400)
    try:
        proposal_id = int(proposal_id_raw)
    except (TypeError, ValueError):
        return Response({'error': 'proposal_id_invalid'}, status=400)
    proposal = _get_accessible_proposal(request, proposal_id)
    if proposal is None:
        return Response({'error': 'proposal_not_found'}, status=404)
    run_id = resolve_run_id(request.data.get('run_id'), proposal_id=proposal.id, org_id=request.META.get('HTTP_X_ORG_ID', ''), provider=getattr(settings, 'AI_PROVIDER', ''))
    try:
        full_text = build_approved_markdown(proposal)
    except SectionsNotApproved:
        return Response({'error': 'sections_not_approved'}, status=409)
    file_refs = sanitize_file_refs(request.data.get('file_refs', []))
    async_enabled = getattr(settings, 'AI_ASYNC', False) and settings.CELERY_BROKER_URL
    if async_enabled:
        job = AIJob.objects.create(
            type='format',
            input_json={
                'proposal_id': proposal_id,
                'full_text': full_text,
                'template_hint': template_hint or None,
                'file_refs': file_refs,
            },
            created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
            org_id=request.META.get('HTTP_X_ORG_ID', ''),
            run_id=run_id,
        )
        run_format.delay(job.id)  # type: ignore[attr-defined]
        return Response({'job_id': job.id, 'status': job.status, 'run_id': str(run_id)})  # type: ignore[attr-defined]
    provider = get_provider(getattr(settings, 'AI_PROVIDER', None))
    t0 = time.time()
    # Deterministic sampling toggle (default on for stable exports)
    deterministic_setting = getattr(settings, 'AI_DETERMINISTIC_SAMPLING', True)
    try:
        deterministic_default = bool(False if str(deterministic_setting) in ('0', 'false', 'False') else deterministic_setting)
    except Exception:
        deterministic_default = True
    deterministic_req = request.data.get('deterministic') if isinstance(request.data, dict) else None
    if deterministic_req is not None:
        try:
            deterministic = bool(False if str(deterministic_req) in ('0', 'false', 'False') else deterministic_req)
        except Exception:
            deterministic = deterministic_default
    else:
        deterministic = deterministic_default
    try:
        res = provider.format_final(
            full_text=full_text,
            template_hint=template_hint or None,
            file_refs=file_refs or None,
            deterministic=deterministic,
        )
    except Exception:
        logger.exception('AI provider.format_final failed')
        return Response({'error': 'ai_provider_error', 'message': t('errors.ai.provider_failed')}, status=502)
    finalize_service(proposal=proposal, final_markdown=res.text)
    dt_ms = int((time.time() - t0) * 1000)
    from .models import AIMetric

    AIMetric.objects.create(
        type='format',
        model_id=res.model_id,
        duration_ms=dt_ms,
        tokens_used=res.usage_tokens,
        proposal_id=proposal_id,
        created_by=(getattr(request, 'user', None) if request.user.is_authenticated else None),
        org_id=request.META.get('HTTP_X_ORG_ID', ''),
        success=True,
        run_id=run_id,
    )
    return Response({'formatted_text': res.text, 'run_id': str(run_id)})


@api_view(['GET'])
@permission_classes([DebugOrAuthPermission])
def job_status(request, job_id: int):
    job = AIJob.objects.filter(id=job_id).first()
    if not job:
        return Response({'error': 'not_found', 'message': t('errors.ai.not_found')}, status=404)
    return Response(
        {
            'id': job.id,  # type: ignore[attr-defined]
            'type': job.type,
            'status': job.status,
            'result': job.result_json,
            'error': job.error_text or None,
            'created_at': job.created_at,
            'updated_at': job.updated_at,
            'run_id': str(job.run_id),
        }
    )


@api_view(['GET'])
@permission_classes([DebugOrAuthPermission])
def run_timeline(request, run_id):
    try:
        run = WorkflowRun.objects.get(run_id=run_id)
    except (WorkflowRun.DoesNotExist, ValueError):
        return Response({'error': 'run_not_found'}, status=404)
    if run.org_id:
        user = getattr(request, 'user', None)
        has_access = getattr(user, 'is_authenticated', False) and Organization.objects.filter(
            id=run.org_id,
        ).filter(
            models.Q(admin=user) | models.Q(memberships__user=user),
        ).exists()
        if not has_access:
            return Response({'error': 'run_not_found'}, status=404)
    jobs = list(AIJob.objects.filter(run_id=run.run_id).order_by('created_at').values('type', 'status', 'created_at', 'updated_at', 'error_text'))
    metrics = list(AIMetric.objects.filter(run_id=run.run_id).order_by('created_at').values('type', 'success', 'duration_ms', 'tokens_used', 'error_text', 'model_id', 'created_at'))
    contexts = list(AIJobContext.objects.filter(run_id=run.run_id).order_by('created_at').values('prompt_version', 'template_sha256', 'created_at'))
    evidence = list(run.evidence_usages.order_by('created_at').values(
        'role', 'rank', 'similarity_score', 'used_in_prompt', 'cited_by_model',
        'evidence_alias', 'prompt_version', 'created_at',
    ))
    tools = list(run.tool_invocations.order_by('created_at').values(
        'tool_name', 'caller_role', 'status', 'error_code', 'created_at',
    ))
    human_tasks = list(run.human_tasks.order_by('created_at').values(
        'node', 'status', 'created_at', 'decided_at',
    ))
    return Response({
        'run_id': str(run.run_id),
        'proposal_id': run.proposal_id,
        'schema_version': run.schema_version,
        'provider': run.provider,
        'architecture': run.architecture,
        'status': run.status,
        'trace': run.trace_json,
        'handoffs': run.handoffs_json,
        'revision_count': run.revision_count,
        'fallback_mode': run.fallback_mode,
        'resumed_from_checkpoint': run.resumed_from_checkpoint,
        'completed_at': run.completed_at,
        'jobs': jobs,
        'metrics': metrics,
        'contexts': contexts,
        'evidence': evidence,
        'tools': tools,
        'human_tasks': human_tasks,
        'summary': {
            'job_count': len(jobs),
            'metric_count': len(metrics),
            'token_usage': sum(item['tokens_used'] for item in metrics),
            'evidence_count': len(evidence),
            'evidence_used_in_prompt_count': sum(item['used_in_prompt'] for item in evidence),
            'evidence_cited_by_model_count': sum(item['cited_by_model'] for item in evidence),
            'tool_call_count': len(tools),
            'tool_error_count': sum(item['status'] != 'done' for item in tools),
            'human_task_count': len(human_tasks),
            'pending_human_task_count': sum(item['status'] == 'pending' for item in human_tasks),
        },
    })


@api_view(['GET'])  # lightweight, DEBUG-only metrics peek
@permission_classes([DebugOrAuthPermission])
def metrics_recent(request):
    """Return the most recent AIMetrics for the caller's org (DEBUG allows anon).

    Query params:
      - limit: max rows (default 20, cap 100)
    """
    try:
        limit = int(request.GET.get('limit', '20'))
    except Exception:
        limit = 20
    if limit <= 0:
        limit = 20
    if limit > 100:
        limit = 100
    org_id = request.META.get('HTTP_X_ORG_ID', '')
    from .models import AIMetric  # local import to avoid circular and linter duplicate

    qs: QuerySet = AIMetric.objects.all()
    if org_id:
        qs = qs.filter(org_id=org_id)
    qs = qs.order_by(
        '-id'
    ).values(  # type: ignore[assignment]
        'id',
        'type',
        'model_id',
        'duration_ms',
        'tokens_used',
        'success',
        'org_id',
        'created_at',
    )[:limit]
    return Response({'items': list(qs)})


@api_view(['GET'])  # aggregate averages across scopes
@permission_classes([DebugOrAuthPermission])
def metrics_summary(request):
    """Averages for tokens/duration and edit metrics by scope (global/org/user)."""
    from .models import AIMetric  # local import
    from django.db.models import Sum, Count

    org_id = request.META.get('HTTP_X_ORG_ID', '')

    def agg(qs):
        totals = qs.aggregate(cnt=Count('id'), tok=Sum('tokens_used'), dur=Sum('duration_ms'))
        cnt = totals.get('cnt') or 0
        tok = totals.get('tok') or 0
        dur = totals.get('dur') or 0
        avg_tokens = (tok / cnt) if cnt else 0.0
        avg_ms = (dur / cnt) if cnt else 0.0

        edits = qs.filter(type='revise')
        e_totals = edits.aggregate(cnt=Count('id'), tok=Sum('tokens_used'))
        e_cnt = e_totals.get('cnt') or 0
        e_tok = e_totals.get('tok') or 0
        # per-user edit counts average
        per_user = edits.exclude(created_by__isnull=True).values('created_by').annotate(c=Count('id'))
        users = per_user.count()
        edits_per_user_avg = (sum(x['c'] for x in per_user) / users) if users else 0.0
        edit_tokens_avg = (e_tok / e_cnt) if e_cnt else 0.0
        return {
            'count': cnt,
            'avg_tokens': round(avg_tokens, 2),
            'avg_duration_ms': round(avg_ms, 2),
            'edits_per_user_avg': round(edits_per_user_avg, 2),
            'edit_tokens_avg': round(edit_tokens_avg, 2),
        }

    global_stats = agg(AIMetric.objects.all())
    empty = {
        'count': 0,
        'avg_tokens': 0.0,
        'avg_duration_ms': 0.0,
        'edits_per_user_avg': 0.0,
        'edit_tokens_avg': 0.0,
    }
    org_stats = agg(AIMetric.objects.filter(org_id=org_id)) if org_id else empty
    user_stats = empty
    if getattr(request, 'user', None) and request.user.is_authenticated:
        user_stats = agg(AIMetric.objects.filter(created_by=request.user))

    return Response({'global': global_stats, 'org': org_stats, 'user': user_stats})


@api_view(['GET'])
@permission_classes([DebugOrAuthPermission])
def memory_suggestions(request):
    """Return AI memory suggestions for the caller.

    Query params:
      - section_id: optional filter
      - limit: max items (default 5, cap 20)
    Scope: if X-Org-ID header present, return org-level items; else user-only.
    """
    from .models import AIMemory  # local import

    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return Response({'items': []})
    section_id = request.GET.get('section_id') or None
    try:
        limit = int(request.GET.get('limit', '5'))
    except Exception:
        limit = 5
    org_id = request.META.get('HTTP_X_ORG_ID', '')
    suggestions = AIMemory.suggestions(user=request.user, org_id=org_id, section_id=section_id, limit=limit)
    return Response({'items': suggestions})
