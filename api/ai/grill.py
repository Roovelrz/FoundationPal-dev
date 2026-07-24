from __future__ import annotations

from typing import Any


PLANNING_QUESTIONS = (
    {
        'prompt': '本项目申报什么类别，并计划研究哪个方向？',
        'fields': ('funding_category', 'research_direction'),
    },
    {
        'prompt': '项目最需要解决的核心科学问题是什么？',
        'fields': ('core_problem',),
    },
    {
        'prompt': '已有研究基础中，哪些成果可以作为申报依据？',
        'fields': ('research_foundation',),
    },
    {
        'prompt': '项目可使用哪些设备，计划周期和预算范围是什么？',
        'fields': ('available_equipment', 'project_duration', 'budget_range'),
    },
    {
        'prompt': '预期成果是什么，并有哪些内容不得生成？',
        'fields': ('expected_outcomes', 'prohibited_content'),
    },
)

REVISION_QUESTIONS = (
    {'prompt': '这次只希望本章节达成什么修改目标？', 'fields': ('change_goal',)},
    {'prompt': '草稿中有哪些表述、事实或结构必须保留？', 'fields': ('preserve',)},
    {'prompt': '修改时必须遵守哪些证据、篇幅或表述限制？', 'fields': ('constraints',)},
)


def _questions(mode: str) -> tuple[dict[str, Any], ...]:
    return REVISION_QUESTIONS if mode == 'revision' else PLANNING_QUESTIONS


def _session_key(mode: str, section_key: str = '') -> str:
    return f'{mode}:{section_key}' if section_key else mode


def _root(proposal) -> dict[str, Any]:
    content = dict(proposal.content or {})
    content.setdefault('grill', {})
    proposal.content = content
    return content['grill']


def get_session(proposal, *, mode: str, section_key: str = '') -> dict[str, Any]:
    questions = _questions(mode)
    root = _root(proposal)
    key = _session_key(mode, section_key)
    session = root.get(key)
    if not isinstance(session, dict):
        session = {
            'mode': mode,
            'section_key': section_key,
            'question_index': 0,
            'question_count': 0,
            'max_questions': len(questions),
            'collected_answers': {},
            'skipped_fields': [],
            'missing_fields': list(field for question in questions for field in question['fields']),
            'completion_reason': '',
            'confirmed': False,
            'suggestion': '',
        }
        root[key] = session
    return session


def next_question(session: dict[str, Any]) -> dict[str, Any] | None:
    questions = _questions(session['mode'])
    index = min(int(session.get('question_index', 0)), len(questions))
    if session.get('completion_reason') or index >= len(questions):
        return None
    question = questions[index]
    return {'index': index + 1, 'prompt': question['prompt'], 'fields': question['fields']}


def answer(session: dict[str, Any], answers: dict[str, str], *, skip: bool = False) -> None:
    question = next_question(session)
    if question is None:
        return
    collected = dict(session.get('collected_answers') or {})
    skipped = list(session.get('skipped_fields') or [])
    for field in question['fields']:
        value = (answers.get(field) or '').strip()
        if value:
            collected[field] = value
        elif skip and field not in skipped:
            skipped.append(field)
    session['collected_answers'] = collected
    session['skipped_fields'] = skipped
    session['question_index'] = int(session.get('question_index', 0)) + 1
    session['question_count'] = min(int(session.get('question_count', 0)) + 1, int(session['max_questions']))
    _refresh_completion(session)


def finish(session: dict[str, Any], reason: str = 'user_finished') -> None:
    if not session.get('completion_reason'):
        session['completion_reason'] = reason
    _refresh_missing(session)
    if session['mode'] == 'revision':
        session['suggestion'] = revision_suggestion(session)


def confirm(session: dict[str, Any]) -> None:
    if not session.get('completion_reason'):
        finish(session)
    session['confirmed'] = True


def planning_context(proposal) -> str:
    session = _root(proposal).get('planning')
    if not isinstance(session, dict) or not session.get('confirmed'):
        return ''
    answers = session.get('collected_answers') or {}
    return '\n'.join(f'{field}: {value}' for field, value in answers.items() if value)


def revision_suggestion(session: dict[str, Any]) -> str:
    answers = session.get('collected_answers') or {}
    goal = answers.get('change_goal', '').strip()
    preserve = answers.get('preserve', '').strip()
    constraints = answers.get('constraints', '').strip()
    parts = [f'仅修改与以下目标直接相关的段落：{goal or "根据当前草稿提升表达清晰度"}。']
    if preserve:
        parts.append(f'必须保留：{preserve}。')
    if constraints:
        parts.append(f'修改限制：{constraints}。')
    parts.append('不得补造事实；保持本章节现有结构和可追溯证据。')
    return ''.join(parts)


def serialize(session: dict[str, Any], *, draft: str = '') -> dict[str, Any]:
    return {
        'mode': session['mode'],
        'section_key': session.get('section_key', ''),
        'question': next_question(session),
        'collected_answers': session.get('collected_answers') or {},
        'missing_fields': session.get('missing_fields') or [],
        'skipped_fields': session.get('skipped_fields') or [],
        'question_count': session.get('question_count', 0),
        'max_questions': session.get('max_questions', 0),
        'completion_reason': session.get('completion_reason', ''),
        'confirmed': bool(session.get('confirmed')),
        'suggestion': session.get('suggestion', ''),
        'draft': draft,
    }


def _refresh_completion(session: dict[str, Any]) -> None:
    _refresh_missing(session)
    if not session['missing_fields'] or int(session['question_count']) >= int(session['max_questions']):
        finish(session, 'all_questions_completed' if not session['missing_fields'] else 'max_questions_reached')


def _refresh_missing(session: dict[str, Any]) -> None:
    all_fields = [field for question in _questions(session['mode']) for field in question['fields']]
    answered = set((session.get('collected_answers') or {}).keys())
    skipped = set(session.get('skipped_fields') or [])
    session['missing_fields'] = [field for field in all_fields if field not in answered and field not in skipped]
