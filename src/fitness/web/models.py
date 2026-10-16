"""Pydantic models for the API request/response contract.

These translate between the HTTP JSON surface and the application DTOs. They're the only
place in the web layer that knows the wire format; the use-cases never touch them.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MessageRequest(BaseModel):
    text: str
    context: dict | None = None  # opaque to the client; echoed back to continue a turn


class MessageResponse(BaseModel):
    status: str  # "logged" | "needs_clarification"
    message: str
    context: dict | None = None
    meal_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class DailySummaryResponse(BaseModel):
    day: str
    total_calories: float
    total_macros: MacrosResponse
    calories_by_slot: dict[str, float]
    meal_count: int


class MacrosResponse(BaseModel):
    protein_g: float
    carbs_g: float
    fat_g: float


# Rebuild DailySummaryResponse so it picks up MacrosResponse which was defined after it.
DailySummaryResponse.model_rebuild()
