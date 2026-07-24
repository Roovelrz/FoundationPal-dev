from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
import uuid


class WorkflowRun(models.Model):
    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    proposal_id = models.IntegerField(null=True, blank=True)
    org_id = models.CharField(max_length=64, blank=True, default='')
    provider = models.CharField(max_length=64, blank=True, default='')
    schema_version = models.CharField(max_length=16, default='v1')
    architecture = models.CharField(max_length=32, default='sequential')
    status = models.CharField(max_length=32, default='running')
    trace_json = models.JSONField(default=list)
    handoffs_json = models.JSONField(default=list)
    revision_count = models.PositiveIntegerField(default=0)
    fallback_mode = models.CharField(max_length=32, blank=True, default='')
    resumed_from_checkpoint = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class HumanApprovalTask(models.Model):
    STATUS_CHOICES = [
        ('pending', 'pending'),
        ('approved', 'approved'),
        ('ready_after_edit', 'ready_after_edit'),
        ('rejected', 'rejected'),
    ]
    workflow_run = models.ForeignKey(WorkflowRun, on_delete=models.CASCADE, related_name='human_tasks')
    proposal_id = models.IntegerField(db_index=True)
    thread_id = models.CharField(max_length=128, unique=True)
    node = models.CharField(max_length=64)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='pending')
    input_json = models.JSONField(default=dict)
    model_output_json = models.JSONField(default=dict)
    decision_json = models.JSONField(default=dict)
    decided_by = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


class ToolInvocation(models.Model):
    '''Auditable tool call with an idempotency boundary for side effects.'''

    tool_name = models.CharField(max_length=64, db_index=True)
    caller_role = models.CharField(max_length=32)
    caller = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    organization_id = models.CharField(max_length=64, blank=True, default='')
    proposal_id = models.IntegerField(null=True, blank=True)
    workflow_run = models.ForeignKey(WorkflowRun, null=True, blank=True, on_delete=models.SET_NULL, related_name='tool_invocations')
    idempotency_key = models.CharField(max_length=128, blank=True, default='')
    request_hash = models.CharField(max_length=64, blank=True, default='')
    status = models.CharField(max_length=16, default='done')
    result_json = models.JSONField(default=dict)
    error_code = models.CharField(max_length=64, blank=True, default='')
    duration_ms = models.IntegerField(default=0)
    replay_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['tool_name', 'caller_role', 'caller', 'organization_id', 'idempotency_key'],
                name='toolinvocation_idempotency_unique',
            )
        ]
        indexes = [models.Index(fields=['organization_id', 'tool_name', 'created_at'])]


class AIPromptTemplate(models.Model):
    """Versioned prompt template owned by backend (users never edit directly).

    name: machine-readable identifier (e.g., planner.base)
    version: monotonically increasing integer
    role: planner|writer|reviser|formatter (for fast filtering)
    template: raw template text with {{variable}} placeholders
    checksum: sha256 of template text (quick integrity check)
    variables: declared variable names (for validation / rendering safety)
    active: soft flag to allow deprecation while keeping history
    """

    ROLE_CHOICES = [
        ('planner', 'planner'),
        ('writer', 'writer'),
        ('reviser', 'reviser'),
        ('formatter', 'formatter'),
    ]

    name = models.CharField(max_length=128, db_index=True)
    version = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    template = models.TextField()
    checksum = models.CharField(max_length=64, db_index=True)
    variables = models.JSONField(default=list)  # list[str]
    active = models.BooleanField(default=True)
    # Optional structural output blueprint (JSON schema-like) for roles that require constrained formatting
    blueprint_schema = models.JSONField(null=True, blank=True)
    # Human authored instructions describing how to conform to blueprint (displayed to provider prompt)
    blueprint_instructions = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['name', 'version'], name='prompt_template_version_unique'),
        ]
        indexes = [models.Index(fields=['role', 'active'])]

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f'AIPromptTemplate({self.name}@v{self.version})'

    @staticmethod
    def compute_checksum(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):  # pragma: no cover - simple override
        # Always recompute checksum when template text is being saved (initial create or template field updated)
        update_fields = kwargs.get('update_fields')
        if update_fields is None or 'template' in update_fields:
            self.checksum = self.compute_checksum(self.template)
        super().save(*args, **kwargs)


