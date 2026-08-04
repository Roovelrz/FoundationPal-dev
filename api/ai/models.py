from django.conf import settings
from django.core.exceptions import ValidationError
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
    KNOWLEDGE_DOMAIN_CHOICES = [
        ('unknown', 'unknown'),
        ('grant_rule', 'grant_rule'),
        ('user_evidence', 'user_evidence'),
    ]
    CLASSIFICATION_STATUS_CHOICES = [
        ('pending_classification', 'pending_classification'),
        ('classified', 'classified'),
        ('pack_draft', 'pack_draft'),
    ]
    AUTHORIZATION_SCOPE_CHOICES = [
        ('organization', 'organization'),
        ('proposal', 'proposal'),
        ('owner_private', 'owner_private'),
    ]

    organization_id = models.CharField(max_length=64, db_index=True, default='')
    proposal_id = models.IntegerField(null=True, blank=True, db_index=True)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPE_CHOICES)
    evidence_purpose = models.CharField(max_length=16, choices=PURPOSE_CHOICES, default='fact')
    knowledge_domain = models.CharField(max_length=32, choices=KNOWLEDGE_DOMAIN_CHOICES, default='unknown', db_index=True)
    classification_status = models.CharField(max_length=32, choices=CLASSIFICATION_STATUS_CHOICES, default='pending_classification', db_index=True)
    source_authority = models.CharField(max_length=256, blank=True, default='')
    source_effective_date = models.DateField(null=True, blank=True)
    source_expiry_date = models.DateField(null=True, blank=True)
    grant_pack = models.ForeignKey('GrantPack', null=True, blank=True, on_delete=models.PROTECT, related_name='resources')
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='owned_ai_resources')
    authorization_scope = models.CharField(max_length=32, choices=AUTHORIZATION_SCOPE_CHOICES, default='organization')
    supersedes_resource = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='superseded_by')
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
                fields=['organization_id', 'proposal_id', 'sha256', 'parser_version'],
                name='airesource_org_proposal_sha_parser_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['organization_id', 'proposal_id', 'source_type'], name='ai_airesour_orgpsrc_idx'),
            models.Index(fields=['created_at']),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f'AIResource({self.source_type},{self.id})'  # type: ignore[attr-defined]

    def clean(self):
        super().clean()
        if self.knowledge_domain == 'grant_rule':
            if not self.grant_pack_id and self.classification_status != 'pack_draft':
                raise ValidationError({'grant_pack': 'grant_rule resources require a grant pack or pack_draft status.'})
        if self.knowledge_domain == 'user_evidence':
            if not self.organization_id:
                raise ValidationError({'organization_id': 'user_evidence resources require an organization.'})
            if self.source_authority or self.source_effective_date or self.source_expiry_date:
                raise ValidationError('rule authority and validity dates only apply to grant_rule resources.')

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
    KNOWLEDGE_DOMAIN_CHOICES = AIResource.KNOWLEDGE_DOMAIN_CHOICES
    CHUNK_TYPE_CHOICES = [
        ('unknown', 'unknown'),
        ('requirement', 'requirement'),
        ('eligibility', 'eligibility'),
        ('budget', 'budget'),
        ('review_criterion', 'review_criterion'),
        ('section_instruction', 'section_instruction'),
        ('submission_rule', 'submission_rule'),
        ('publication', 'publication'),
        ('project', 'project'),
        ('patent', 'patent'),
        ('experiment', 'experiment'),
        ('dataset', 'dataset'),
        ('equipment', 'equipment'),
        ('team_profile', 'team_profile'),
        ('budget_basis', 'budget_basis'),
    ]
    knowledge_domain = models.CharField(max_length=32, choices=KNOWLEDGE_DOMAIN_CHOICES, default='unknown', db_index=True)
    chunk_type = models.CharField(max_length=32, choices=CHUNK_TYPE_CHOICES, default='unknown', db_index=True)
    parent_chunk = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='child_chunks')
    section_path = models.JSONField(default=list)
    rule_number = models.CharField(max_length=128, blank=True, default='')
    entity_keys = models.JSONField(default=list)
    index_namespace = models.CharField(max_length=32, blank=True, default='', db_index=True)
    index_version = models.CharField(max_length=64, blank=True, default='')
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
    embedding_input_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
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

    def clean(self):
        super().clean()
        if self.resource_id and self.knowledge_domain != self.resource.knowledge_domain:
            raise ValidationError({'knowledge_domain': 'chunk domain must match its resource domain.'})
        if self.knowledge_domain in {'grant_rule', 'user_evidence'} and self.index_namespace != self.knowledge_domain:
            raise ValidationError({'index_namespace': 'index namespace must match the knowledge domain.'})
        if self.parent_chunk_id and self.parent_chunk.knowledge_domain != self.knowledge_domain:
            raise ValidationError({'parent_chunk': 'parent chunk must use the same knowledge domain.'})


