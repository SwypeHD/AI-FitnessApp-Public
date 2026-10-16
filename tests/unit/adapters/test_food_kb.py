from fitness.adapters.extraction.food_kb import StaticFoodKnowledgeBase


def kb():
    return StaticFoodKnowledgeBase()


def test_exact_match():
    assert kb().lookup("chicken breast").name == "chicken breast"


def test_alias_resolves_to_canonical():
    assert kb().lookup("rice").name == "white rice"
    assert kb().lookup("yogurt").name == "greek yogurt"


def test_case_and_plural_insensitive():
    assert kb().lookup("EGGS").name == "egg"


def test_longest_phrase_wins():
    # "chicken" and "chicken breast" are both aliases; the longer phrase should win.
    assert kb().lookup("grilled chicken breast").name == "chicken breast"


def test_token_matching_avoids_false_substring():
    # "egg" must not match inside "eggplant".
    assert kb().lookup("eggplant parmesan") is None


def test_unknown_food_returns_none():
    assert kb().lookup("kangaroo steak") is None
