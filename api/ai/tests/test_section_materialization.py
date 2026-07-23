from django.test import TestCase
from django.contrib.auth import get_user_model
from orgs.models import Organization
from proposals.models import ProposalSection, Proposal


class SectionMaterializationTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='planner', password='p')

    def test_plan_creates_sections_from_blueprint(self):
        self.client.force_login(self.user)
        # First create a proposal to reference.
        # Minimal proposal create (content just placeholder); call_url optional
        p_resp = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'Base'}},
            content_type='application/json',
        )
        self.assertIn(p_resp.status_code, (200, 201))
        pid = p_resp.json()['id']
        blueprint = [
            {
                'id': 'Introduction',
                'title': 'Introduction',
                'order': 0,
                'draft': 'Intro draft',
                'questions': ['What is the objective?', 'What is the impact?'],
            },
            {'id': 'Objectives', 'title': 'Objectives', 'order': 1},
        ]
        from unittest.mock import patch

        with patch('ai.views.get_provider') as gp:
            provider = gp.return_value
            provider.plan.return_value = {'schema_version': 'v1', 'sections': blueprint}
            resp = self.client.post(
                '/api/ai/plan',
                data={'proposal_id': pid, 'grant_url': 'https://example.com/call', 'text_spec': 'Spec'},
                content_type='application/json',
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn('plan', body)
        self.assertEqual(body['schema_version'], 'v1')
        self.assertEqual(body['sections'], blueprint)
        self.assertIn('created_sections', body)
        self.assertEqual(set(body['created_sections']), {'introduction', 'objectives'})
        sections = ProposalSection.objects.filter(proposal_id=pid).order_by('order').values_list('key', 'title')
        self.assertEqual(list(sections), [('introduction', 'Introduction'), ('objectives', 'Objectives')])
        intro = ProposalSection.objects.get(proposal_id=pid, key='introduction')
        self.assertTrue(intro.draft_content.startswith('Intro draft'))
        self.assertEqual(
            intro.metadata['inputs'],
            ['What is the objective?', 'What is the impact?'],
        )
        detail = self.client.get(f'/api/proposals/{pid}/')
        self.assertEqual(
            detail.json()['sections'][0]['inputs'],
            ['What is the objective?', 'What is the impact?'],
        )

    def test_plan_idempotent_updates_title_and_order(self):
        self.client.force_login(self.user)
        # Create initial proposal via API to ensure org provisioning/path consistency
        r = self.client.post(
            '/api/proposals/',
            data={'content': {'title': 'X'}},
            content_type='application/json',
        )
        self.assertIn(r.status_code, (200, 201))
        p_id = r.json()['id']
        p = Proposal.objects.get(id=p_id)
        ProposalSection.objects.create(proposal=p, key='intro', title='Old', order=5)
        new_blueprint = [
            {'key': 'intro', 'title': 'New Intro', 'order': 0},
            {'key': 'methods', 'title': 'Methods', 'order': 1},
        ]
        from unittest.mock import patch

        with patch('ai.views.get_provider') as gp:
            provider = gp.return_value
            provider.plan.return_value = {'schema_version': 'v1', 'sections': new_blueprint}
            for _ in range(2):
                resp = self.client.post(
                    '/api/ai/plan',
                    data={'proposal_id': p_id, 'grant_url': 'https://example.com/call', 'text_spec': 'Spec'},
                    content_type='application/json',
                )
        self.assertEqual(resp.status_code, 200)
        keys = list(ProposalSection.objects.filter(proposal=p).order_by('order').values_list('key', flat=True))
        self.assertEqual(keys, ['intro', 'methods'])
        self.assertEqual(ProposalSection.objects.filter(proposal=p).count(), 2)
        intro = ProposalSection.objects.get(proposal=p, key='intro')
        self.assertEqual(intro.title, 'New Intro')
        self.assertEqual(intro.order, 0)

    def test_plan_requires_proposal_id(self):
        self.client.force_login(self.user)

        resp = self.client.post(
            '/api/ai/plan',
            data={'text_spec': 'Spec'},
            content_type='application/json',
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['error'], 'proposal_id_required')

    def test_plan_rejects_inaccessible_proposal(self):
        other_user = get_user_model().objects.create_user(username='other-planner', password='p')
        other_org = Organization.objects.create(name='other-org', admin=other_user)
        other_proposal = Proposal.objects.create(author=other_user, org=other_org, content={})
        self.client.force_login(self.user)

        resp = self.client.post(
            '/api/ai/plan',
            data={'proposal_id': other_proposal.id, 'text_spec': 'Spec'},
            content_type='application/json',
        )

        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()['error'], 'proposal_not_found')