class GrantProgram(models.Model):
    name = models.CharField(max_length=256)
    program_type = models.CharField(max_length=128)
    region = models.CharField(max_length=128, blank=True, default='')
    authority = models.CharField(max_length=256)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['name', 'program_type', 'region'], name='grantprogram_name_type_region_unique')]


class GrantPack(models.Model):
    program = models.ForeignKey(GrantProgram, on_delete=models.PROTECT, related_name='packs')
    code = models.CharField(max_length=128, unique=True)
    name = models.CharField(max_length=256)
    organization_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    is_public = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class GrantPackVersion(models.Model):
    STATUS_CHOICES = [('draft', 'draft'), ('extracted', 'extracted'), ('needs_review', 'needs_review'), ('validated', 'validated'), ('published', 'published'), ('superseded', 'superseded'), ('archived', 'archived')]

    pack = models.ForeignKey(GrantPack, on_delete=models.CASCADE, related_name='versions')
    year = models.PositiveIntegerField()
    version = models.CharField(max_length=64)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')
    published_at = models.DateField(null=True, blank=True)
    last_verified_at = models.DateField(null=True, blank=True)
    detected_metadata = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['pack', 'year', 'version'], name='grantpackversion_pack_year_version_unique')]


class GrantPackDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = [('guide', 'guide'), ('template', 'template'), ('notice', 'notice'), ('faq', 'faq'), ('budget', 'budget'), ('review', 'review'), ('form_check', 'form_check'), ('organization_supplement', 'organization_supplement')]

    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='documents')
    resource = models.ForeignKey(AIResource, on_delete=models.PROTECT, related_name='grant_pack_documents')
    document_type = models.CharField(max_length=32, choices=DOCUMENT_TYPE_CHOICES, default='guide')
    confidence = models.DecimalField(max_digits=4, decimal_places=3, default=1)
    needs_human_review = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['pack_version', 'resource'], name='grantpackdocument_version_resource_unique')]


class GrantRequirement(models.Model):
    REQUIREMENT_TYPE_CHOICES = [('content', 'content'), ('format', 'format'), ('eligibility', 'eligibility'), ('budget', 'budget'), ('submission', 'submission')]

    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='requirements')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='grant_requirements')
    requirement_type = models.CharField(max_length=32, choices=REQUIREMENT_TYPE_CHOICES)
    mandatory = models.BooleanField(default=True)
    target_section = models.CharField(max_length=128, blank=True, default='')
    validation_method = models.CharField(max_length=128, blank=True, default='')
    applicability = models.JSONField(default=dict)
    text = models.TextField()
    priority = models.PositiveIntegerField(default=0)
    applicable_condition = models.TextField(blank=True, default='')
    source_excerpt = models.TextField(blank=True, default='')
    extraction_prompt_version = models.PositiveIntegerField(default=1)
    target_sections = models.ManyToManyField('SectionSchema', blank=True, related_name='requirements')


class EligibilityRule(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='eligibility_rules')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='eligibility_rules')
    rule = models.TextField()
    applicability = models.JSONField(default=dict)


class SectionSchema(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='section_schemas')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='section_schemas')
    section_key = models.CharField(max_length=128)
    title = models.CharField(max_length=256)
    order = models.PositiveIntegerField(default=0)
    required = models.BooleanField(default=True)
    word_limit = models.PositiveIntegerField(null=True, blank=True)
    subsections = models.JSONField(default=list)
    field_type = models.CharField(max_length=64, blank=True, default='markdown')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['pack_version', 'section_key'], name='sectionschema_version_key_unique')]


class ReviewCriterion(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='review_criteria')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='review_criteria')
    criterion = models.TextField()
    weight = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)


class BudgetRule(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='budget_rules')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='budget_rules')
    rule = models.TextField()
    applicability = models.JSONField(default=dict)


