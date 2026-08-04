from rest_framework import serializers

from .models import Proposal


class ProposalSerializer(serializers.ModelSerializer):
    author = serializers.ReadOnlyField(source='author.id')
    can_unarchive = serializers.SerializerMethodField()
    call_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    # Org and local project number are assigned server-side from the selected workspace.
    org = serializers.PrimaryKeyRelatedField(read_only=True)
    # Read-only section listing for authoring and approval state. Order is
    # guaranteed by model Meta.
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Proposal
        fields = [
            'id',
            'author',
            'org',
            'workspace_number',
            'state',
            'last_edited',
            'downloads',
            'content',
            'final_markdown',
            'schema_version',
            'shared_with',
            'archived_at',
            'call_url',
            'can_unarchive',
            'created_at',
            'sections',
        ]

    read_only_fields = ['last_edited', 'downloads', 'created_at', 'org', 'workspace_number', 'final_markdown']

    def get_can_unarchive(self, obj: Proposal) -> bool:
        return True

    def update(self, instance: Proposal, validated_data):
        # Enforce call_url immutability (write-once). If already set, drop any new value.
        if instance.call_url:
            validated_data.pop('call_url', None)
        return super().update(instance, validated_data)

    def get_sections(self, obj: Proposal):  # pragma: no cover - simple serialization
        try:
            # Access related manager; mypy/ruff (typing) may not see dynamic related_name
            qs = getattr(obj, 'sections', []).all()  # type: ignore[attr-defined]
            return [
                {
                    'id': s.id,
                    'key': s.key,
                    'title': s.title,
                    'order': s.order,
                    'state': s.state,
                    'draft_content': s.draft_content,
                    'approved_content': s.approved_content,
                    'locked': s.locked,
                    'questions': list((s.metadata or {}).get('questions') or [])[:20],
                    'answers': dict((s.metadata or {}).get('answers') or {}),
                    'previous_draft': str((s.revisions or [])[-1].get('from') or '') if s.revisions else '',
                }
                for s in qs
            ]
        except Exception:
            return []
