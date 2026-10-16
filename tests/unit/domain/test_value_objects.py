import pytest

from fitness.domain.value_objects import (
    FieldValue,
    Macros,
    Provenance,
    Quantity,
    Unit,
)


class TestMacros:
    def test_calories_uses_atwater_4_4_9(self):
        m = Macros(protein_g=10, carbs_g=20, fat_g=5)
        assert m.calories_from_macros == 10 * 4 + 20 * 4 + 5 * 9

    def test_rejects_negative(self):
        with pytest.raises(ValueError):
            Macros(protein_g=-1, carbs_g=0, fat_g=0)

    def test_addition(self):
        assert Macros(1, 2, 3) + Macros(4, 5, 6) == Macros(5, 7, 9)

    def test_scaled(self):
        assert Macros(2, 4, 6).scaled(0.5) == Macros(1, 2, 3)

    def test_scaled_rejects_negative_factor(self):
        with pytest.raises(ValueError):
            Macros(1, 1, 1).scaled(-1)

    def test_zero_is_additive_identity(self):
        m = Macros(3, 4, 5)
        assert m + Macros.zero() == m

    def test_is_immutable(self):
        m = Macros(1, 1, 1)
        with pytest.raises(AttributeError):
            m.protein_g = 99  # type: ignore[misc]


class TestQuantity:
    def test_valid(self):
        q = Quantity(3, Unit.SERVING)
        assert q.amount == 3 and q.unit is Unit.SERVING

    @pytest.mark.parametrize("amount", [0, -1, -0.5])
    def test_rejects_non_positive(self, amount):
        with pytest.raises(ValueError):
            Quantity(amount, Unit.GRAM)


class TestProvenancePrecedence:
    def test_ordering(self):
        ranks = [
            Provenance.USER,
            Provenance.DETERMINISTIC,
            Provenance.KNOWLEDGE_BASE,
            Provenance.LLM,
            Provenance.DEFAULT,
        ]
        values = [p.rank for p in ranks]
        assert values == sorted(values, reverse=True)
        assert len(set(values)) == len(values)  # all distinct


class TestFieldValue:
    def test_confidence_bounds(self):
        with pytest.raises(ValueError):
            FieldValue("x", Provenance.LLM, confidence=1.5)
        with pytest.raises(ValueError):
            FieldValue("x", Provenance.LLM, confidence=-0.1)

    def test_deterministic_outranks_llm(self):
        det = FieldValue(200.0, Provenance.DETERMINISTIC, 0.9)
        llm = FieldValue(180.0, Provenance.LLM, 1.0)
        assert det.outranks(llm)
        assert not llm.outranks(det)

    def test_user_outranks_everything(self):
        user = FieldValue("lunch", Provenance.USER, 0.5)
        det = FieldValue("dinner", Provenance.DETERMINISTIC, 1.0)
        assert user.outranks(det)

    def test_same_provenance_breaks_tie_on_confidence(self):
        low = FieldValue(1, Provenance.LLM, 0.4)
        high = FieldValue(2, Provenance.LLM, 0.8)
        assert high.outranks(low)
        assert not low.outranks(high)