class SubmissionRule(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='submission_rules')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='submission_rules')
    rule = models.TextField()
    deadline = models.DateTimeField(null=True, blank=True)


class RuleConflict(models.Model):
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='conflicts')
    primary_requirement = models.ForeignKey(GrantRequirement, null=True, blank=True, on_delete=models.SET_NULL, related_name='primary_conflicts')
    conflicting_requirement = models.ForeignKey(GrantRequirement, null=True, blank=True, on_delete=models.SET_NULL, related_name='conflicting_conflicts')
    source_priority = models.PositiveIntegerField(default=0)
    description = models.TextField()
    human_resolution = models.TextField(blank=True, default='')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='rule_conflict_reviews')


class RuleExtractionReview(models.Model):
    STATUS_CHOICES = [('pending', 'pending'), ('accepted', 'accepted'), ('rejected', 'rejected')]

    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.CASCADE, related_name='extraction_reviews')
    source_chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='rule_extraction_reviews')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='rule_extraction_reviews')
    notes = models.TextField(blank=True, default='')


class UserEvidence(models.Model):
    resource = models.ForeignKey(AIResource, on_delete=models.PROTECT, related_name='user_evidence_records')
    chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='user_evidence_records')
    organization_id = models.CharField(max_length=64, db_index=True)
    proposal = models.ForeignKey('proposals.Proposal', null=True, blank=True, on_delete=models.CASCADE, related_name='user_evidence_records')
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='user_evidence_records')
    authorization_scope = models.CharField(max_length=32, choices=AIResource.AUTHORIZATION_SCOPE_CHOICES, default='organization')
    controlled_summary = models.TextField(blank=True, default='')

    def clean(self):
        super().clean()
        if self.resource.knowledge_domain != 'user_evidence' or self.chunk.knowledge_domain != 'user_evidence':
            raise ValidationError('user evidence requires user_evidence resource and chunk domains.')
        if self.resource_id != self.chunk.resource_id:
            raise ValidationError('user evidence chunk must belong to its resource.')


class EvidenceFact(models.Model):
    FACT_STATUS_CHOICES = [('completed', 'completed'), ('ongoing', 'ongoing'), ('planned', 'planned'), ('uncertain', 'uncertain')]
    USER_ROLE_CHOICES = [('lead', 'lead'), ('first_author', 'first_author'), ('participant', 'participant'), ('team_member', 'team_member'), ('unknown', 'unknown')]
    VERIFICATION_STATUS_CHOICES = [('extracted', 'extracted'), ('user_confirmed', 'user_confirmed'), ('conflicted', 'conflicted'), ('rejected', 'rejected')]

    user_evidence = models.ForeignKey(UserEvidence, on_delete=models.CASCADE, related_name='facts')
    subject = models.CharField(max_length=512)
    predicate = models.CharField(max_length=256)
    object = models.TextField()
    fact_type = models.CharField(max_length=128)
    time_range = models.JSONField(default=dict)
    numeric_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=64, blank=True, default='')
    metric_definition = models.TextField(blank=True, default='')
    author_order = models.PositiveIntegerField(null=True, blank=True)
    project_status = models.CharField(max_length=32, blank=True, default='')
    authority_level = models.CharField(max_length=32, blank=True, default='')
    fact_status = models.CharField(max_length=16, choices=FACT_STATUS_CHOICES, default='uncertain')
    user_role = models.CharField(max_length=16, choices=USER_ROLE_CHOICES, default='unknown')
    verification_status = models.CharField(max_length=16, choices=VERIFICATION_STATUS_CHOICES, default='extracted')


class EvidenceEntity(models.Model):
    user_evidence = models.ForeignKey(UserEvidence, on_delete=models.CASCADE, related_name='entities')
    entity_key = models.CharField(max_length=128)
    entity_type = models.CharField(max_length=128)
    name = models.CharField(max_length=512)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user_evidence', 'entity_key'], name='evidenceentity_evidence_key_unique')]


class EvidenceVerification(models.Model):
    fact = models.ForeignKey(EvidenceFact, on_delete=models.CASCADE, related_name='verifications')
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_verifications')
    status = models.CharField(max_length=16, choices=EvidenceFact.VERIFICATION_STATUS_CHOICES)
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


