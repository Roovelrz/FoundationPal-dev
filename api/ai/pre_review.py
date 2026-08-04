import json


def _clean(value, limit):
    return str(value or '').strip()[:limit]


def _load_payload(raw):
    text = str(raw or '').strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    start = text.find('{')
    end = text.rfind('}')
    if start < 0 or end < start:
        return {}
    try:
        payload = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def normalize_pre_review(raw, draft):
    payload = _load_payload(raw)
    strengths = [
        _clean(item, 500)
        for item in payload.get('strengths', [])
        if _clean(item, 500)
    ][:3]
    if not strengths:
        strengths = ['本章节已形成完整草稿，具备继续核对论证逻辑和材料依据的基础。']

    issues = []
    for item in payload.get('issues', [])[:5]:
        if not isinstance(item, dict):
            continue
        problem = _clean(item.get('problem') or item.get('finding'), 500)
        reason = _clean(item.get('reason') or item.get('evidence'), 700)
        direction = _clean(item.get('direction') or item.get('suggestion'), 700)
        if problem and reason and direction:
            issues.append({'problem': problem, 'reason': reason, 'direction': direction})
    if not issues:
        draft_length = len(str(draft or '').strip())
        issues = [{
            'problem': '需要继续核对章节是否完整覆盖本章应回答的问题。',
            'reason': f'当前草稿约 {draft_length} 个字符，尚不能仅凭篇幅确认每一项问题均已得到充分论证。',
            'direction': '逐项对照本章问题，补足研究对象、论证依据、实施路径或预期结果中缺失的内容。',
        }]

    summary = _clean(payload.get('summary'), 1000)
    if not summary:
        summary = '预评审已完成。下列意见仅针对当前章节草稿，可用于决定是否继续修订。'
    revision_request = _clean(payload.get('revision_request'), 3000)
    if not revision_request:
        revision_request = '\n'.join(
            f'{item["problem"]} 原因：{item["reason"]} 修改方向：{item["direction"]}'
            for item in issues
        )
    return {
        'summary': summary,
        'strengths': strengths,
        'issues': issues,
        'revision_request': revision_request,
    }


def create_draft_pre_review(*, title, draft, provider, application_system):
    draft = str(draft or '').strip()
    if not draft:
        raise ValueError('draft_required')
    result = provider.pre_review(
        section_title=str(title or '当前草稿'),
        draft=draft,
        application_system=application_system,
    )
    return normalize_pre_review(result.text, draft)


def create_section_pre_review(*, section, provider, application_system):
    return create_draft_pre_review(
        title=section.title or section.key,
        draft=section.draft_content or section.approved_content,
        provider=provider,
        application_system=application_system,
    )
