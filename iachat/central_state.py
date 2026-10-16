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


def state_to_dict(state: ConversationState) -> dict:
    """Create a JSON-compatible snapshot without exposing mutable references."""
    return {
        "version": 1,
        "active_topic": state.active_topic,
        "pending_question": state.pending_question,
        "facts": dict(state.facts),
    }


def state_from_dict(data: dict) -> ConversationState:
    """Load a snapshot, rejecting malformed or unsupported state."""
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("unsupported conversation state")
    topic = data.get("active_topic")
    pending = data.get("pending_question")
    facts = data.get("facts")
    if (topic is not None and (not isinstance(topic, str) or not topic.strip())):
        raise ValueError("invalid active_topic")
    if (pending is not None and (not isinstance(pending, str) or not pending.strip())):
        raise ValueError("invalid pending_question")
    if not isinstance(facts, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in facts.items()
    ):
        raise ValueError("invalid facts")
    return ConversationState(active_topic=topic, pending_question=pending, facts=dict(facts))


_EXPLICIT_TOPIC = re.compile(r"\b(?:obra|presupuesto)\s*(?:n[°ºo.]\s*)?(\d{3,8})\b", re.I)


def explicit_topic(text: str) -> str | None:
    """Recognize only a clearly named work/budget identifier.

    Do not infer topics from dates, bare numbers or ambiguous place names.
    """
    match = _EXPLICIT_TOPIC.search(text)
    return f"Obra {match.group(1)}" if match else None
