"""Mini test/sample flow για το backend/app/retrieval/llm.py.

Καλύπτει το payload που φεύγει προς το Ollama `/api/chat`, με mock στο
`requests.post` — καμία πραγματική HTTP κλήση, κανένα ζωντανό Ollama.

Γιατί υπάρχει:
  - `num_ctx` ΠΡΕΠΕΙ να είναι μέσα στο `options`. Χωρίς αυτό το Ollama
    χρησιμοποιεί το default του μοντέλου (131072 για Krikri) και το KV cache
    δεν χωράει σε μηχάνημα 16 GB.
  - `keep_alive` ΠΡΕΠΕΙ να είναι top-level πεδίο του json. Αν μπει μέσα στο
    `options`, το Ollama το αγνοεί ΣΙΩΠΗΛΑ: καμία εξαίρεση, καμία διαφορά στην
    απάντηση, απλώς το μοντέλο ξεφορτώνεται μετά από 5 λεπτά. Το negative test
    παρακάτω είναι ο μόνος τρόπος να πιαστεί αυτό.
  - Τα υπόλοιπα πεδία (model/messages/stream/temperature/seed) ελέγχονται
    ρητά ώστε το test να πέφτει και σε ΑΦΑΙΡΕΣΗ, όχι μόνο σε λάθος τοποθέτηση.

Εκτελείται standalone: `python tests/test_llm.py`
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.retrieval import llm as llm_module  # noqa: E402
from app.retrieval.llm import OllamaClient  # noqa: E402


class FakeResponse:
    """Ελάχιστο stand-in για requests.Response."""

    def __init__(self, content: str = "απάντηση"):
        self._content = content
        self.raise_for_status_calls = 0

    def raise_for_status(self):
        self.raise_for_status_calls += 1

    def json(self):
        return {"message": {"content": self._content}}


class PostRecorder:
    """Αντικαθιστά το requests.post και κρατάει ό,τι του δόθηκε."""

    def __init__(self):
        self.calls = []

    def __call__(self, url, json=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    @property
    def payload(self):
        assert len(self.calls) == 1, f"αναμενόταν 1 POST, έγιναν {len(self.calls)}"
        return self.calls[0]["json"]


def _capture(client: OllamaClient) -> PostRecorder:
    """Τρέχει μία generate() με mocked requests.post και επιστρέφει τον recorder."""
    recorder = PostRecorder()
    original_post = llm_module.requests.post
    llm_module.requests.post = recorder
    try:
        client.generate(system="system prompt", user="user prompt")
    finally:
        llm_module.requests.post = original_post
    return recorder


def test_payload_carries_num_ctx_inside_options():
    settings = get_settings()
    recorder = _capture(OllamaClient())
    options = recorder.payload["options"]

    assert "num_ctx" in options, "το num_ctx λείπει από το options"
    assert options["num_ctx"] == settings.OLLAMA_NUM_CTX


def test_payload_carries_keep_alive_at_top_level():
    settings = get_settings()
    recorder = _capture(OllamaClient())
    payload = recorder.payload

    assert "keep_alive" in payload, "το keep_alive λείπει από το top level του json"
    assert payload["keep_alive"] == settings.OLLAMA_KEEP_ALIVE


def test_keep_alive_is_not_buried_inside_options():
    """NEGATIVE: μέσα στο options το Ollama αγνοεί σιωπηλά το keep_alive."""
    recorder = _capture(OllamaClient())
    options = recorder.payload["options"]

    assert "keep_alive" not in options, (
        "το keep_alive βρέθηκε μέσα στο options — το Ollama το αγνοεί σιωπηλά "
        "και το μοντέλο θα ξεφορτώνεται μετά από 5 λεπτά"
    )


def test_payload_preserves_the_fields_it_already_sent():
    """REGRESSION: κανένα προϋπάρχον πεδίο δεν χάνεται με την προσθήκη των νέων."""
    settings = get_settings()
    recorder = _capture(OllamaClient())
    payload = recorder.payload

    assert payload["model"] == settings.OLLAMA_MODEL
    assert payload["messages"] == [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "user prompt"},
    ]
    assert payload["stream"] is False

    options = payload["options"]
    assert "temperature" in options, "το temperature λείπει από το options"
    assert options["temperature"] == settings.OLLAMA_TEMPERATURE
    assert "seed" in options, "το seed λείπει από το options"
    assert options["seed"] == settings.OLLAMA_SEED


def test_payload_has_no_unexpected_top_level_keys():
    """Το σχήμα του json είναι ακριβώς αυτό που περιμένει το Ollama chat API."""
    recorder = _capture(OllamaClient())
    assert set(recorder.payload) == {
        "model",
        "messages",
        "stream",
        "keep_alive",
        "options",
    }
    assert set(recorder.payload["options"]) == {"temperature", "seed", "num_ctx"}


def test_constructor_overrides_win_over_settings():
    """Ίδιο pattern με temperature/seed: explicit arg > setting."""
    client = OllamaClient(num_ctx=2048, keep_alive="5s")
    assert client.num_ctx == 2048
    assert client.keep_alive == "5s"

    payload = _capture(client).payload
    assert payload["options"]["num_ctx"] == 2048
    assert payload["keep_alive"] == "5s"


def test_defaults_come_from_settings_when_args_omitted():
    settings = get_settings()
    client = OllamaClient()
    assert client.num_ctx == settings.OLLAMA_NUM_CTX
    assert client.keep_alive == settings.OLLAMA_KEEP_ALIVE


def test_url_and_timeout_are_unchanged():
    settings = get_settings()
    recorder = _capture(OllamaClient())
    call = recorder.calls[0]
    assert call["url"] == f"{settings.OLLAMA_URL}/api/chat"
    assert call["timeout"] == settings.OLLAMA_TIMEOUT_S


def run_all():
    tests = [
        test_payload_carries_num_ctx_inside_options,
        test_payload_carries_keep_alive_at_top_level,
        test_keep_alive_is_not_buried_inside_options,
        test_payload_preserves_the_fields_it_already_sent,
        test_payload_has_no_unexpected_top_level_keys,
        test_constructor_overrides_win_over_settings,
        test_defaults_come_from_settings_when_args_omitted,
        test_url_and_timeout_are_unchanged,
    ]
    for test in tests:
        test()
        print(f"OK  {test.__name__}")
    print(f"\n{len(tests)} tests passed.")


if __name__ == "__main__":
    run_all()
