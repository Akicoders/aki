"""Regression test for task 3.3: reserved `session:*` facts must not leak
into `assemble_context`'s `get_facts_by_scope` fallback path."""

from agentos.memory.models import MemoryFact


class TestAssembleContextExcludesReservedFacts:
    def test_assemble_context_excludes_reserved_session_facts(self, memory_repo):
        project = "demo"
        scope = f"project:{project}"

        memory_repo.touch_last_session(project, "sess_aaaaaaaa")
        memory_repo.write_checkpoint(
            project=project,
            session_id="sess_aaaaaaaa",
            goal="goal",
            last_response="response",
            last_tool_result="tool result",
            iterations_exhausted=False,
        )
        memory_repo.upsert_fact(
            MemoryFact(key="favorite_language", value="Python", scope=scope, confidence=1.0)
        )

        # A query with no keyword match forces search_facts to return
        # nothing, triggering the get_facts_by_scope fallback path.
        context = memory_repo.assemble_context(query="zzz_no_match_zzz", project=project)

        keys = {fact.key for fact in context.facts}
        assert "session:last" not in keys
        assert "session:sess_aaaaaaaa:checkpoint" not in keys
        assert "favorite_language" in keys