class AIJob(models.Model):
    TYPE_CHOICES = [
        ('plan', 'plan'),
        ('write', 'write'),
        ('revise', 'revise'),
        ('format', 'format'),
    ]
    STATUS_CHOICES = [
        ('queued', 'queued'),
        ('processing', 'processing'),
        ('done', 'done'),
        ('error', 'error'),
    ]

    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='queued')
    input_json = models.JSONField(default=dict)
    result_json = models.JSONField(null=True, blank=True)
    error_text = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    org_id = models.CharField(max_length=64, blank=True, default='')
    run_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        # id attribute available at runtime; ignore static checker
        return f"AIJob#{getattr(self, 'id', 'unsaved')} {self.type} {self.status}"  # type: ignore[attr-defined]


class AIMetric(models.Model):
    TYPE_CHOICES = [
        ('plan', 'plan'),
        ('write', 'write'),
        ('revise', 'revise'),
        ('format', 'format'),
        ('promote', 'promote'),  # section promotion event
        ('export', 'export'),
        ('evaluation', 'evaluation'),
    ]

    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    model_id = models.CharField(max_length=64, blank=True, default='')
    # Optional linkage for pricing/analytics
    proposal_id = models.IntegerField(null=True, blank=True)
    section_id = models.CharField(max_length=128, blank=True, default='')
    duration_ms = models.IntegerField(default=0)
    tokens_used = models.IntegerField(default=0)
    estimated_cost_usd = models.FloatField(default=0.0)
    success = models.BooleanField(default=True)
    error_text = models.TextField(blank=True, default='')
    created_by = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    org_id = models.CharField(max_length=64, blank=True, default='')
    run_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f'AIMetric({self.type},{self.model_id},{self.duration_ms}ms)'


class AIMemory(models.Model):
    """Reusable small snippets of user/org knowledge captured from answers.

    Scope rules:
      - If org_id set: shared across org members (org-scoped memory)
      - Else: user only (personal memory)
    Deduplication:
      - (created_by, org_id, key_hash, value_hash) uniqueness to avoid bloat
    Retrieval:
      - Filter by user/org, optional section_id or key prefix search.
    """

    created_by = models.ForeignKey(get_user_model(), null=True, blank=True, on_delete=models.SET_NULL)
    org_id = models.CharField(max_length=64, blank=True, default='')
    section_id = models.CharField(max_length=128, blank=True, default='')
    key = models.CharField(max_length=256)
    value = models.TextField()
    # Simple hashes for fast dedup (sha256 hex truncated)
    key_hash = models.CharField(max_length=32, db_index=True)
    value_hash = models.CharField(max_length=32, db_index=True)
    usage_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['created_by', 'org_id', 'key_hash', 'value_hash'],
                name='aimemory_dedup_unique',
            )
        ]
        indexes = [
            models.Index(fields=['org_id', 'section_id']),
            models.Index(fields=['created_by', 'section_id']),
        ]

    def __str__(self) -> str:  # pragma: no cover - trivial
        scope = self.org_id or f"user:{getattr(self.created_by, 'id', 'anon')}"
        return f'AIMemory[{scope}] {self.key[:40]}={self.value[:40]}...'

    @staticmethod
    def hash_text(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode('utf-8')).hexdigest()[:32]

    @classmethod
    def record(cls, *, user, org_id: str, section_id: str, key: str, value: str) -> 'AIMemory':
        """Idempotently store a key/value memory item and return it.

        Increments usage_count if already present.
        """
        key = (key or '').strip()
        value = (value or '').strip()
        if not key or not value:
            raise ValueError('key and value required')
        kh = cls.hash_text(key)
        vh = cls.hash_text(value)
        obj, created = cls.objects.get_or_create(
            created_by=user if getattr(user, 'is_authenticated', False) else None,
            org_id=org_id or '',
            key_hash=kh,
            value_hash=vh,
            defaults={
                'section_id': section_id or '',
                'key': key[:256],
                'value': value[:2000],  # safety cap
            },
        )
        if not created:
            cls.objects.filter(id=getattr(obj, 'id', None)).update(  # type: ignore[attr-defined]
                usage_count=models.F('usage_count') + 1,
                updated_at=models.functions.Now(),
            )
            obj.usage_count += 1
        return obj

    @classmethod
    def suggestions(cls, *, user, org_id: str, section_id: str | None = None, limit: int = 5):
        qs = cls.objects.all().order_by('-usage_count', '-updated_at')
        if org_id:
            qs = qs.filter(org_id=org_id)
        else:
            # Personal scope: only records explicitly stored without an org_id.
            # We intentionally exclude org-scoped memories even if created_by matches
            # to ensure isolation unless the caller supplies the org header.
            qs = qs.filter(created_by=user, org_id='')
        if section_id:
            qs = qs.filter(section_id=section_id)
        return list(qs.values('key', 'value', 'usage_count')[: max(1, min(limit, 20))])


