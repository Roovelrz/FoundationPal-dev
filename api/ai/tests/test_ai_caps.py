from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(
    AI_PROVIDER='stub',
    DEBUG=False,
    AI_RATE_PER_MIN_PRO=1,
    AI_DAILY_REQUEST_CAP_PRO=1,
    AI_MONTHLY_TOKENS_CAP_PRO=1,
)
def test_legacy_ai_cap_settings_do_not_limit_authenticated_users(db):  # noqa: D103
    client = APIClient()
    user = get_user_model().objects.create_user(username='unlimited-ai', password='test12345')
    client.force_authenticate(user=user)
    org = Organization.objects.create(name='Unlimited AI', admin=user)
    proposal = Proposal.objects.create(author=user, org=org, content={})
    section = ProposalSection.objects.create(proposal=proposal, key='summary', title='摘要')

    for index in range(3):
        response = client.post(
            '/api/ai/write',
            {
                'proposal_id': proposal.id,
                'section_id': section.key,
                'answers': {'目标': f'第 {index + 1} 次生成'},
            },
            format='json',
        )
        assert response.status_code == 200, response.content  # type: ignore[attr-defined]