class EvidenceAuthorization(models.Model):
    user_evidence = models.ForeignKey(UserEvidence, on_delete=models.CASCADE, related_name='authorizations')
    proposal = models.ForeignKey('proposals.Proposal', null=True, blank=True, on_delete=models.CASCADE, related_name='evidence_authorizations')
    owner_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_authorizations')
    allowed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Claim(models.Model):
    CLAIM_TYPE_CHOICES = [('factual', 'factual'), ('numerical', 'numerical'), ('interpretive', 'interpretive'), ('proposed', 'proposed'), ('comparative', 'comparative'), ('eligibility', 'eligibility'), ('unsupported', 'unsupported')]
    STATUS_CHOICES = [('planned', 'planned'), ('retrieved', 'retrieved'), ('drafted', 'drafted'), ('verified', 'verified'), ('human_approved', 'human_approved'), ('locked', 'locked'), ('missing_evidence', 'missing_evidence'), ('partial_support', 'partial_support'), ('conflicted', 'conflicted'), ('rejected', 'rejected'), ('outdated', 'outdated')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='claims')
    proposal_section = models.ForeignKey('proposals.ProposalSection', null=True, blank=True, on_delete=models.SET_NULL, related_name='claims')
    text = models.TextField()
    claim_type = models.CharField(max_length=64, choices=CLAIM_TYPE_CHOICES, default='unsupported')
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='planned')
    source_mode = models.CharField(max_length=32, default='confirmed_brief')
    risk_level = models.CharField(max_length=16, default='low')
    ledger = models.JSONField(default=dict)
    proposal_decisions = models.ManyToManyField('ProposalDecision', blank=True, related_name='claims')
    addressed_requirements = models.ManyToManyField(GrantRequirement, blank=True, related_name='addressing_claims')


class ClaimEvidenceBinding(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='evidence_bindings')
    grant_requirement = models.ForeignKey(GrantRequirement, null=True, blank=True, on_delete=models.CASCADE, related_name='claim_bindings')
    user_evidence = models.ForeignKey(UserEvidence, null=True, blank=True, on_delete=models.CASCADE, related_name='claim_bindings')
    support_type = models.CharField(max_length=32, default='support')
    support_strength = models.CharField(max_length=16, default='partial')
    reviewer_status = models.CharField(max_length=32, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        if not self.grant_requirement_id and not self.user_evidence_id:
            raise ValidationError('a claim evidence binding requires a requirement or user evidence record.')


class ClaimLedgerEntry(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='ledger_entries')
    evidence_fact = models.ForeignKey(EvidenceFact, null=True, blank=True, on_delete=models.SET_NULL, related_name='claim_ledger_entries')
    proposal_decision = models.ForeignKey('ProposalDecision', null=True, blank=True, on_delete=models.SET_NULL, related_name='claim_ledger_entries')
    subject = models.CharField(max_length=512, blank=True, default='')
    predicate = models.CharField(max_length=256, blank=True, default='')
    object = models.TextField(blank=True, default='')
    numeric_value = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    unit = models.CharField(max_length=64, blank=True, default='')
    metric_definition = models.TextField(blank=True, default='')
    time_range = models.JSONField(default=dict)
    completion_status = models.CharField(max_length=32, blank=True, default='')
    person_role = models.CharField(max_length=32, blank=True, default='')
    funding_source = models.CharField(max_length=256, blank=True, default='')
    amount = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    locked = models.BooleanField(default=False)


class ClaimPlan(models.Model):
    STATUS_CHOICES = [('planned', 'planned'), ('needs_replan', 'needs_replan'), ('confirmed', 'confirmed'), ('superseded', 'superseded')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='claim_plans')
    brief = models.ForeignKey('ProposalBrief', on_delete=models.PROTECT, related_name='claim_plans')
    policy = models.ForeignKey('ProposalWorkPolicy', on_delete=models.PROTECT, related_name='claim_plans')
    pack_version = models.ForeignKey(GrantPackVersion, on_delete=models.PROTECT, related_name='claim_plans')
    planning_mode = models.CharField(max_length=32)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='planned')
    requirement_gaps = models.JSONField(default=list)
    evidence_gaps = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)


class SectionPlan(models.Model):
    claim_plan = models.ForeignKey(ClaimPlan, on_delete=models.CASCADE, related_name='section_plans')
    section_schema = models.ForeignKey(SectionSchema, null=True, blank=True, on_delete=models.SET_NULL, related_name='planned_sections')
    section_key = models.CharField(max_length=128)
    title = models.CharField(max_length=256)
    order = models.PositiveIntegerField(default=0)
    claim_intents = models.JSONField(default=list)
    questions = models.JSONField(default=list)
    target_requirements = models.ManyToManyField(GrantRequirement, blank=True, related_name='section_plans')
    proposal_decisions = models.ManyToManyField('ProposalDecision', blank=True, related_name='section_plans')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['claim_plan', 'section_key'], name='sectionplan_plan_key_unique')]


