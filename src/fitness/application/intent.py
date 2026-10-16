"""Deterministic intent router.

Classifies an inbound message into LOG / QUERY / EDIT / CHAT using keyword heuristics.
Only the genuinely ambiguous middle (no heuristic fires) falls back to the LLM's
``classify_intent`` — so the system works even when the LLM is down or absent.

The patterns are intentionally simple and over-inclusive for QUERY/EDIT (it's cheaper to
misroute a log as a query and have the query say "I didn't find anything" than to treat
"show me my log" as a food).
"""

from __future__ import annotations

import re

from fitness.application.ports.extraction import Intent

# QUERY patterns: the user is asking about their data, not logging.
_QUERY_PATTERNS = [
    re.compile(r"\b(?:show|list|view|display|see|get)\b.*\b(?:log|meals?|food|summary|totals?|eaten)\b", re.I),
    re.compile(r"\b(?:how (?:much|many))\b.*\b(?:today|so far|have i|did i|i've|eaten|logged)\b", re.I),
    re.compile(r"\b(?:total|so far)\b.*\b(?:calories?|protein|carbs?|fat|macros?)\b", re.I),
    re.compile(r"\b(?:summary|overview|daily|today'?s?)\b.*\b(?:log|meals?|food|calories?|protein|macros?)\b", re.I),
    re.compile(r"\b(?:calories?|protein|carbs?|fat)\b.*\b(?:today|so far|this (?:morning|afternoon|evening))\b", re.I),
    re.compile(r"\bwhat(?:'s| is| did| have)\b.*\b(?:eat|ate|have|had|log|today)\b", re.I),
]

# PLAN BUILDER patterns: creating/modifying workout plans via chat.
_PLAN_BUILDER_PATTERNS = [
    re.compile(r"\b(?:create|make|build|generate|design)\b.*\b(?:plan|split|routine|program|schedule)\b", re.I),
    re.compile(r"\b(?:add|remove|delete)\b.*\b(?:day|rest)\b.*\b(?:plan|routine|split|program)\b", re.I),
    re.compile(r"\b(?:add|remove|delete)\b.*\b(?:day|rest)\b\s+(?:after|before|to)\b", re.I),
    re.compile(r"\brename\b.*\b(?:day\b|to\b).*\b(?:plan|routine|split|program)\b", re.I),
    re.compile(r"\brename\b\s+\w+\s+(?:day\s+)?to\s+", re.I),
]

# EDIT patterns: the user wants to change an existing log entry.
_EDIT_PATTERNS = [
    re.compile(r"\b(?:move|change|switch|update|edit|modify)\b.*\b(?:to |from )?\b(?:breakfast|lunch|dinner|snack)\b", re.I),
    re.compile(r"\b(?:delete|remove|undo|cancel)\b", re.I),
    re.compile(r"\b(?:change|update|set|make)\b\s+(?:the\s+|my\s+)?\w+.*\bto\s+\d+", re.I),
    re.compile(r"\b(?:convert|show|display)\b\s+(?:the\s+|my\s+)?\w+.*\b(?:to|in|as)\s+(?:g|grams?|oz|ounces?|servings?|cups?|pieces?|ml)\b", re.I),
    re.compile(r"\brename\b", re.I),
    re.compile(r"\b(?:actually|only)\b.*\d+\s*(?:g|grams?|oz|ounces?|servings?|cups?|pieces?|ml)\b", re.I),
    re.compile(r"\b(?:add|remove)\b\s+(?:a\s+)?(?:last\s+)?set\b", re.I),
    re.compile(r"\b(?:save|delete|remove)\b.*\bsaved\s+meal\b", re.I),
    re.compile(r"\bsave\b.*\bas\b", re.I),
    re.compile(r"\b(?:create|make)\b.*\bsaved\s+meal\b", re.I),
    re.compile(r"\b(?:create|make)\b.*\bmeal\s+(?:called|named)\b", re.I),
    re.compile(r"\b(?:set|change)\b.*\b(?:calorie|protein|carb|fat)\s*(?:targets?|goals?)\b", re.I),
    re.compile(r"\b(?:targets?|goals?)\b.*\b\d+\s*(?:kcal|cal|calories?|g)\b", re.I),
    re.compile(r"\bswitch\b.*\b(?:metric|imperial|pounds?|lbs|kg|kilos?)\b", re.I),
    re.compile(r"\buse\s+(?:metric|imperial|kg|lbs|pounds?|kilos?)\b", re.I),
    re.compile(r"\b(?:actually|used)\b.*\b\d+\b.*\b(?:bench|squat|deadlift|curl|press|row)\b", re.I),
    re.compile(r"\balign\b.*\b(?:to|rotation)\b", re.I),
]

# CALENDAR patterns: workout calendar management actions.
_CALENDAR_PATTERNS = [
    re.compile(r"\b(?:skip|push\s*back)\b.*\b(?:today|workout|day)\b", re.I),
    re.compile(r"\b(?:skip|catch\s*up|push\s*back|shift)\b.*\bto\s*today\b", re.I),
    re.compile(r"\b(?:mark|done|complete|finished)\b.*\b(?:today|workout|day)\b", re.I),
    re.compile(r"\b(?:i'?m|i\s+am)\b\s+(?:done|finished)\b.*\b(?:today|workout)?\b", re.I),
    re.compile(r"\b(?:activate|start|switch\s+to|use)\b.*\b(?:plan|ppl|push\s*pull|upper\s*lower|bro\s*split|full\s*body)\b", re.I),
    re.compile(r"\b(?:activate|start)\b\s+(?:the\s+|my\s+)?\w+.{0,40}$", re.I),
    re.compile(r"\bundo\b.*\b(?:skip|push\s*back|calendar|workout)\b", re.I),
]

