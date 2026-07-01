from agentos.memory import repository as memory_repository


class FakeSentenceTransformer:
    def __init__(self, model_name: str):
        self.model_name = model_name


def test_sentence_transformer_embedder_reuses_cached_model(monkeypatch):
    created_models: list[str] = []

    def fake_create_sentence_transformer(model_name: str) -> FakeSentenceTransformer:
        created_models.append(model_name)
        return FakeSentenceTransformer(model_name)

    monkeypatch.setattr(
        memory_repository,
        "_create_sentence_transformer",
        fake_create_sentence_transformer,
    )

    first = memory_repository.SentenceTransformerEmbedder("mini-model")
    second = memory_repository.SentenceTransformerEmbedder("mini-model")

    assert first.model is second.model
    assert created_models == ["mini-model"]