class ClaimIntent(models.Model):
    CLAIM_TYPE_CHOICES = Claim.CLAIM_TYPE_CHOICES

    section_plan = models.ForeignKey(SectionPlan, on_delete=models.CASCADE, related_name='claim_intents_records')
    proposal_decision = models.ForeignKey('ProposalDecision', on_delete=models.PROTECT, related_name='claim_intents')
    claim_type = models.CharField(max_length=32, choices=CLAIM_TYPE_CHOICES)
    text = models.TextField()
    risk_level = models.CharField(max_length=16, default='low')
    addressed_requirements = models.ManyToManyField(GrantRequirement, blank=True, related_name='claim_intents')


class EvidenceNeed(models.Model):
    STATUS_CHOICES = [('open', 'open'), ('satisfied', 'satisfied'), ('blocked', 'blocked')]

    section_plan = models.ForeignKey(SectionPlan, on_delete=models.CASCADE, related_name='evidence_needs')
    claim_intent = models.ForeignKey(ClaimIntent, null=True, blank=True, on_delete=models.CASCADE, related_name='evidence_needs')
    evidence_type = models.CharField(max_length=64)
    description = models.TextField()
    required_for_claim_type = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='open')


class SectionWriterRun(models.Model):
    section = models.ForeignKey('proposals.ProposalSection', on_delete=models.CASCADE, related_name='writer_runs')
    section_plan = models.ForeignKey(SectionPlan, on_delete=models.PROTECT, related_name='writer_runs')
    writing_mode = models.CharField(max_length=32)
    rule_context = models.JSONField(default=list)
    user_evidence_context = models.JSONField(default=list)
    protected_facts = models.JSONField(default=list)
    missing_evidence = models.JSONField(default=list)
    proposal_brief = models.JSONField(default=dict)
    work_policy = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class ClaimSentenceMapping(models.Model):
    claim = models.ForeignKey(Claim, on_delete=models.CASCADE, related_name='sentence_mappings')
    section = models.ForeignKey('proposals.ProposalSection', on_delete=models.CASCADE, related_name='claim_sentence_mappings')
    start_offset = models.PositiveIntegerField()
    end_offset = models.PositiveIntegerField()
    text_snapshot = models.TextField()


class ReviewIssue(models.Model):
    CATEGORY_CHOICES = [('rule', 'rule'), ('fact', 'fact'), ('cross_system', 'cross_system')]
    SEVERITY_CHOICES = [('low', 'low'), ('high', 'high')]
    STATUS_CHOICES = [('open', 'open'), ('auto_fixed', 'auto_fixed'), ('needs_user_decision', 'needs_user_decision'), ('resolved', 'resolved')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='review_issues')
    section = models.ForeignKey('proposals.ProposalSection', on_delete=models.CASCADE, related_name='review_issues')
    claim = models.ForeignKey(Claim, null=True, blank=True, on_delete=models.CASCADE, related_name='review_issues')
    requirement = models.ForeignKey(GrantRequirement, null=True, blank=True, on_delete=models.SET_NULL, related_name='review_issues')
    category = models.CharField(max_length=32, choices=CATEGORY_CHOICES)
    code = models.CharField(max_length=64)
    message = models.TextField()
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES)
    auto_fixable = models.BooleanField(default=False)
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewDecision(models.Model):
    issue = models.OneToOneField(ReviewIssue, on_delete=models.CASCADE, related_name='review_decision')
    session = models.ForeignKey('GrillSession', on_delete=models.CASCADE, related_name='review_decisions')
    decision = models.ForeignKey('ProposalDecision', on_delete=models.CASCADE, related_name='review_decisions')
    action = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)


