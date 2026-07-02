"""Unit tests for `render_checkpoint` deterministic bounded formatter (task 3.1)."""

from agentos.memory.repository import CHECKPOINT_REHYDRATION_CHAR_CAP, render_checkpoint


def _checkpoint(**overrides) -> dict:
    base = {
        "v": 1,
        "session_id": "sess_aaaaaaaa",
        "project": "demo",
        "goal": "Implement checkpoint rehydration",
        "open_items": ["finish render_checkpoint", "wire _build_messages"],
        "last_tool_result": "ran pytest, 5 passed",
        "last_response": "Working on it.",
        "iterations_exhausted": False,
        "updated_at": "2024-01-01T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestRenderCheckpoint:
    def test_render_checkpoint_respects_char_cap(self):
        checkpoint = _checkpoint(
            goal="g" * 5000,
            open_items=["item " + str(i) * 50 for i in range(50)],
            last_tool_result="t" * 5000,
        )

        rendered_a = render_checkpoint(checkpoint, cap=CHECKPOINT_REHYDRATION_CHAR_CAP)
        rendered_b = render_checkpoint(checkpoint, cap=CHECKPOINT_REHYDRATION_CHAR_CAP)

        assert len(rendered_a) <= CHECKPOINT_REHYDRATION_CHAR_CAP
        assert rendered_a == rendered_b

    def test_render_checkpoint_handles_empty_open_items(self):
        checkpoint = _checkpoint(open_items=[])

        rendered = render_checkpoint(checkpoint, cap=CHECKPOINT_REHYDRATION_CHAR_CAP)

        assert rendered
        assert "Implement checkpoint rehydration" in rendered
