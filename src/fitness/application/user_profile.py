"""User profile — personal stats and daily targets.

Stored as a simple JSON file (not a domain entity — it's user configuration, not a
logged event). Injected into the dashboard for progress bars and into chat grounding
so the LLM can give personalized advice.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


_PROFILE_FIELDS = {
    "name": "your name",
    "age": "your age",
    "gender": "your gender",
    "height_cm": "your height",
    "weight_kg": "your weight",
    "fitness_goal": "your fitness goal (e.g. lose fat, build muscle, maintain)",
    "activity_level": "your activity level (sedentary, lightly active, active, very active)",
    "experience_level": "your training experience (beginner, intermediate, advanced)",
}


@dataclass
class UserProfile:
    name: str = ""
    age: int = 0
    gender: str = ""
    height_cm: float = 0
    weight_kg: float = 0
    height_ft: int = 0
    height_in: int = 0
    weight_lbs: float = 0
    unit_system: str = "metric"
    fitness_goal: str = ""
    activity_level: str = ""
    experience_level: str = ""
    injuries: str = ""
    calorie_target: int = 2000
    protein_target_g: int = 150
    carbs_target_g: int = 250
    fat_target_g: int = 70

    def sync_units(self) -> None:
        """Derive the non-primary unit system from the primary one. Never overwrites
        the values the user actually entered — only fills in the other side."""
        if self.unit_system == "imperial":
            if self.height_ft or self.height_in:
                self.height_cm = round(self.height_ft * 30.48 + self.height_in * 2.54, 1)
            if self.weight_lbs:
                self.weight_kg = round(self.weight_lbs / 2.205, 1)
        else:
            if self.height_cm:
                total_inches = self.height_cm / 2.54
                self.height_ft = int(total_inches // 12)
                self.height_in = int(round(total_inches % 12))
            if self.weight_kg:
                self.weight_lbs = round(self.weight_kg * 2.205, 1)

    def missing_fields(self) -> list[str]:
        """Return human-readable descriptions of important unfilled fields."""
        missing = []
        for field, desc in _PROFILE_FIELDS.items():
            val = getattr(self, field)
            if not val or val == 0:
                missing.append(desc)
        return missing

    def grounding_text(self) -> str:
        parts = []
        if self.name:
            parts.append(f"User's name: {self.name}.")
        if self.age > 0:
            parts.append(f"Age: {self.age}.")
        if self.gender:
            parts.append(f"Gender: {self.gender}.")
        if self.height_cm > 0:
            if self.unit_system == "imperial" and self.height_ft:
                parts.append(f"Height: {self.height_ft}'{self.height_in}\" ({self.height_cm}cm).")
            else:
                parts.append(f"Height: {self.height_cm}cm.")
        if self.weight_kg > 0:
            if self.unit_system == "imperial" and self.weight_lbs:
                parts.append(f"Bodyweight: {self.weight_lbs}lbs ({self.weight_kg}kg).")
            else:
                parts.append(f"Bodyweight: {self.weight_kg}kg.")
        if self.fitness_goal:
            parts.append(f"Fitness goal: {self.fitness_goal}.")
        if self.activity_level:
            parts.append(f"Activity level: {self.activity_level}.")
        if self.experience_level:
            parts.append(f"Experience: {self.experience_level}.")
        if self.injuries:
            parts.append(f"Injuries/limitations: {self.injuries}.")
        parts.append(
            f"Daily targets: {self.calorie_target} kcal, "
            f"{self.protein_target_g}g protein, "
            f"{self.carbs_target_g}g carbs, "
            f"{self.fat_target_g}g fat."
        )

        missing = self.missing_fields()
        if missing:
            parts.append(f"MISSING PROFILE INFO: {', '.join(missing)}.")

        return " ".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "UserProfile":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ProfileStore(Protocol):
    def load(self) -> UserProfile: ...
    def save(self, profile: UserProfile) -> None: ...