class ReviewRevision(models.Model):
    section = models.ForeignKey('proposals.ProposalSection', on_delete=models.CASCADE, related_name='review_revisions')
    issue = models.ForeignKey(ReviewIssue, null=True, blank=True, on_delete=models.SET_NULL, related_name='revisions')
    trigger = models.CharField(max_length=64)
    before_text = models.TextField()
    after_text = models.TextField()
    diff = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class EvidenceUsage(models.Model):
    """Immutable snapshot of evidence made available to one model invocation."""

    ROLE_CHOICES = [('planner', 'planner'), ('writer', 'writer'), ('reviser', 'reviser'), ('formatter', 'formatter')]
    EVIDENCE_DOMAIN_CHOICES = [('grant_rule', 'grant_rule'), ('user_evidence', 'user_evidence'), ('pending_review', 'pending_review')]

    workflow_run = models.ForeignKey(WorkflowRun, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    ai_job = models.ForeignKey(AIJob, null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    proposal_section = models.ForeignKey('proposals.ProposalSection', null=True, blank=True, on_delete=models.SET_NULL, related_name='evidence_usages')
    chunk = models.ForeignKey(AIChunk, on_delete=models.PROTECT, related_name='evidence_usages')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    evidence_domain = models.CharField(max_length=32, choices=EVIDENCE_DOMAIN_CHOICES, default='pending_review', db_index=True)
    retrieval_run_id = models.UUIDField(null=True, blank=True, db_index=True)
    query_id = models.CharField(max_length=128, blank=True, default='')
    injection_role = models.CharField(max_length=32, blank=True, default='')
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

    def clean(self):
        super().clean()
        if self.evidence_domain in {'grant_rule', 'user_evidence'} and self.chunk.knowledge_domain != self.evidence_domain:
            raise ValidationError({'evidence_domain': 'evidence usage domain must match its chunk domain.'})


class ProposalIntakeProfile(models.Model):
    RULE_READINESS_CHOICES = [('verified_pack', 'verified_pack'), ('uploaded_pending', 'uploaded_pending'), ('generic_fallback', 'generic_fallback'), ('missing_blocking', 'missing_blocking')]
    CONTENT_MATURITY_CHOICES = [('none', 'none'), ('rough_notes', 'rough_notes'), ('outline', 'outline'), ('partial_draft', 'partial_draft'), ('full_draft', 'full_draft')]
    EVIDENCE_READINESS_CHOICES = [('none', 'none'), ('partial', 'partial'), ('sufficient', 'sufficient'), ('verified', 'verified')]
    TASK_MODE_CHOICES = [('polish_existing', 'polish_existing'), ('refine_outline', 'refine_outline'), ('plan_from_scratch', 'plan_from_scratch')]
    QUALITY_LEVEL_CHOICES = [('quick', 'quick'), ('standard', 'standard'), ('deep', 'deep')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='intake_profiles')
    organization_id = models.CharField(max_length=64, db_index=True)
    version = models.PositiveIntegerField(default=1)
    schema_version = models.CharField(max_length=16, default='v1')
    rule_readiness = models.CharField(max_length=32, choices=RULE_READINESS_CHOICES)
    content_maturity = models.CharField(max_length=32, choices=CONTENT_MATURITY_CHOICES)
    evidence_readiness = models.CharField(max_length=32, choices=EVIDENCE_READINESS_CHOICES)
    task_mode = models.CharField(max_length=32, choices=TASK_MODE_CHOICES)
    quality_level = models.CharField(max_length=16, choices=QUALITY_LEVEL_CHOICES)
    detected_inputs = models.JSONField(default=dict)
    user_overrides = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['proposal', 'version'], name='intakeprofile_proposal_version_unique')]


