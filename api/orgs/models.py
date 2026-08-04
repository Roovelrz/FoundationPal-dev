from django.conf import settings
from django.db import models
import secrets
from datetime import date
from django.utils import timezone


class Organization(models.Model):
    name = models.CharField(max_length=200)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='admin_organizations')
    description = models.TextField(blank=True, default='')
    files_meta = models.JSONField(default=dict, blank=True)
    next_proposal_number = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class OrgUser(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('member', 'Member'),
    )
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='org_memberships')
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default='member')

    class Meta:
        unique_together = ('org', 'user')

    def __str__(self) -> str:  # pragma: no cover
        return f'{self.user_id}@{self.org_id}:{self.role}'


class OrgInvite(models.Model):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('member', 'Member'),
    )
    org = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='invites')
    email = models.EmailField()
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default='member')
    token = models.CharField(max_length=128, unique=True, editable=False)
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_org_invites')
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Optional: Expiry time. If null, treated as non-expiring; default is set on create via save().
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['org', 'email']),
        ]

    def save(self, *args, **kwargs):  # pragma: no cover - simple token gen
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        # Set a default expiry if not set: ORG_INVITE_TTL_DAYS (default 14 days)
        if self.expires_at is None:
            try:
                from django.conf import settings as dj_settings

                ttl_days = int(getattr(dj_settings, 'ORG_INVITE_TTL_DAYS', 14) or 0)
            except Exception:
                ttl_days = 14
            if ttl_days and ttl_days > 0:
                self.expires_at = timezone.now() + timezone.timedelta(days=ttl_days)
        return super().save(*args, **kwargs)

    def is_active(self) -> bool:
        if self.accepted_at is not None or self.revoked_at is not None:
            return False
        if self.expires_at and timezone.now() >= self.expires_at:
            return False
        return True


class OrgProposalAllocation(models.Model):
    """Enterprise-only: per-admin per-org monthly proposal allocation preference.
    allocation = 0 means participate proportionally in the unallocated remainder.
    """

    admin = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='org_allocations')
    org = models.ForeignKey('orgs.Organization', on_delete=models.CASCADE, related_name='admin_allocations')
    month = models.DateField(default=date.today)
    allocation = models.IntegerField(default=0)

    class Meta:
        unique_together = ('admin', 'org', 'month')
