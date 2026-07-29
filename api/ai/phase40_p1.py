import json
import re
from pathlib import Path

from .models import EvidenceFact, Phase11SeedMap, UserEvidence


def _normalized(value):
    return ''.join(re.findall(r'[0-9A-Za-z\u4e00-\u9fff]+', value or '')).lower()


def _eight_character_leaks(query, source, allowed_terms):
    query_text = _normalized(query)
    source_text = _normalized(source)
    allowed = [_normalized(value) for value in allowed_terms]
    values = set()
    for index in range(max(len(query_text) - 7, 0)):
        value = query_text[index:index + 8]
        if value in source_text and not any(value in term for term in allowed):
            values.add(value)
    return sorted(values)


def validate_holdout(root, mapping_prefix):
    root = Path(root)
    rewrites = json.loads((root / '00_p1_evidence_query_rewrites.json').read_text(encoding='utf-8'))['cases']
    evidence = json.loads((root / '02_user_evidence_grounding.json').read_text(encoding='utf-8'))['cases']
    mixed = json.loads((root / '04_mixed_dual_domain.json').read_text(encoding='utf-8'))['cases']
    leakage = json.loads((root / '05_cross_organization_leakage.json').read_text(encoding='utf-8'))['cases']
    bindings = json.loads((root / 'phase40_p1_source_bindings.json').read_text(encoding='utf-8'))['cases']
    errors = []
    if not all(len(values) == len(rewrites) for values in (evidence, mixed, leakage, bindings)):
        errors.append('p1_fixture_count_mismatch')
    maps = {
        row.external_id: row.target_id
        for row in Phase11SeedMap.objects.filter(kind=f'{mapping_prefix}user_evidence')
    }
    evidence_by_rewrite = {row.get('rewrite_id'): row for row in evidence}
    mixed_by_rewrite = {row.get('evidence_rewrite_id'): row for row in mixed}
    leakage_by_rewrite = {row.get('rewrite_id'): row for row in leakage}
    bindings_by_external = {row['external_id']: row for row in bindings}
    exact_leaks = []
    ngram_leaks = []
    for row in rewrites:
        rewrite_id = row['rewrite_id']
        query = row.get('query', '')
        if not query or row.get('reviewer') != 'roovel' or not row.get('exact_leak_check_passed') or not row.get('ngram_leak_check_passed'):
            errors.append(f'incomplete_rewrite:{rewrite_id}')
        if evidence_by_rewrite.get(rewrite_id, {}).get('query') != query:
            errors.append(f'evidence_query_mismatch:{rewrite_id}')
        if mixed_by_rewrite.get(rewrite_id, {}).get('evidence_query') != query:
            errors.append(f'mixed_query_mismatch:{rewrite_id}')
        leakage_case = leakage_by_rewrite.get(rewrite_id, {})
        if leakage_case.get('query') != query:
            errors.append(f'leakage_query_mismatch:{rewrite_id}')
        source_id = row['source_user_evidence_id']
        target_id = maps.get(source_id)
        if not target_id:
            errors.append(f'missing_p0v5_source:{rewrite_id}')
            continue
        item = UserEvidence.objects.select_related('chunk__resource').get(pk=target_id)
        facts = EvidenceFact.objects.filter(user_evidence=item)
        source = ' '.join([item.chunk.text, item.chunk.resource.display_name, *[f'{fact.subject} {fact.predicate} {fact.object}' for fact in facts]])
        if _normalized(query) in _normalized(source):
            exact_leaks.append(rewrite_id)
        overlaps = _eight_character_leaks(query, source, row.get('allowed_overlap_terms', []))
        if overlaps:
            ngram_leaks.append({'rewrite_id': rewrite_id, 'overlaps': overlaps})
        for forbidden_id in leakage_case.get('forbidden_user_evidence_ids', []):
            binding = bindings_by_external.get(forbidden_id)
            if not binding or binding.get('source_user_evidence_id') != source_id:
                errors.append(f'forbidden_source_binding_mismatch:{rewrite_id}')
    if exact_leaks:
        errors.append(f'exact_query_leaks:{"|".join(exact_leaks)}')
    if ngram_leaks:
        errors.append(f'eight_character_query_leaks:{"|".join(item["rewrite_id"] for item in ngram_leaks)}')
    return {
        'valid': not errors,
        'rewrite_count': len(rewrites),
        'exact_query_leaks': exact_leaks,
        'eight_character_query_leaks': ngram_leaks,
        'errors': errors,
    }