class AIJobContext(models.Model):
    """Audit + reproducibility context for an AIJob.

    Stores the rendered (redacted) prompt snapshot, template/version and basic model params
    plus retrieval metadata once retrieval is integrated. Users never see raw unredacted prompt.
    """

    job = models.ForeignKey(AIJob, on_delete=models.CASCADE, related_name='contexts')
    run_id = models.UUIDField(null=True, blank=True, db_index=True)
    prompt_template = models.ForeignKey(AIPromptTemplate, null=True, blank=True, on_delete=models.SET_NULL)
    prompt_version = models.PositiveIntegerField(default=1)
    rendered_prompt_redacted = models.TextField()
    model_params = models.JSONField(default=dict)
    snippet_ids = models.JSONField(default=list)
    retrieval_metrics = models.JSONField(default=dict)
    # sha256 of the exact template text (post substitution template, prior to variable injection) for drift detection
    template_sha256 = models.CharField(max_length=64, blank=True, default='')
    # mapping of redacted token -> original classification (not the original literal) for forensic/audit
    redaction_map = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['created_at']),
            models.Index(fields=['job']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"AIJobContext(job={getattr(self.job, 'id', 'unsaved')},v={self.prompt_version})"

    def save(self, *args, **kwargs):  # pragma: no cover
        if self.run_id is None and self.job_id:
            self.run_id = self.job.run_id
        super().save(*args, **kwargs)

    @staticmethod
    def redact(text: str) -> str:
        """Backward compatible simple redaction returning string only (deprecated)."""
        redacted, _ = AIJobContext.redact_with_mapping(text)
        return redacted

    @staticmethod
    def redact_with_mapping(text: str) -> tuple[str, dict[str, str]]:
        """Extended deterministic redaction.

        Returns (redacted_text, mapping) where mapping is token->classification (NOT raw value).
        Classifications: EMAIL, NUMBER, PHONE, SIMPLE_NAME, ID_CODE, ADDRESS_LINE
        """
        import re
        import hashlib

        if not text:
            return text, {}
        mapping: dict[str, str] = {}

        patterns: list[tuple[str, str]] = [
            (r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', 'EMAIL'),
            (r'\b\d{6,}\b', 'NUMBER'),
            (r'\b\+?[0-9][0-9\-\s]{6,}[0-9]\b', 'PHONE'),
            (r'\b[A-Z]{2}[0-9]{2,}\b', 'ID_CODE'),  # simplistic code/id pattern
            (r'\b([A-Z][a-z]{1,15}\s[A-Z][a-z]{1,15})\b', 'SIMPLE_NAME'),
            (r'\b\d+\s+[A-Z][A-Za-z]+\s+(Street|St|Road|Rd|Avenue|Ave|Boulevard|Blvd|Lane|Ln)\b', 'ADDRESS_LINE'),
        ]

        def token_for(val: str, cls: str) -> str:
            h = hashlib.sha256(val.encode('utf-8')).hexdigest()[:10]
            return f'[{cls}_{h}]'

        redacted = text
        for pattern, classification in patterns:

            def repl(m, _c=classification):  # bind current classification
                val = m.group(0)
                tok = token_for(val, _c)
                mapping.setdefault(tok, _c)
                return tok

            redacted = re.sub(pattern, repl, redacted)

        if len(redacted) > 20000:
            redacted = redacted[:20000] + '…'
        return redacted, mapping


class AIResource(models.Model):
    """Versioned source document for RAG evidence."""

    SOURCE_TYPE_CHOICES = [
        ('guideline', 'guideline'),
        ('call_snapshot', 'call_snapshot'),
        ('successful_case', 'successful_case'),
        ('team_profile', 'team_profile'),
        ('template', 'template'),
        ('review_criteria', 'review_criteria'),
        ('sample', 'sample'),
    ]
    PURPOSE_CHOICES = [
        ('constraint', 'constraint'),
        ('fact', 'fact'),
        ('style', 'style'),
        ('template', 'template'),
    ]
    STATUS_CHOICES = [('ready', 'ready'), ('error', 'error'), ('deleted', 'deleted')]

    organization_id = models.CharField(max_length=64, db_index=True, default='')
    proposal_id = models.IntegerField(null=True, blank=True, db_index=True)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPE_CHOICES)
    evidence_purpose = models.CharField(max_length=16, choices=PURPOSE_CHOICES, default='fact')
    title = models.CharField(max_length=256, blank=True, default='')  # legacy display fallback
    original_filename = models.CharField(max_length=512, blank=True, default='')
    display_name = models.CharField(max_length=256, blank=True, default='')
    mime_type = models.CharField(max_length=128, blank=True, default='')
    source_url = models.URLField(blank=True, default='')
    sha256 = models.CharField(max_length=64, db_index=True)
    parser_version = models.CharField(max_length=64, default='pdfminer-v1')
    embedding_model = models.CharField(max_length=128, blank=True, default='')
    embedding_revision = models.CharField(max_length=128, blank=True, default='')
    embedding_dimension = models.PositiveIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='ready')
    error_code = models.CharField(max_length=64, blank=True, default='')
    is_deleted = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organization_id', 'sha256', 'parser_version'],
                name='airesource_org_sha_parser_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['organization_id', 'proposal_id', 'source_type'], name='ai_airesour_orgpsrc_idx'),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f'AIResource({self.source_type},{self.id})'  # type: ignore[attr-defined]

    def delete(self, *args, **kwargs):  # pragma: no cover - exercised through integration tests
        if self.chunks.filter(evidence_usages__isnull=False).exists():
            self.is_deleted = True
            self.status = 'deleted'
            self.save(update_fields=['is_deleted', 'status'])
            return
        return super().delete(*args, **kwargs)

    @staticmethod
    def compute_sha256(text: str) -> str:
        import hashlib

        return hashlib.sha256(text.encode('utf-8')).hexdigest()


