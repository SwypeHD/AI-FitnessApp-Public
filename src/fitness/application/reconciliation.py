"""Reconciliation — merge candidate meals from multiple sources into one.

Pure function, no IO. This is where "run the sources, deterministic wins" is enforced:
every field is merged via ``pick`` (provenance-ranked), foods are aligned across sources
by normalized name, and disagreements/unverified items are surfaced as notes rather than
silently resolved.

Sources are expected in the order they should be considered; ``prior`` (the merged state
from earlier conversational turns, including sticky USER values) is folded in first so it
forms the base. Because merging is provenance-ranked, the final result is independent of
source order for conflicting fields — order only affects same-provenance ties, where the
incumbent is kept for stability.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Sequence

from fitness.domain.candidate import CandidateFood, CandidateMeal
from fitness.domain.naming import normalize_food_name
from fitness.domain.value_objects import Provenance, pick

#: Relative difference in calories above which deterministic and LLM are considered to
#: disagree (and a note is emitted). 0.25 == 25%.
CALORIE_DIVERGENCE_TOLERANCE = 0.25

#: Provenances that count as "verified" — i.e. not a bare LLM guess.
_VERIFIED = {Provenance.USER, Provenance.DETERMINISTIC, Provenance.KNOWLEDGE_BASE}


@dataclass(frozen=True)
class ReconcileResult:
    candidate: CandidateMeal
    notes: list[str] = field(default_factory=list)


def reconcile(
    sources: Sequence[CandidateMeal],
    prior: CandidateMeal | None = None,
    *,
    tolerance: float = CALORIE_DIVERGENCE_TOLERANCE,
) -> ReconcileResult:
    ordered: list[CandidateMeal] = ([prior] if prior is not None else []) + list(sources)
    notes: list[str] = []

    # --- meal-level fields -------------------------------------------------
    meal_time = None
    raw_turns: list[str] = []
    for src in ordered:
        meal_time = pick(meal_time, src.meal_time)
        raw_turns.extend(src.raw_turns)

    # --- align foods by normalized name -----------------------------------
    buckets: "OrderedDict[str, list[CandidateFood]]" = OrderedDict()
    unnamed: list[CandidateFood] = []
    for src in ordered:
        for cf in src.foods:
            if cf.name is None:
                unnamed.append(cf)
                continue
            key = normalize_food_name(cf.name.value)
            buckets.setdefault(key, []).append(cf)

    merged_foods: list[CandidateFood] = []
    for contributions in buckets.values():
        merged = CandidateFood()
        for cf in contributions:
            for field_name in CandidateFood.FIELDS:
                merged.offer(field_name, getattr(cf, field_name))
        notes.extend(_food_notes(merged, contributions, tolerance))
        merged_foods.append(merged)
    merged_foods.extend(unnamed)

    candidate = CandidateMeal(
        meal_time=meal_time, foods=merged_foods, raw_turns=raw_turns
    )
    return ReconcileResult(candidate=candidate, notes=notes)


def _food_notes(
    merged: CandidateFood,
    contributions: list[CandidateFood],
    tolerance: float,
) -> list[str]:
    notes: list[str] = []
    label = merged.name.value if merged.name else "(unnamed food)"

    # Calorie divergence between a verified source and the LLM.
    cals_by_provenance: dict[Provenance, float] = {}
    for cf in contributions:
        if cf.calories is not None:
            cals_by_provenance.setdefault(cf.calories.provenance, cf.calories.value)
    verified_cals = cals_by_provenance.get(Provenance.DETERMINISTIC)
    if verified_cals is None:
        verified_cals = cals_by_provenance.get(Provenance.KNOWLEDGE_BASE)
    llm_cals = cals_by_provenance.get(Provenance.LLM)
    if (
        verified_cals is not None
        and llm_cals is not None
        and verified_cals > 0
        and abs(verified_cals - llm_cals) / verified_cals > tolerance
    ):
        notes.append(
            f"calorie estimates differ for '{label}': kept {verified_cals:g}, "
            f"LLM suggested {llm_cals:g}"
        )

    # Unverified food: every present field came from the LLM only.
    provenances = set().union(*(cf.provenances() for cf in contributions))
    if provenances and not (provenances & _VERIFIED):
        notes.append(f"unverified food (LLM only): {label}")

    return notes
