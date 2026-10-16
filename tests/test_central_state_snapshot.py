import json
import pytest
from iachat.central_state import ConversationState, state_to_dict, state_from_dict


def test_snapshot_json_round_trip():
    state = ConversationState(active_topic="Obra 1058", pending_question="¿Qué fecha?", facts={"permiso": "pendiente"})
    loaded = state_from_dict(json.loads(json.dumps(state_to_dict(state))))
    assert loaded == state
    loaded.facts["permiso"] = "aprobado"
    assert state.facts["permiso"] == "pendiente"


@pytest.mark.parametrize("invalid", [
    {}, {"version": 2, "facts": {}},
    {"version": 1, "active_topic": 123, "facts": {}},
    {"version": 1, "pending_question": "", "facts": {}},
    {"version": 1, "facts": {"key": 123}},
    {"version": 1, "facts": []},
])
def test_reject_invalid_snapshot(invalid):
    with pytest.raises(ValueError):
        state_from_dict(invalid)
