from __future__ import annotations

from contextlib import contextmanager
from typing import Any, TypedDict

from django.conf import settings
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


HUMAN_NODES = {
    'plan_confirmation', 'innovation_confirmation', 'section_approval',
    'budget_confirmation', 'final_export_confirmation',
}
HUMAN_ACTIONS = {'approve', 'edit', 'reject'}
_memory_checkpointer = InMemorySaver()


class HumanState(TypedDict, total=False):
    thread_id: str
    human_node: str
    human_input: dict[str, Any]
    model_output: dict[str, Any]
    decision: dict[str, Any]
    status: str
    validation_error: str


def human_gate(state: HumanState) -> dict[str, Any]:
    decision = interrupt({
        'thread_id': state['thread_id'],
        'node': state['human_node'],
        'input': state.get('human_input') or {},
        'model_output': state.get('model_output') or {},
    })
    action = decision.get('action') if isinstance(decision, dict) else ''
    if action == 'approve':
        return {'decision': decision, 'status': 'approved'}
    if action == 'edit':
        return {'decision': decision, 'status': 'needs_revalidation'}
    return {'decision': decision, 'status': 'rejected'}


def validate_edit(state: HumanState) -> dict[str, Any]:
    edited = (state.get('decision') or {}).get('edited_input')
    if not isinstance(edited, dict) or not edited:
        return {'status': 'needs_revalidation', 'validation_error': 'edited_input_required'}
    return {'status': 'ready_after_edit', 'validation_error': ''}


def after_human(state: HumanState) -> str:
    return 'validate_edit' if state.get('status') == 'needs_revalidation' else END


def build_human_graph(checkpointer):
    graph = StateGraph(HumanState)
    graph.add_node('human_gate', human_gate)
    graph.add_node('validate_edit', validate_edit)
    graph.add_edge(START, 'human_gate')
    graph.add_conditional_edges('human_gate', after_human, {'validate_edit': 'validate_edit', END: END})
    graph.add_edge('validate_edit', END)
    return graph.compile(checkpointer=checkpointer)


@contextmanager
def checkpointer():
    dsn = getattr(settings, 'LANGGRAPH_CHECKPOINT_DSN', '')
    if not dsn:
        yield _memory_checkpointer
        return
    from langgraph.checkpoint.postgres import PostgresSaver

    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
        yield saver


def start_human_task(state: HumanState) -> None:
    with checkpointer() as saver:
        graph = build_human_graph(saver)
        graph.invoke(state, {'configurable': {'thread_id': state['thread_id']}})


def resume_human_task(thread_id: str, decision: dict[str, Any]) -> HumanState:
    with checkpointer() as saver:
        graph = build_human_graph(saver)
        return graph.invoke(Command(resume=decision), {'configurable': {'thread_id': thread_id}})
