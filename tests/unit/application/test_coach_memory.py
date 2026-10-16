"""Coach memory: explicit remember/forget commands and prompt injection."""

from __future__ import annotations

from datetime import date

import pytest

from fitness.adapters.persistence.json_memory_store import JsonMemoryStore
from fitness.application.use_cases.handle_message import HandleMessageUseCase
from fitness.domain.coach_memory import CoachMemory


class FixedClock:
    def today(self) -> date:
        return date(2026, 8, 8)


@pytest.fixture
def store(tmp_path):
    return JsonMemoryStore(tmp_path)


@pytest.fixture
def uc(store):
    return HandleMessageUseCase(
        log_meal=None, query=None, memory_store=store, clock=FixedClock()
    )


def reply(uc, text):
    return uc._try_memory_command(text)


class TestStore:
    def test_round_trip(self, store):
        store.add(CoachMemory(text="left shoulder is bad", created=date(2026, 8, 8)))
        assert [m.text for m in store.list_all()] == ["left shoulder is bad"]

    def test_rejects_blank(self):
        with pytest.raises(ValueError):
            CoachMemory(text="   ", created=date(2026, 8, 8))

    def test_duplicates_ignored(self, store):
        assert store.add(CoachMemory(text="I train at home", created=date(2026, 8, 8))) is True
        assert store.add(CoachMemory(text="i train at HOME", created=date(2026, 8, 8))) is False
        assert len(store.list_all()) == 1

    def test_remove_matching(self, store):
        store.add(CoachMemory(text="left shoulder is bad", created=date(2026, 8, 8)))
        store.add(CoachMemory(text="I train at home", created=date(2026, 8, 8)))
        removed = store.remove_matching("shoulder")
        assert len(removed) == 1
        assert [m.text for m in store.list_all()] == ["I train at home"]

    def test_missing_file_is_empty(self, store):
        assert store.list_all() == []

    def test_corrupt_file_does_not_raise(self, tmp_path):
        (tmp_path / "coach_memory.json").write_text("{not json", encoding="utf-8")
        assert JsonMemoryStore(tmp_path).list_all() == []

    def test_caps_growth(self, store):
        for i in range(60):
            store.add(CoachMemory(text=f"fact {i}", created=date(2026, 8, 8)))
        remaining = store.list_all()
        assert len(remaining) == 50
        assert remaining[-1].text == "fact 59"      # newest kept


class TestCommands:
    @pytest.mark.parametrize("phrasing", [
        "remember that my left shoulder is bad",
        "Remember my left shoulder is bad",
        "please remember that my left shoulder is bad",
        "don't forget my left shoulder is bad",
        "keep in mind my left shoulder is bad",
        "note that my left shoulder is bad",
    ])
    def test_add_phrasings(self, uc, store, phrasing):
        assert reply(uc, phrasing) is not None
        assert any("shoulder is bad" in m.text for m in store.list_all())

    def test_add_strips_trailing_punctuation(self, uc, store):
        reply(uc, "remember that I train at home.")
        assert store.list_all()[0].text == "I train at home"

    def test_recall_lists_memories(self, uc, store):
        reply(uc, "remember that I train at home")
        out = reply(uc, "what do you remember?")
        assert "I train at home" in out

    def test_recall_when_empty(self, uc):
        assert "Nothing saved yet" in reply(uc, "what do you remember about me?")

    def test_forget_specific(self, uc, store):
        reply(uc, "remember that my left shoulder is bad")
        reply(uc, "remember that I train at home")
        out = reply(uc, "forget about my shoulder")
        assert "Forgotten" in out
        assert [m.text for m in store.list_all()] == ["I train at home"]

    def test_forget_unknown_term(self, uc):
        assert "don't have anything saved" in reply(uc, "forget about my knee")

    def test_forget_everything(self, uc, store):
        reply(uc, "remember that I train at home")
        assert "Cleared all 1" in reply(uc, "forget everything")
        assert store.list_all() == []

    def test_duplicate_add_is_reported(self, uc):
        reply(uc, "remember that I train at home")
        assert "Already had that one" in reply(uc, "remember that I train at home")

    @pytest.mark.parametrize("text", [
        "I had 3 eggs for breakfast",
        "bench press 3x10 at 185",
        "how many calories left?",
        "what should I eat",
        "remember",
    ])
    def test_ignores_non_memory_messages(self, uc, text):
        assert reply(uc, text) is None

    def test_no_store_configured_is_inert(self):
        bare = HandleMessageUseCase(log_meal=None, query=None)
        assert bare._try_memory_command("remember that I train at home") is None


class TestGroundingInjection:
    def test_memories_appear_in_grounding(self, uc, store):
        reply(uc, "remember that my left shoulder is bad")
        grounding = uc._build_grounding()
        assert "MEMORY" in grounding
        assert "left shoulder is bad" in grounding

    def test_grounding_omits_section_when_empty(self, uc):
        grounding = uc._build_grounding()
        assert grounding is None or "MEMORY" not in grounding


class TestForgetMatching:
    """'forget ...' has to tolerate natural phrasing without over-matching."""

    def _mem(self, text):
        return CoachMemory(text=text, created=date(2026, 8, 8))

    def test_partial_phrase_reaches_memory(self):
        assert self._mem("my left shoulder is bad").matches("my shoulder")

    def test_single_keyword(self):
        assert self._mem("my left shoulder is bad").matches("shoulder")

    def test_exact_substring(self):
        assert self._mem("I train at home").matches("train at home")

    def test_unrelated_term_does_not_match(self):
        assert not self._mem("my left shoulder is bad").matches("knee")

    def test_stopwords_alone_never_match(self):
        assert not self._mem("my left shoulder is bad").matches("the my about")

    def test_partial_word_does_not_match(self):
        assert not self._mem("I do warmups first").matches("arm")