class ProposalWorkPolicy(models.Model):
    profile = models.OneToOneField(ProposalIntakeProfile, on_delete=models.CASCADE, related_name='work_policy')
    version = models.PositiveIntegerField(default=1)
    grill_mode = models.CharField(max_length=32)
    question_budget = models.PositiveIntegerField(default=5)
    preserve_user_structure = models.BooleanField(default=False)
    planning_mode = models.CharField(max_length=32)
    writing_mode = models.CharField(max_length=32)
    allowed_assumptions = models.JSONField(default=list)
    enabled_reviewers = models.JSONField(default=list)
    max_auto_revisions = models.PositiveIntegerField(default=0)
    blocking_policy = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class GrillSession(models.Model):
    STATUS_CHOICES = [('active', 'active'), ('completed', 'completed'), ('skipped', 'skipped'), ('blocked', 'blocked'), ('user_ended', 'user_ended')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='grill_sessions')
    profile = models.ForeignKey(ProposalIntakeProfile, on_delete=models.PROTECT, related_name='grill_sessions')
    policy = models.ForeignKey(ProposalWorkPolicy, on_delete=models.PROTECT, related_name='grill_sessions')
    mode = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='active')
    completion_reason = models.CharField(max_length=64, blank=True, default='')
    question_count = models.PositiveIntegerField(default=0)
    knowledge_snapshot = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class GrillDecisionNode(models.Model):
    STATUS_CHOICES = [('pending', 'pending'), ('answered', 'answered'), ('skipped', 'skipped'), ('not_applicable', 'not_applicable'), ('auto_resolved', 'auto_resolved')]

    session = models.ForeignKey(GrillSession, on_delete=models.CASCADE, related_name='nodes')
    node_id = models.CharField(max_length=64)
    topic = models.CharField(max_length=64)
    question = models.TextField()
    question_type = models.CharField(max_length=32)
    depends_on = models.JSONField(default=list)
    blocking = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=0)
    recommended_answer = models.TextField(blank=True, default='')
    recommendation_reason = models.TextField(blank=True, default='')
    rule_evidence_ids = models.JSONField(default=list)
    user_evidence_ids = models.JSONField(default=list)
    affected_sections = models.JSONField(default=list)
    status = models.CharField(max_length=24, choices=STATUS_CHOICES, default='pending')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'node_id'], name='grillnode_session_nodeid_unique')]
        indexes = [models.Index(fields=['session', 'status', 'priority'], name='grillnode_session_status_idx')]


class GrillAnswer(models.Model):
    ACTION_CHOICES = [('adopt_recommendation', 'adopt_recommendation'), ('modify_and_adopt', 'modify_and_adopt'), ('custom', 'custom'), ('skip', 'skip'), ('end', 'end')]

    node = models.ForeignKey(GrillDecisionNode, on_delete=models.CASCADE, related_name='answers')
    action = models.CharField(max_length=32, choices=ACTION_CHOICES)
    answer = models.TextField(blank=True, default='')
    idempotency_key = models.CharField(max_length=128)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='grill_answers')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['node', 'idempotency_key'], name='grillanswer_node_idempotency_unique')]


class ProposalDecision(models.Model):
    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='intake_decisions')
    session = models.ForeignKey(GrillSession, on_delete=models.CASCADE, related_name='decisions')
    node = models.OneToOneField(GrillDecisionNode, on_delete=models.CASCADE, related_name='decision')
    topic = models.CharField(max_length=64)
    value = models.TextField()
    source = models.CharField(max_length=32, default='user_confirmed')
    version = models.PositiveIntegerField(default=1)
    affected_sections = models.JSONField(default=list)
    confirmed_at = models.DateTimeField(auto_now_add=True)


class ProposalBrief(models.Model):
    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='intake_briefs')
    session = models.OneToOneField(GrillSession, on_delete=models.CASCADE, related_name='brief')
    version = models.PositiveIntegerField(default=1)
    content = models.JSONField(default=dict)
    confirmed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ProposalDecisionLedger(models.Model):
    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='decision_ledger_entries')
    session = models.ForeignKey(GrillSession, on_delete=models.CASCADE, related_name='ledger_entries')
    decision = models.ForeignKey(ProposalDecision, null=True, blank=True, on_delete=models.SET_NULL, related_name='ledger_entries')
    event_type = models.CharField(max_length=32)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class GrantGlossary(models.Model):
    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='grant_glossary')
    term = models.CharField(max_length=256)
    definition = models.TextField()
    source = models.CharField(max_length=32, default='user_confirmed')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['proposal', 'term'], name='grantglossary_proposal_term_unique')]


class AssumptionRegister(models.Model):
    RISK_CHOICES = [('low', 'low'), ('high', 'high')]

    proposal = models.ForeignKey('proposals.Proposal', on_delete=models.CASCADE, related_name='assumptions')
    session = models.ForeignKey(GrillSession, on_delete=models.CASCADE, related_name='assumptions')
    assumption = models.TextField()
    risk_level = models.CharField(max_length=8, choices=RISK_CHOICES)
    status = models.CharField(max_length=32, default='open')
    created_at = models.DateTimeField(auto_now_add=True)


class Phase11SeedMap(models.Model):
    kind = models.CharField(max_length=32)
    external_id = models.CharField(max_length=160)
    target_id = models.PositiveIntegerField()
    source_sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['kind', 'external_id'], name='phase11seedmap_kind_external_unique')]
