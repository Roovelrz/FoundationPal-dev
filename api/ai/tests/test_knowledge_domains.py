from django.test import SimpleTestCase, override_settings

from ai.knowledge_domains import KnowledgeDomain, PENDING_CLASSIFICATION, is_knowledge_domain


class KnowledgeDomainContractTests(SimpleTestCase):
    def test_only_two_indexable_knowledge_domains_exist(self):
        self.assertEqual(
            set(KnowledgeDomain.values),
            {'grant_rule', 'user_evidence'},
        )
        self.assertTrue(is_knowledge_domain(KnowledgeDomain.GRANT_RULE))
        self.assertTrue(is_knowledge_domain(KnowledgeDomain.USER_EVIDENCE))
        self.assertFalse(is_knowledge_domain(PENDING_CLASSIFICATION))

    @override_settings(
        DUAL_RAG_ENABLED=True,
        RULE_RAG_HYBRID_ENABLED=True,
        USER_RAG_HYBRID_ENABLED=False,
        RERANK_ENABLED=False,
        CLAIM_LEVEL_GROUNDING_ENABLED=True,
    )
    def test_feature_flags_can_be_enabled_independently_in_tests(self):
        from django.conf import settings

        self.assertTrue(settings.DUAL_RAG_ENABLED)
        self.assertTrue(settings.RULE_RAG_HYBRID_ENABLED)
        self.assertFalse(settings.USER_RAG_HYBRID_ENABLED)
        self.assertFalse(settings.RERANK_ENABLED)
        self.assertTrue(settings.CLAIM_LEVEL_GROUNDING_ENABLED)
