from unittest.mock import Mock

from django.test import SimpleTestCase

from ai.providers.deepseek import APPLICATION_SYSTEM_PROFILES, DeepSeekProvider


class OtherApplicationProfileTests(SimpleTestCase):
    def test_other_plan_uses_a_simplified_research_system(self):
        provider = DeepSeekProvider.__new__(DeepSeekProvider)
        provider._call = Mock(return_value='{}')

        plan = provider.plan(
            grant_url=None,
            text_spec='通用研究项目测试方向',
            application_system='other',
        )

        system_prompt = provider._call.call_args.args[0]
        self.assertIn('通用研究型项目申报规划专家', system_prompt)
        self.assertEqual(
            [section['title'] for section in plan['sections']],
            ['（一）项目背景与问题', '（二）目标与研究内容', '（三）研究方法与实施方案', '（四）条件与预期成果'],
        )
        self.assertIn('二至三项研究内容或任务', APPLICATION_SYSTEM_PROFILES['other']['writer_system'])
        self.assertIn('问题或背景、目标、研究内容、方法、条件与成果', APPLICATION_SYSTEM_PROFILES['other']['writer_system'])
