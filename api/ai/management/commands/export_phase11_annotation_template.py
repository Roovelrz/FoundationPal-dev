import json
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Export the 150 synthetic cases and 15 manual anchors as a Phase 11 human annotation template.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='../data/phase11_annotation_template.json')

    def handle(self, *args, **options):
        repository = Path.cwd().parent
        synthetic = json.loads((repository / 'data' / 'rag_synthetic_eval_v1.json').read_text(encoding='utf-8')).get('cases', [])
        anchors = json.loads((repository / 'data' / 'rag_eval_questions.json').read_text(encoding='utf-8'))
        cases = []
        for item in synthetic:
            cases.append({
                'case_id': f"synthetic:{item['case_id']}",
                'annotation_status': 'pending_human_review',
                'domain': 'pending',
                'query': item['query'],
                'answer_state': 'pending',
                'requirement_ids': [],
                'user_evidence_ids': [],
                'gold_chunk_ids': item.get('source_chunk_ids', []),
                'source_document_ids': item.get('source_document_ids', []),
                'annotation_notes': '',
                'source': {'kind': 'synthetic', 'source_type': item.get('source_type'), 'reference_answer': item.get('reference_answer', '')},
            })
        for item in anchors:
            cases.append({
                'case_id': f"anchor:{item['id']}",
                'annotation_status': 'pending_human_review',
                'domain': 'pending',
                'query': item['query'],
                'answer_state': 'pending',
                'requirement_ids': [],
                'user_evidence_ids': [],
                'gold_chunk_ids': item.get('gold_chunk_ids', []),
                'source_document_ids': [],
                'annotation_notes': '',
                'source': {'kind': 'manual_anchor', 'has_answer': item.get('has_answer'), 'allowed_source_types': item.get('allowed_source_types', [])},
            })
        output = Path(options['output'])
        if not output.is_absolute():
            output = Path.cwd() / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({'schema_version': 'phase11_annotation_v1', 'cases': cases}, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'phase11_annotation_template_exported: {len(cases)} cases -> {output}'))
