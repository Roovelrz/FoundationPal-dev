import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from ai.domain_retrieval import RuleQuery
from ai.embedding_service import EmbeddingService
from ai.models import Phase11SeedMap
from ai.query_router import search_grant_rules


def _ratio(value, total):
    return round(value / total, 4) if total else None


class Command(BaseCommand):
    help = 'Run the leak-checked isolated BGE Rule RAG baseline for Phase 11.'

    def add_arguments(self, parser):
        parser.add_argument('--input-dir', required=True)
        parser.add_argument('--model-path', required=True)
        parser.add_argument('--output', default='reports/phase11-bge-rule-eval.json')
        parser.add_argument('--mapping-kind-prefix', default='phase11_bge_')

    def handle(self, *args, **options):
        os.environ['EMBEDDING_BACKEND'] = 'bge'
        os.environ['BGE_MODEL_PATH'] = options['model_path']
        EmbeddingService.reset()
        service = EmbeddingService.instance()
        if service.backend != 'bge':
            raise CommandError('real_embedding_backend_required')
        prefix = options['mapping_kind_prefix']
        mapping = {(row.kind.removeprefix(prefix), row.external_id): row.target_id for row in Phase11SeedMap.objects.filter(kind__startswith=prefix)}
        root = Path(options['input_dir'])
        cases = json.loads((root / '01_rule_requirement_mapping.json').read_text(encoding='utf-8'))['cases']
        hits = {1: 0, 3: 0, 5: 0, 20: 0, 40: 0}
        rows = []
        for case in cases:
            gold = {mapping[('grant_requirement', value)] for value in case['requirement_ids']}
            pack_id = mapping[('grant_pack_version', case['grant_pack_version_id'])]
            result = search_grant_rules(RuleQuery(pack_version_id=pack_id, year=case['applicable_year'], user_question=case['query']))
            final_ids = [row['requirement_id'] for row in result['results']]
            candidates = result['audit_candidates']
            for k in (1, 3, 5):
                hits[k] += bool(gold.intersection(final_ids[:k]))
            for k in (20, 40):
                hits[k] += bool(gold.intersection(candidates[:k]))
            rows.append({'case_id': case['case_id'], 'gold_rank': next((index for index, value in enumerate(candidates, start=1) if value in gold), None), 'final_hit_at_5': bool(gold.intersection(final_ids[:5]))})
        payload = {
            'evaluation_scope': 'phase11_bge_isolated_rule_corpus',
            'embedding': service.health(),
            'case_count': len(cases),
            'candidate_recall_at_20': _ratio(hits[20], len(cases)),
            'candidate_recall_at_40': _ratio(hits[40], len(cases)),
            'final_recall_at_1': _ratio(hits[1], len(cases)),
            'final_recall_at_3': _ratio(hits[3], len(cases)),
            'final_recall_at_5': _ratio(hits[5], len(cases)),
            'rows': rows,
        }
        output = Path(options['output'])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS('phase11_bge_rule_eval_complete'))
