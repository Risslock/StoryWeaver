"""Guided Earthdawn 4E character creation flow."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_DATA = Path(__file__).parent / "data"


def load_disciplines() -> list[dict[str, Any]]:
    with (_DATA / "disciplines.json").open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def load_races() -> list[dict[str, Any]]:
    with (_DATA / "races.json").open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def load_circle_tables() -> dict[str, Any]:
    with (_DATA / "circle_tables.json").open() as f:
        return json.load(f)  # type: ignore[no-any-return]


def race_names() -> list[str]:
    return [r["name"] for r in load_races()]


def discipline_names() -> list[str]:
    return [d["name"] for d in load_disciplines()]


def tier_for_circle(circle: int) -> str:
    tables = load_circle_tables()
    entry = tables["circle_breakpoints"].get(str(circle))
    return entry["tier"] if entry else "Unknown"


@dataclass
class CreationState:
    """Mutable state accumulated during multi-step character creation."""

    name: str = ""
    race: str = ""
    discipline: str = ""
    circle: int = 1
    attributes: dict[str, int] = field(default_factory=lambda: {
        "dex": 10, "str": 10, "tou": 10, "per": 10, "wil": 10, "cha": 10
    })
    derived_stats: dict[str, Any] = field(default_factory=dict)
    talents: list[dict[str, Any]] = field(default_factory=list)
    skills: list[dict[str, Any]] = field(default_factory=list)
    equipment: list[dict[str, Any]] = field(default_factory=list)
    background: str = ""
    personality: str = ""
    goals: str = ""
    relationships: list[dict[str, Any]] = field(default_factory=list)
    physical_description: str = ""


# Ordered steps in the guided creation flow.
# physical_description is included at creation so the twin has grounding material
# from the start; it can be updated at any time during play.
CREATION_STEPS = [
    "race",
    "discipline",
    "attributes",
    "talents",
    "skills",
    "background",
    "physical_description",
]


def apply_step(state: CreationState, step: str, value: Any) -> CreationState:
    """Apply a single creation step value to the state. Returns the (mutated) state."""
    if step == "race":
        state.race = str(value)
    elif step == "discipline":
        state.discipline = str(value)
    elif step == "attributes":
        if isinstance(value, dict):
            state.attributes.update({k: int(v) for k, v in value.items()})
        _compute_derived(state)
    elif step == "talents":
        if isinstance(value, list):
            state.talents = [dict(t) for t in value]
    elif step == "skills":
        if isinstance(value, list):
            state.skills = [dict(s) for s in value]
    elif step == "background":
        state.background = str(value)
    elif step == "physical_description":
        # Records how the character looks at creation; can be updated during play
        # to reflect growth, scars, or deliberate changes in appearance.
        state.physical_description = str(value)
    return state


def _compute_derived(state: CreationState) -> None:
    """Populate derived_stats from attribute step values (simplified 4E formulas)."""
    attrs = state.attributes
    state.derived_stats = {
        "initiative": attrs.get("dex", 10),
        "physical_defense": attrs.get("dex", 10),
        "spell_defense": attrs.get("per", 10),
        "social_defense": attrs.get("cha", 10),
        "physical_armor": 0,
        "mystic_armor": 0,
        "death_rating": attrs.get("tou", 10) + 20,
        "wound_threshold": (attrs.get("tou", 10) // 2) + 2,
        "unconscious_rating": attrs.get("tou", 10) + 10,
        "recovery_tests": attrs.get("tou", 10) // 6 + 1,
        "karma_modifier": _karma_modifier(state.circle),
    }


def _karma_modifier(circle: int) -> int:
    tables = load_circle_tables()
    entry = tables["circle_breakpoints"].get(str(circle))
    return entry["karma_modifier"] if entry else 4


def default_creation_state() -> CreationState:
    return CreationState()