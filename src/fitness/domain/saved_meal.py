"""Saved meal domain — reusable meal templates that users can quick-log.

A SavedMeal is a named collection of SavedMealItems. Unlike the immutable Meal
aggregate used for daily logging, SavedMeal is mutable so users can edit their
templates over time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SavedMealItem:
    """One food line inside a saved meal template."""

    food_name: str
    quantity_g: float
    calories: float
    protein_g: float
    carbs_g: float
    fat_g: float

    def to_dict(self) -> dict:
        return {
            "food_name": self.food_name,
            "quantity_g": self.quantity_g,
            "calories": self.calories,
            "protein_g": self.protein_g,
            "carbs_g": self.carbs_g,
            "fat_g": self.fat_g,
        }

    @classmethod
    def from_dict(cls, d: dict) -> SavedMealItem:
        return cls(
            food_name=d["food_name"],
            quantity_g=d["quantity_g"],
            calories=d["calories"],
            protein_g=d["protein_g"],
            carbs_g=d["carbs_g"],
            fat_g=d["fat_g"],
        )


@dataclass(slots=True)
class SavedMeal:
    """A reusable meal template with a unique id and human-readable name."""

    id: str
    name: str
    items: list[SavedMealItem] = field(default_factory=list)

    @property
    def total_calories(self) -> float:
        return sum(item.calories for item in self.items)

    @property
    def total_protein_g(self) -> float:
        return sum(item.protein_g for item in self.items)

    @property
    def total_carbs_g(self) -> float:
        return sum(item.carbs_g for item in self.items)

    @property
    def total_fat_g(self) -> float:
        return sum(item.fat_g for item in self.items)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, d: dict) -> SavedMeal:
        return cls(
            id=d["id"],
            name=d["name"],
            items=[SavedMealItem.from_dict(i) for i in d.get("items", [])],
        )
