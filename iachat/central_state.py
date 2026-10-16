"""Small, deterministic conversation state for Central.

No global singleton: the caller owns persistence and scopes each state to its
conversation. This module does not call a language model.
"""
from dataclasses import dataclass, field
import re


@dataclass
class ConversationState:
    active_topic: str | None = None
    pending_question: str | None = None
    facts: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextResult:
    status: str  # "resolved", "clarify", "unrelated"
    topic: str | None = None
    question: str = ""


_REFERENCE = re.compile(r"\b(ahí|alli|allí|esa|ese|eso|esta|este|esto|la misma|el mismo)\b", re.I)


def resolve_topic(text: str, state: ConversationState) -> ContextResult:
    """Resolve only explicit deictic references; never guess a missing topic."""
    if not _REFERENCE.search(text):
        return ContextResult("unrelated")
    if state.active_topic:
        return ContextResult("resolved", topic=state.active_topic)
    return ContextResult("clarify", question="¿A qué tema te referís?")


def set_topic(state: ConversationState, topic: str) -> None:
    """The application sets a verified topic; free text is not auto-extracted."""
    topic = topic.strip()
    if not topic:
        raise ValueError("topic must not be empty")
    state.active_topic = topic
    state.pending_question = None


def ask_clarification(state: ConversationState, question: str) -> None:
    question = question.strip()
    if not question:
        raise ValueError("question must not be empty")
    state.pending_question = question


def clear_topic(state: ConversationState) -> None:
    state.active_topic = None
    state.pending_question = None
