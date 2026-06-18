"""Sanity-check validation for Earthdawn 4E character data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.errors import ValidationError


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str]

    def raise_if_invalid(self) -> None:
        if not self.valid:
            raise ValidationError("; ".join(self.errors))


_REQUIRED_FIELDS = ("name", "race", "discipline", "background", "personality")
_VALID_ATTRIBUTE_KEYS = ("dex", "str", "tou", "per", "wil", "cha")


def validate_character(data: dict[str, Any]) -> ValidationResult:
    """Run all sanity checks. Returns a ValidationResult (never raises)."""
    errors: list[str] = []

    for field in _REQUIRED_FIELDS:
        value = data.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            errors.append(f"'{field}' is required and cannot be empty")

    circle = data.get("circle", 1)
    try:
        circle_int = int(circle)
        if not (1 <= circle_int <= 15):
            errors.append(f"'circle' must be between 1 and 15, got {circle_int}")
    except (TypeError, ValueError):
        errors.append(f"'circle' must be an integer, got {circle!r}")

    attributes = data.get("attributes", {})
    if isinstance(attributes, dict):
        for key, val in attributes.items():
            if key not in _VALID_ATTRIBUTE_KEYS:
                errors.append(f"Unknown attribute '{key}'")
                continue
            try:
                if int(val) <= 0:
                    errors.append(f"Attribute '{key}' must be a positive integer, got {val}")
            except (TypeError, ValueError):
                errors.append(f"Attribute '{key}' must be an integer, got {val!r}")

    talents = data.get("talents", [])
    if not isinstance(talents, list):
        errors.append("'talents' must be a list")
    else:
        for i, talent in enumerate(talents):
            if not isinstance(talent, dict) or not talent.get("name"):
                errors.append(f"Talent at index {i} must have a 'name' field")

    skills = data.get("skills", [])
    if not isinstance(skills, list):
        errors.append("'skills' must be a list")
    else:
        for i, skill in enumerate(skills):
            if not isinstance(skill, dict) or not skill.get("name"):
                errors.append(f"Skill at index {i} must have a 'name' field")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def validate_and_raise(data: dict[str, Any]) -> None:
    """Validate and raise ValidationError if invalid."""
    validate_character(data).raise_if_invalid()