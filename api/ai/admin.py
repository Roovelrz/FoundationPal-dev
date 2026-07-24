from django.contrib import admin
from .models import AIResource, AIChunk, AIJob, AIMetric, AIPromptTemplate, AIJobContext, AIMemory, EvidenceUsage, ToolInvocation


@admin.register(AIResource)
class AIResourceAdmin(admin.ModelAdmin):
    list_display = ("id", "source_type", "display_name", "organization_id", "status", "created_at")
    search_fields = ("title", "display_name", "source_url", "source_type", "sha256")
    list_filter = ("source_type", "status", "created_at")
    date_hierarchy = "created_at"


@admin.register(AIChunk)
class AIChunkAdmin(admin.ModelAdmin):
    list_display = ("id", "resource", "chunk_index", "token_count", "created_at")
    search_fields = ("text", "embedding_key")
    list_filter = ("created_at",)
    raw_id_fields = ("resource",)


@admin.register(AIJob)
class AIJobAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "status", "org_id", "created_by", "created_at")
    list_filter = ("type", "status", "org_id")
    search_fields = ("id", "org_id", "error_text")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AIMetric)
class AIMetricAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "model_id", "duration_ms", "tokens_used", "success", "org_id", "created_at")
    list_filter = ("type", "model_id", "success", "org_id")
    search_fields = ("model_id", "org_id", "error_text")
    readonly_fields = ("created_at",)


@admin.register(AIPromptTemplate)
class AIPromptTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "role", "active", "created_at")
    list_filter = ("role", "active")
    search_fields = ("name", "role")


@admin.register(AIJobContext)
class AIJobContextAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "prompt_template", "prompt_version", "created_at")
    search_fields = ("job__id",)


@admin.register(AIMemory)
class AIMemoryAdmin(admin.ModelAdmin):
    list_display = ("id", "org_id", "section_id", "usage_count")
    search_fields = ("text",)


@admin.register(EvidenceUsage)
class EvidenceUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'ai_job', 'proposal_section', 'chunk', 'used_in_prompt', 'cited_by_model', 'created_at')
    list_filter = ('role', 'used_in_prompt', 'cited_by_model')


@admin.register(ToolInvocation)
class ToolInvocationAdmin(admin.ModelAdmin):
    list_display = ('id', 'tool_name', 'caller_role', 'organization_id', 'proposal_id', 'status', 'created_at')
    list_filter = ('tool_name', 'caller_role', 'status')
    search_fields = ('organization_id', 'idempotency_key', 'error_code')
    readonly_fields = ('created_at', 'updated_at', 'request_hash', 'result_json')
