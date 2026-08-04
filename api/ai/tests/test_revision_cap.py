from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from orgs.models import Organization
from proposals.models import Proposal, ProposalSection


@override_settings(AI_PROVIDER='stub', PROPOSAL_SECTION_REVISION_CAP=1)
def test_revisions_remain_available_when_legacy_cap_setting_is_present(db):  # noqa: D103
    client = APIClient()
    user = get_user_model().objects.create_user(username='unlimited-reviser', password='test12345')
    client.force_authenticate(user=user)
    org = Organization.objects.create(name='Unlimited revisions', admin=user)
    proposal = Proposal.objects.create(author=user, org=org, state='draft', content={})
    section = ProposalSection.objects.create(proposal=proposal, key='summary', title='摘要')

    first = client.post(
        '/api/ai/write',
        {'proposal_id': proposal.id, 'section_id': section.key, 'answers': {'目标': '验证不限次数修订'}},
        format='json',
    )
    assert first.status_code == 200, first.content  # type: ignore[attr-defined]
    text = first.json()['draft_text']  # type: ignore[call-arg]

    for index in range(6):
        response = client.post(
            '/api/ai/revise',
            {
                'proposal_id': proposal.id,
                'section_id': section.key,
                'base_text': text,
                'change_request': f'第 {index + 1} 次修订',
            },
            format='json',
        )
        assert response.status_code == 200, response.content  # type: ignore[attr-defined]
        text = response.json()['draft_text']  # type: ignore[call-arg]

    section.refresh_from_db()
    assert len(section.revisions) == 6
    detail = client.get(f'/api/proposals/{proposal.id}')  # type: ignore[attr-defined]
    section_data = detail.json()['sections'][0]  # type: ignore[call-arg]
    assert 'remaining_revision_slots' not in section_data
