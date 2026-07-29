import json
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand


LABELS = {
    'supported': ('complete_support', '冻结夹具标注为事实与规则均有支持。'),
    'missing_evidence': ('unsupported', '冻结夹具标注为缺少必要用户证据。'),
    'conflicted': ('not_evaluable', '冻结夹具标注为证据冲突，不能推断蕴含结论。'),
    'locked': ('not_evaluable', '冻结夹具标注为锁定状态，不能推断蕴含结论。'),
}


class Command(BaseCommand):
    help = 'Create traceable developer-initial citation labels from verified claim-grounding fixtures.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)

    def handle(self, *args, **options):
        root = Path(options['input_dir'])
        source = json.loads((root / '06_claim_grounding.json').read_text(encoding='utf-8'))
        cases = []
        for item in source['cases']:
            label, rationale = LABELS[item['expected_status']]
            cases.append({
                'case_id': item['case_id'],
                'claim_external_id': item['claim_external_id'],
                'label': label,
                'review_status': 'synthetic_test_developer_review',
                'reviewer': 'synthetic_test_developer_review',
                'review_date': str(date.today()),
                'source_pages': [{'page': 1, 'source_type': 'synthetic_test_fixture'}],
                'source_page_status': 'synthetic_test_fixture_not_business_evidence',
                'rationale': rationale,
                'source_annotation': item['annotation_notes'],
            })
        payload = {
            'dataset': 'phase11_claim_citation_entailment_labels',
            'annotation_level': 'synthetic_test_developer_review',
            'source_fixture': '06_claim_grounding.json',
            'cases': cases,
        }
        (root / '06_claim_citation_entailment_labels.json').write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8'
        )
        self.stdout.write(self.style.SUCCESS('phase11_developer_citation_labels_complete'))