class AIChunk(models.Model):
    """Embedded chunk of an AIResource."""

    resource = models.ForeignKey(AIResource, on_delete=models.CASCADE, related_name='chunks')
    stable_chunk_id = models.CharField(max_length=64, db_index=True)
    chunk_index = models.IntegerField()
    text = models.TextField()
    normalized_text = models.TextField(blank=True, default='')
    text_sha256 = models.CharField(max_length=64, db_index=True, default='')
    page_start = models.PositiveIntegerField(default=1)
    page_end = models.PositiveIntegerField(default=1)
    section_title = models.CharField(max_length=512, blank=True, default='')
    heading_path = models.JSONField(default=list)
    token_count = models.IntegerField(default=0)
    embedding_key = models.CharField(max_length=64, blank=True, default='')  # placeholder until vector store integration
    # Cached embedding vector (list[float]) for naive in-DB retrieval; replace with external vector store later
    embedding = models.JSONField(null=True, blank=True)
    embedding_model = models.CharField(max_length=128, blank=True, default='')
    embedding_dimension = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['resource', 'chunk_index'], name='aichunk_resource_index_unique'),
        ]
        indexes = [
            models.Index(fields=['resource']),
            models.Index(fields=['embedding_key']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"AIChunk(res={getattr(self.resource, 'id', 'unsaved')},ord={self.chunk_index})"


class EvidenceUsage(models.Model):
    """Immutable snapshot of evidence made available to one model invocation."""

    ROLE_CHOICES = [('planner', 'planner'), ('writer', 'writer'), ('reviser', 'reviser'), ('formatter', 'formatter')]

    workflow_run = models.ForeignKey(WorkflowRun, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    ai_job = models.ForeignKey(AIJob, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    proposal_section = models.ForeignKey('proposals.ProposalSection', null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='evidence_usages')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    retrieval_query = models.TextField(blank=True, default='')
    rank = models.PositiveIntegerField(default=0)
    similarity_score = models.FloatField(default=0.0)
    used_in_prompt = models.BooleanField(default=False)
    cited_by_model = models.BooleanField(default=False)
    evidence_alias = models.CharField(max_length=32, blank=True, default='')
    snapshot_text = models.TextField()
    document_name_snapshot = models.CharField(max_length=256, blank=True, default='')
    page_start_snapshot = models.PositiveIntegerField(default=1)
    page_end_snapshot = models.PositiveIntegerField(default=1)
    section_title_snapshot = models.CharField(max_length=512, blank=True, default='')
    prompt_version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['ai_job', 'chunk', 'role'], name='evidenceusage_job_chunk_role_unique'),
        ]
        indexes = [models.Index(fields=['proposal_section', 'created_at'], name='ai_evidence_propcrt_idx')]
