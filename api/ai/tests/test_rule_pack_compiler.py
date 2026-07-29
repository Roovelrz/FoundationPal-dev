from django.test import TestCase

from ai.ingestion import create_resource_with_chunks
from ai.models import GrantPack, GrantPackVersion, GrantProgram
from ai.rule_pack_compiler import bind_rule_pack_documents, compile_rule_pack, publish_rule_pack


class RulePackCompilerTests(TestCase):
    def setUp(self):
        program = GrantProgram.objects.create(name='NSFC', program_type='youth', authority='NSFC')
        pack = GrantPack.objects.create(program=program, code='nsfc-youth', name='NSFC Youth')
        self.version = GrantPackVersion.objects.create(pack=pack, year=2026, version='v1')

    def test_compile_and_publish_rule_pack(self):
        resource = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='申请人必须提交预算说明。')
        resource.knowledge_domain = 'grant_rule'
        resource.classification_status = 'pack_draft'
        resource.save(update_fields=['knowledge_domain', 'classification_status'])
        bind_rule_pack_documents(pack_version=self.version, resources=[resource])
        compile_rule_pack(pack_version=self.version)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, 'validated')
        self.assertEqual(self.version.requirements.count(), 1)
        self.assertEqual(self.version.section_schemas.count(), 1)
        publish_rule_pack(pack_version=self.version)
        self.version.refresh_from_db()
        self.assertEqual(self.version.status, 'published')

    def test_duplicate_sha_is_rejected(self):
        one = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='必须提交。')
        two = create_resource_with_chunks(type_='guideline', title='Guide', source_url='', full_text='必须提交。', organization_id='other')
        for resource in (one, two):
            resource.knowledge_domain = 'grant_rule'
            resource.classification_status = 'pack_draft'
            resource.save(update_fields=['knowledge_domain', 'classification_status'])
        with self.assertRaisesRegex(ValueError, 'duplicate_rule_pack_document'):
            bind_rule_pack_documents(pack_version=self.version, resources=[one, two])
