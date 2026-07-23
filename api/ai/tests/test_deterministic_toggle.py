from django.test import override_settings
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from orgs.models import Organization
from proposals.models import Proposal, ProposalSection

User = get_user_model()


def login(client, username='detuser'):
    user = User.objects.create_user(username=username, password='test12345')
    org = Organization.objects.create(name=f'{username} Org', admin=user)
    proposal = Proposal.objects.create(author=user, org=org, content={})
    ProposalSection.objects.create(
        proposal=proposal,
        key='summary',
        state='approved',
        approved_content='Hello World',
        content='Hello World',
        locked=True,
    )
    resp = client.post('/api/token', {'username': username, 'password': 'test12345'})
    token = resp.json()['access']
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
    return proposal


def test_format_deterministic_default(db):
    client = APIClient()
    proposal = login(client)
    r1 = client.post('/api/ai/format', {'proposal_id': proposal.id}, format='json')
    r2 = client.post('/api/ai/format', {'proposal_id': proposal.id}, format='json')
    assert r1.status_code == 200 and r2.status_code == 200  # type: ignore[attr-defined]
    assert r1.json()['formatted_text'] == r2.json()['formatted_text']  # type: ignore[attr-defined]


def test_format_non_deterministic_toggle_off(db):
    client = APIClient()
    proposal = login(client, username='detuser2')
    with override_settings(AI_DETERMINISTIC_SAMPLING=False):
        r1 = client.post('/api/ai/format', {'proposal_id': proposal.id}, format='json')
        r2 = client.post('/api/ai/format', {'proposal_id': proposal.id}, format='json')
    assert r1.status_code == 200 and r2.status_code == 200  # type: ignore[attr-defined]
    # With stub providers output is currently identical; ensure flag propagates marker in text
    # GeminiProvider / LocalStubProvider embed deterministic=1 marker when True; absence implies toggle off
    assert 'deterministic=1' not in r1.json()['formatted_text']  # type: ignore[attr-defined]
    assert 'deterministic=1' not in r2.json()['formatted_text']  # type: ignore[attr-defined]


def test_format_deterministic_toggle_on(db):
    client = APIClient()
    proposal = login(client, username='detuser3')
    with override_settings(AI_DETERMINISTIC_SAMPLING=True):
        r = client.post('/api/ai/format', {'proposal_id': proposal.id}, format='json')
    assert r.status_code == 200  # type: ignore[attr-defined]
    assert 'deterministic=1' in r.json()['formatted_text']  # type: ignore[attr-defined]
