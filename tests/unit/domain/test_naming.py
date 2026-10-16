import pytest

from fitness.domain.naming import normalize_food_name


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("  Chicken  Breasts ", "chicken breast"),
        ("Rice", "rice"),
        ("eggs", "egg"),
        ("grass", "grass"),  # trailing 'ss' is preserved
        ("OATS", "oat"),
        ("bus", "bus"),  # too short to strip (<= 3 chars)
        # The heuristic over-strips real singulars ending in 's' ("hummus" -> "hummu").
        # That's acceptable: normalization exists to ALIGN sources, not to be correct
        # English. What matters is that it's consistent (asserted below).
        ("hummus", "hummu"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_food_name(raw) == expected


def test_normalization_is_idempotent_and_consistent():
    # Aligning sources only works if normalization is stable: normalizing an
    # already-normalized name is a no-op, and different casings/plurals of the same
    # food collapse to one key.
    for raw in ["Chicken Breasts", "chicken breast", "CHICKEN BREASTS"]:
        once = normalize_food_name(raw)
        assert normalize_food_name(once) == once  # idempotent
    keys = {normalize_food_name(r) for r in ["Eggs", "egg", "EGG"]}
    assert len(keys) == 1