# EXERCISE signals: exercise verbs/nouns that distinguish from food logging.
_EXERCISE_PATTERNS = [
    re.compile(r"\b(?:sets?\s+(?:of\s+)?\d+|\d+\s*x\s*\d+)\b", re.I),
    re.compile(r"\b(?:ran|run|running|jog|jogged|jogging|cycling|biked?|biking|swam|swim|swimming|walked|walk|walking|hiking|hiked)\b", re.I),
    re.compile(r"\b(?:bench\s*press|squats?|deadlifts?|curls?|pullups?|pull[\s-]*ups?|pushups?|push[\s-]*ups?|lunges?|planks?|dips?|rows?|shrugs?|press(?:es)?|extensions?|flyes?|hip\s*thrusts?|calf\s*raises?|lateral\s*raises?|face\s*pulls?|lat\s*pulldowns?|leg\s*press(?:es)?|rdls?)\b", re.I),
    re.compile(r"\b(?:yoga|stretch(?:ing|ed)?|hiit|cardio|elliptical|stairmaster|foam\s*roll(?:ing)?)\b", re.I),
    re.compile(r"\b\d+\s*(?:min(?:ute)?s?|hr|hours?)\b.*\b(?:run|walk|bike|swim|yoga|stretch|cardio|workout)\b", re.I),
    re.compile(r"\b(?:hit|worked|trained|lifting|lifted)\b.*\b(?:chest|back|legs?|arms?|shoulders?|gym|weights?)\b", re.I),
]

# LOG signals: quantity + food-ish tokens, or explicit logging verbs.
_LOG_PATTERNS = [
    re.compile(r"\b(?:ate|had|eating|having)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*(?:g|oz|grams?|ounces?|servings?|cups?|pieces?|ml)\b", re.I),
    # Small number (1-20) at the start, followed by a word — likely "2 eggs", "3 chicken".
    re.compile(r"^(?:\d|1\d|20)\s+[a-zA-Z]", re.I),
]


def classify_intent(text: str) -> Intent | None:
    """Return the classified intent, or None if heuristics are inconclusive (needs LLM)."""
    text = text.strip()

    # Target/goal statements with numbers are EDIT, not QUERY — catch before QUERY
    # eats "daily calories" or "daily protein".
    if re.search(r"\b(?:targets?|goals?)\b", text, re.I) and re.search(r"\d", text):
        return Intent.EDIT

    # "I should be eating 2200 calories" / "my calories should be 2200" — target, not food
    if re.search(r"\b(?:should|want\s+to|like\s+to)\b", text, re.I) and re.search(
        r"\d+\s*(?:kcal|cal|calories?|protein|carbs?|fat)\b", text, re.I
    ):
        return Intent.EDIT
    # "my calories should be 2200" / "daily calories 2200"
    if re.search(r"\b(?:calories?|protein|carbs?|fat)\b.*\bshould\b.*\d", text, re.I):
        return Intent.EDIT

    # QUERY and EDIT are checked first because they're more specific. A message like
    # "show me what I had for lunch" contains the word "had" (a LOG signal), but the
    # overall structure is clearly a query.
    for pattern in _QUERY_PATTERNS:
        if pattern.search(text):
            return Intent.QUERY

    for pattern in _PLAN_BUILDER_PATTERNS:
        if pattern.search(text):
            return Intent.EDIT

    # Calendar patterns describe commands ("mark today done"). A message opening with
    # an interrogative is asking about the log instead — "what exercises have I done
    # today?" otherwise trips the mark-done pattern on the words "done ... today".
    asks_for_information = bool(
        re.match(r"^\s*(?:what|which|how|when|why|who)\b", text, re.I)
    )

    for pattern in _CALENDAR_PATTERNS:
        if asks_for_information:
            break
        if pattern.search(text):
            return Intent.CALENDAR

    for pattern in _EDIT_PATTERNS:
        if pattern.search(text):
            return Intent.EDIT

    # When both food verbs ("had/ate/eating") and exercise keywords are present,
    # check for strong exercise signals (sets/reps/weights). If present, prefer EXERCISE.
    # Otherwise the food verb wins — "had a protein bar after my run" is food, not exercise.
    has_food_verb = re.search(r"\b(?:ate|had|eating|having|drank|drinking)\b", text, re.I)
    has_exercise = any(p.search(text) for p in _EXERCISE_PATTERNS)
    has_strong_exercise = bool(re.search(
        r"\b(?:sets?\s+(?:of\s+)?\d+|\d+\s*x\s*\d+|\d+\s*reps?)\b", text, re.I,
    ))

    # A question about an exercise isn't a log. "Should I do overhead press today?"
    # mentions a lift, but answering it is the point — only actual set/rep/weight
    # data should pull a message into EXERCISE logging.
    is_question = bool(
        text.rstrip().endswith("?")
        or re.match(
            r"^\s*(?:should|can|could|would|do|does|did|is|are|what|which|how|why|when|who)\b",
            text,
            re.I,
        )
    )
    if is_question and not has_strong_exercise:
        has_exercise = False

    if has_food_verb and has_exercise:
        if has_strong_exercise:
            return Intent.EXERCISE
        return Intent.LOG
    if has_exercise:
        return Intent.EXERCISE

    for pattern in _LOG_PATTERNS:
        if pattern.search(text):
            return Intent.LOG

    # No heuristic fired and no LOG signal → if there's no number and no food-related
    # keyword, this is almost certainly chat, not a food log. Only return None (ambiguous)
    # when there's genuinely mixed evidence.
    if not re.search(r"\d", text):
        return Intent.CHAT

    return None  # ambiguous — caller should fall back to LLM or default
