from unittest.mock import Mock

from django.test import SimpleTestCase

from ai.providers.deepseek import DeepSeekProvider


class DeepSeekPlannerRegressionTests(SimpleTestCase):
    def test_invalid_model_plan_uses_nonempty_guided_questions(self):
        provider = DeepSeekProvider.__new__(DeepSeekProvider)
        provider._call = Mock(return_value='not valid json')

        result = provider.plan(grant_url=None, text_spec='测试研究方向')

        self.assertEqual(len(result['sections']), 4)
        self.assertTrue(all(section['questions'] for section in result['sections']))

    def test_application_system_changes_each_role_prompt(self):
        provider = DeepSeekProvider.__new__(DeepSeekProvider)
        provider.model = 'test-model'
        provider._call = Mock(return_value='not valid json')
        systems = ('nsfc', 'provincial', 'university', 'other')
        role_prompts = {'plan': [], 'write': [], 'revise': [], 'format': []}
        first_questions = []

        for application_system in systems:
            plan = provider.plan(
                grant_url=None,
                text_spec='测试研究方向',
                application_system=application_system,
            )
            role_prompts['plan'].append(provider._call.call_args.args[0])
            first_questions.append(plan['sections'][0]['questions'][0])

            provider.write(
                section_id='section',
                answers={'问题': '回答'},
                application_system=application_system,
            )
            role_prompts['write'].append(provider._call.call_args.args[0])

            provider.revise(
                base_text='原文',
                change_request='修订',
                application_system=application_system,
            )
            role_prompts['revise'].append(provider._call.call_args.args[0])

            provider.format_final(
                full_text='正文',
                application_system=application_system,
            )
            role_prompts['format'].append(provider._call.call_args.args[0])

        self.assertEqual(len(set(first_questions)), 4)
        for prompts in role_prompts.values():
            self.assertEqual(len(set(prompts)), 4)

    def test_unknown_application_system_defaults_to_nsfc(self):
        provider = DeepSeekProvider.__new__(DeepSeekProvider)
        provider._call = Mock(return_value='not valid json')

        result = provider.plan(
            grant_url=None,
            text_spec='测试研究方向',
            application_system='legacy-value',
        )

        self.assertEqual(result['sections'][0]['section_key'], 'lixiangyiju')
