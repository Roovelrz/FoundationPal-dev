from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from .intake import answer_node, next_node, question_card
from .models import GrillSession


class IntakeGrillState(TypedDict, total=False):
    session_id: int
    thread_id: str
    completion_reason: str
    question_count: int
    proposal_decision_ids: list[int]


def grill_turn(state: IntakeGrillState) -> dict[str, Any]:
    session = GrillSession.objects.get(pk=state['session_id'])
    node = next_node(session)
    if node is None:
        return {'completion_reason': session.completion_reason, 'question_count': session.question_count}
    response = interrupt(question_card(node))
    answer_node(
        session,
        node_id=node.node_id,
        action=(response or {}).get('action', ''),
        answer=(response or {}).get('answer', ''),
        idempotency_key=(response or {}).get('idempotency_key', f'{state["thread_id"]}:{node.node_id}'),
    )
    session.refresh_from_db()
    return {
        'completion_reason': session.completion_reason,
        'question_count': session.question_count,
        'proposal_decision_ids': list(session.decisions.values_list('id', flat=True)),
    }


def after_grill_turn(state: IntakeGrillState) -> str:
    session = GrillSession.objects.get(pk=state['session_id'])
    return 'grill_turn' if next_node(session) is not None and session.status == 'active' else END


def build_intake_grill_graph(checkpointer):
    graph = StateGraph(IntakeGrillState)
    graph.add_node('grill_turn', grill_turn)
    graph.add_edge(START, 'grill_turn')
    graph.add_conditional_edges('grill_turn', after_grill_turn, {'grill_turn': 'grill_turn', END: END})
    return graph.compile(checkpointer=checkpointer)
