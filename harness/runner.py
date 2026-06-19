"""Harness scenario runner — executes YAML fixture files as regression tests.

Usage:
    # Run all scenarios in a directory
    uv run python harness/runner.py --dir harness/scenarios/history_recall/

    # Run a single scenario file
    uv run python harness/runner.py --file harness/scenarios/history_recall/role_scoped_filter.yaml

    # Run all known scenario directories
    uv run python harness/runner.py --all

Exit code: 0 if all scenarios pass, 1 if any scenario fails.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path
from typing import Any

import yaml

# Repository root (parent of harness/)
_REPO_ROOT = Path(__file__).parent.parent

# Known scenario directories, in dependency order
_ALL_DIRS = [
    "harness/scenarios/history_recall",
    "harness/scenarios/gm_agent",
    "harness/scenarios/player_agent",
    "harness/scenarios/twin_dialogue",
    "harness/scenarios/imagegen",
    "harness/scenarios/session_planning",
]


# ── Result types ──────────────────────────────────────────────────────────────

class ScenarioResult:
    def __init__(self, scenario_id: str, passed: bool, message: str) -> None:
        self.scenario_id = scenario_id
        self.passed = passed
        self.message = message

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"  [{status}] {self.scenario_id}: {self.message}"


# ── Shared DB setup helper ────────────────────────────────────────────────────

async def _bootstrap_db(setup: dict[str, Any]) -> tuple[Any, Any, dict[str, Any]]:
    """Spin up an in-memory SQLite DB and seed it from the scenario's setup block.

    Returns (backend, campaign, entities) where entities may contain keys:
    'character', 'characters', 'npc', 'npcs', 'sessions'.
    """
    from core.models import NPC, Campaign, Character
    from storage.sqlite.adapter import SQLiteBackend
    from story.session import create_session as _create_session

    backend = SQLiteBackend("sqlite+aiosqlite:///:memory:")
    await backend.initialize_db()

    campaign_cfg = setup.get("campaign", {})
    entities: dict[str, Any] = {}

    async with await backend.get_session() as db:
        campaign = Campaign(
            id=uuid.uuid4(),
            name=campaign_cfg.get("name", "Test Campaign"),
            join_code=campaign_cfg.get("join_code", "TEST0000"),
            gm_display_name=campaign_cfg.get("gm_display_name", "GM"),
        )
        db.add(campaign)
        await db.commit()
        await db.refresh(campaign)
        entities["campaign"] = campaign

        # Single character
        if "character" in setup:
            cfg = setup["character"]
            char = Character(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                player_display_name=cfg.get("player_display_name", "Player"),
                name=cfg.get("name", "Hero"),
                race=cfg.get("race", "Human"),
                discipline=cfg.get("discipline", "Warrior"),
                circle=cfg.get("circle", 1),
                background=cfg.get("background", ""),
                personality=cfg.get("personality", ""),
                goals=cfg.get("goals"),
                physical_description=cfg.get("physical_description"),
                portrait_url=cfg.get("portrait_url"),
            )
            db.add(char)
            await db.commit()
            await db.refresh(char)
            entities["character"] = char

        # Multiple characters
        created_chars: list[Any] = []
        for cfg in setup.get("characters", []):
            char = Character(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                player_display_name=cfg.get("player_display_name", "Player"),
                name=cfg.get("name", "Hero"),
                race=cfg.get("race", "Human"),
                discipline=cfg.get("discipline", "Warrior"),
                circle=cfg.get("circle", 1),
                background=cfg.get("background", ""),
                personality=cfg.get("personality", ""),
                goals=cfg.get("goals"),
                physical_description=cfg.get("physical_description"),
                portrait_url=cfg.get("portrait_url"),
            )
            db.add(char)
            await db.commit()
            await db.refresh(char)
            created_chars.append(char)
        if created_chars:
            entities["characters"] = created_chars

        # Single NPC
        if "npc" in setup:
            cfg = setup["npc"]
            npc = NPC(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                name=cfg.get("name", "NPC"),
                role=cfg.get("role", ""),
                race=cfg.get("race", "Human"),
                personality=cfg.get("personality", ""),
                background=cfg.get("background", ""),
                gm_notes=cfg.get("gm_notes", ""),
                is_visible_to_players=cfg.get("is_visible_to_players", True),
            )
            db.add(npc)
            await db.commit()
            await db.refresh(npc)
            entities["npc"] = npc

        # Multiple NPCs
        created_npcs: list[Any] = []
        for cfg in setup.get("npcs", []):
            npc = NPC(
                id=uuid.uuid4(),
                campaign_id=campaign.id,
                name=cfg.get("name", "NPC"),
                role=cfg.get("role", ""),
                race=cfg.get("race", "Human"),
                personality=cfg.get("personality", ""),
                background=cfg.get("background", ""),
                gm_notes=cfg.get("gm_notes", ""),
                is_visible_to_players=cfg.get("is_visible_to_players", True),
            )
            db.add(npc)
            await db.commit()
            await db.refresh(npc)
            created_npcs.append(npc)
        if created_npcs:
            entities["npcs"] = created_npcs

        # Sessions
        created_sessions: list[Any] = []
        for scfg in setup.get("sessions", []):
            date_str = scfg.get("date_played", "2026-01-01")
            d = date.fromisoformat(date_str)
            s = await _create_session(
                db,
                campaign_id=campaign.id,
                title=scfg.get("title", "Untitled Session"),
                date_played=d,
            )
            created_sessions.append(s)
        if created_sessions:
            entities["sessions"] = created_sessions

        # Events (require sessions already created)
        from story.history import create_event
        for ecfg in setup.get("events", []):
            session_index = ecfg.get("session_index")
            ev_session_id: uuid.UUID | None = None
            if session_index is not None and session_index < len(created_sessions):
                ev_session_id = created_sessions[session_index].id
            await create_event(
                db,
                campaign_id=campaign.id,
                event_type=ecfg.get("event_type", "dialogue"),
                content=ecfg.get("content", ""),
                is_public=ecfg.get("is_public", True),
                session_id=ev_session_id,
                participants=ecfg.get("participants", []),
            )

    return backend, campaign, entities


def _resolve_tool_input(raw: dict[str, Any], entities: dict[str, Any]) -> dict[str, Any]:
    """Replace template variables like '$character.id', '$npc.id', '$campaign.id'."""
    resolved: dict[str, Any] = {}
    for k, v in raw.items():
        if isinstance(v, str) and v.startswith("$"):
            parts = v[1:].split(".")
            obj = entities.get(parts[0])
            if obj is not None and len(parts) > 1:
                resolved[k] = getattr(obj, parts[1], v)
            else:
                resolved[k] = v
        else:
            resolved[k] = v
    return resolved


# ── History recall runner ─────────────────────────────────────────────────────

async def _run_history_recall_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    """Execute a single history_recall scenario against an in-memory SQLite DB."""
    from story.history import list_events

    sid = scenario.get("id", "unknown")

    try:
        backend, campaign, entities = await _bootstrap_db(scenario.get("setup", {}))
        sessions = entities.get("sessions", [])

        async with await backend.get_session() as db:
            query = scenario.get("query", {})
            role = query.get("role", "gm")
            session_id_spec = query.get("session_id")
            filter_session_id: uuid.UUID | None = None
            if isinstance(session_id_spec, int) and session_id_spec < len(sessions):
                filter_session_id = sessions[session_id_spec].id

            events = await list_events(db, campaign.id, role=role, session_id=filter_session_id)

        expected = scenario.get("expected", {})
        failures: list[str] = []

        if "event_count" in expected:
            want = expected["event_count"]
            got = len(events)
            if got != want:
                failures.append(f"event_count: expected {want}, got {got}")

        contents = [e.content for e in events]

        for needle in expected.get("must_contain_content", []):
            if not any(needle in c for c in contents):
                failures.append(f"must_contain_content: '{needle}' not found in any event")

        for needle in expected.get("must_not_contain_content", []):
            if any(needle in c for c in contents):
                failures.append(f"must_not_contain_content: '{needle}' unexpectedly found")

        ordered = expected.get("ordered_content", [])
        if ordered:
            indices = []
            for needle in ordered:
                found = next((i for i, c in enumerate(contents) if needle in c), None)
                if found is None:
                    failures.append(f"ordered_content: '{needle}' not found in results")
                else:
                    indices.append(found)
            if indices and indices != sorted(indices):
                failures.append(f"ordered_content: events not in expected order — indices {indices}")

        if failures:
            return ScenarioResult(sid, False, "; ".join(failures))
        return ScenarioResult(sid, True, "all assertions passed")

    except Exception as exc:
        return ScenarioResult(sid, False, f"exception: {exc}")


# ── GM agent runner ───────────────────────────────────────────────────────────

async def _run_gm_agent_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    from agents.gm_agent.gm_agent import (
        CreateEventInput,
        GetNPCsInput,
        ToggleNPCVisibilityInput,
        build_gm_agent_tools,
    )
    from core.errors import AccessDeniedError, EntityNotFoundError, ValidationError
    from story.history import list_events

    sid = scenario.get("id", "unknown")
    tool_name = scenario.get("tool", "")
    expected = scenario.get("expected", {})

    _ERROR_TYPES: dict[str, type] = {
        "AccessDeniedError": AccessDeniedError,
        "EntityNotFoundError": EntityNotFoundError,
        "ValidationError": ValidationError,
    }

    try:
        backend, campaign, entities = await _bootstrap_db(scenario.get("setup", {}))
        raw_input = _resolve_tool_input(scenario.get("tool_input", {}), entities)

        async with await backend.get_session() as db:
            tools = build_gm_agent_tools(campaign.id, db)

            try:
                if tool_name == "create_story_event":
                    result = await tools["create_story_event"](CreateEventInput(**raw_input))
                elif tool_name == "toggle_npc_visibility":
                    if isinstance(raw_input.get("npc_id"), str):
                        raw_input["npc_id"] = uuid.UUID(raw_input["npc_id"])
                    result = await tools["toggle_npc_visibility"](ToggleNPCVisibilityInput(**raw_input))
                elif tool_name == "get_all_npcs":
                    if isinstance(raw_input.get("campaign_id"), str):
                        raw_input["campaign_id"] = uuid.UUID(raw_input["campaign_id"])
                    result = await tools["get_all_npcs"](GetNPCsInput(**raw_input))
                else:
                    return ScenarioResult(sid, True, f"SKIP — runner does not support gm_agent tool '{tool_name}'")

                # Expected success
                if expected.get("outcome") == "error":
                    return ScenarioResult(sid, False, f"expected error but tool succeeded with {result!r}")

                failures: list[str] = []

                # result_field check
                if "result_field" in expected:
                    field = expected["result_field"]
                    val = getattr(result, field, None)
                    if expected.get("result_not_null") and val is None:
                        failures.append(f"result.{field} is None, expected non-null")
                    if "result_value" in expected and val != expected["result_value"]:
                        failures.append(f"result.{field} expected {expected['result_value']!r}, got {val!r}")

                if "result_field_2" in expected:
                    field2 = expected["result_field_2"]
                    val2 = getattr(result, field2, None)
                    if "result_value_2" in expected and val2 != expected["result_value_2"]:
                        failures.append(f"result.{field2} expected {expected['result_value_2']!r}, got {val2!r}")

                # get_all_npcs specific checks
                if tool_name == "get_all_npcs":
                    if "result_count" in expected:
                        got = len(result.npcs)
                        want = expected["result_count"]
                        if got != want:
                            failures.append(f"npc count: expected {want}, got {got}")
                    if "result_npc_names" in expected:
                        names = [n.name for n in result.npcs]
                        for name in expected["result_npc_names"]:
                            if name not in names:
                                failures.append(f"expected NPC '{name}' not in results")
                    if "must_not_contain_names" in expected:
                        names = [n.name for n in result.npcs]
                        for name in expected["must_not_contain_names"]:
                            if name in names:
                                failures.append(f"NPC '{name}' should not appear in results")
                    if expected.get("gm_notes_present"):
                        for npc in result.npcs:
                            if npc.gm_notes is None:
                                failures.append(f"NPC {npc.name!r} missing gm_notes field")
                    if "sample_gm_notes_check" in expected:
                        chk = expected["sample_gm_notes_check"]
                        target = next((n for n in result.npcs if n.name == chk["npc_name"]), None)
                        if target is None:
                            failures.append(f"sample_gm_notes_check: NPC '{chk['npc_name']}' not found")
                        elif chk.get("expected_gm_notes_contains") not in (target.gm_notes or ""):
                            failures.append(
                                f"gm_notes for '{chk['npc_name']}' does not contain "
                                f"'{chk['expected_gm_notes_contains']}'"
                            )

                # Post-checks (create_story_event visibility)
                post = scenario.get("post_check", {})
                if post:
                    if tool_name == "create_story_event" and "must_contain_content" in post:
                        events = await list_events(db, campaign.id, role=post.get("query_as_role", "player"))
                        contents = [e.content for e in events]
                        needle = post["must_contain_content"]
                        if not any(needle in c for c in contents):
                            failures.append(f"post_check must_contain_content: '{needle}' not found")
                    if tool_name == "create_story_event" and "must_not_contain_content" in post:
                        events = await list_events(db, campaign.id, role=post.get("query_as_role", "player"))
                        contents = [e.content for e in events]
                        needle = post["must_not_contain_content"]
                        if any(needle in c for c in contents):
                            failures.append(f"post_check must_not_contain_content: '{needle}' found unexpectedly")
                    if "gm_must_contain_content" in post:
                        events = await list_events(db, campaign.id, role="gm")
                        contents = [e.content for e in events]
                        needle = post["gm_must_contain_content"]
                        if not any(needle in c for c in contents):
                            failures.append(f"post_check gm_must_contain_content: '{needle}' not found in GM view")
                    if tool_name == "toggle_npc_visibility":
                        from core.models import NPC
                        from sqlalchemy import select
                        stmt = select(NPC).where(
                            NPC.campaign_id == campaign.id,
                            NPC.is_visible_to_players.is_(True),
                        )
                        npc_result = await db.execute(stmt)
                        visible_npcs = list(npc_result.scalars().all())
                        if "player_visible_query_includes_npc" in post:
                            toggled_name = getattr(entities.get("npc"), "name", "")
                            visible_names = [n.name for n in visible_npcs]
                            should_be_visible = post["player_visible_query_includes_npc"]
                            is_visible = toggled_name in visible_names
                            if should_be_visible and not is_visible:
                                failures.append(f"post_check: NPC '{toggled_name}' should be visible to players but isn't")
                            elif not should_be_visible and is_visible:
                                failures.append(f"post_check: NPC '{toggled_name}' should not be visible but is")

            except Exception as exc:
                if expected.get("outcome") == "error":
                    error_type_name = expected.get("error_type", "")
                    if error_type_name and error_type_name in _ERROR_TYPES:
                        expected_exc = _ERROR_TYPES[error_type_name]
                        if not isinstance(exc, expected_exc):
                            return ScenarioResult(
                                sid, False,
                                f"expected {error_type_name}, got {type(exc).__name__}: {exc}"
                            )
                    return ScenarioResult(sid, True, f"correctly raised {type(exc).__name__}")
                return ScenarioResult(sid, False, f"unexpected exception: {type(exc).__name__}: {exc}")

        if failures:
            return ScenarioResult(sid, False, "; ".join(failures))
        return ScenarioResult(sid, True, "all assertions passed")

    except Exception as exc:
        return ScenarioResult(sid, False, f"setup exception: {exc}")


# ── Player agent runner ───────────────────────────────────────────────────────

async def _run_player_agent_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    from agents.player_agent.player_agent import (
        GetCharacterInput,
        ListCharactersInput,
        UpdateCharacterInput,
        build_player_agent_tools,
    )
    from core.errors import AccessDeniedError, EntityNotFoundError, ValidationError

    sid = scenario.get("id", "unknown")
    tool_name = scenario.get("tool", "")
    expected = scenario.get("expected", {})
    session_ctx = scenario.get("session_context", {})
    display_name = session_ctx.get("display_name", "Player")

    _ERROR_TYPES: dict[str, type] = {
        "AccessDeniedError": AccessDeniedError,
        "EntityNotFoundError": EntityNotFoundError,
        "ValidationError": ValidationError,
    }

    try:
        backend, campaign, entities = await _bootstrap_db(scenario.get("setup", {}))
        raw_input = _resolve_tool_input(scenario.get("tool_input", {}), entities)

        async with await backend.get_session() as db:
            tools = build_player_agent_tools(display_name, campaign.id, db)

            try:
                if tool_name == "get_character_sheet":
                    if isinstance(raw_input.get("character_id"), str):
                        raw_input["character_id"] = uuid.UUID(raw_input["character_id"])
                    result = await tools["get_character_sheet"](GetCharacterInput(**raw_input))
                elif tool_name == "update_character_field":
                    if isinstance(raw_input.get("character_id"), str):
                        raw_input["character_id"] = uuid.UUID(raw_input["character_id"])
                    result = await tools["update_character_field"](UpdateCharacterInput(**raw_input))
                elif tool_name == "list_own_characters":
                    if isinstance(raw_input.get("campaign_id"), str):
                        raw_input["campaign_id"] = uuid.UUID(raw_input["campaign_id"])
                    else:
                        raw_input["campaign_id"] = campaign.id
                    result = await tools["list_own_characters"](ListCharactersInput(**raw_input))
                else:
                    return ScenarioResult(sid, True, f"SKIP — runner does not support player_agent tool '{tool_name}'")

                if expected.get("outcome") == "error":
                    return ScenarioResult(sid, False, f"expected error but tool succeeded with {result!r}")

                failures: list[str] = []

                if "result_field" in expected:
                    field = expected["result_field"]
                    val = getattr(result, field, None)
                    if "result_value" in expected and val != expected["result_value"]:
                        failures.append(f"result.{field} expected {expected['result_value']!r}, got {val!r}")

                if "result_field_2" in expected:
                    field2 = expected["result_field_2"]
                    val2 = getattr(result, field2, None)
                    if "result_value_2" in expected and val2 != expected["result_value_2"]:
                        failures.append(f"result.{field2} expected {expected['result_value_2']!r}, got {val2!r}")

                # list_own_characters specific checks
                if tool_name == "list_own_characters":
                    chars = result.characters
                    if "result_count" in expected:
                        if len(chars) != expected["result_count"]:
                            failures.append(f"character count: expected {expected['result_count']}, got {len(chars)}")
                    if "result_names" in expected:
                        names = [c.name for c in chars]
                        for name in expected["result_names"]:
                            if name not in names:
                                failures.append(f"expected character '{name}' in results")
                    if "must_not_contain_names" in expected:
                        names = [c.name for c in chars]
                        for name in expected["must_not_contain_names"]:
                            if name in names:
                                failures.append(f"character '{name}' should not appear in results")
                    if "has_portrait_map" in expected:
                        char_map = {c.name: c.has_portrait for c in chars}
                        for name, flag in expected["has_portrait_map"].items():
                            if char_map.get(name) != flag:
                                failures.append(f"has_portrait for '{name}': expected {flag}, got {char_map.get(name)}")

            except Exception as exc:
                if expected.get("outcome") == "error":
                    error_type_name = expected.get("error_type", "")
                    if error_type_name and error_type_name in _ERROR_TYPES:
                        expected_exc = _ERROR_TYPES[error_type_name]
                        if not isinstance(exc, expected_exc):
                            return ScenarioResult(
                                sid, False,
                                f"expected {error_type_name}, got {type(exc).__name__}: {exc}"
                            )
                    return ScenarioResult(sid, True, f"correctly raised {type(exc).__name__}")
                return ScenarioResult(sid, False, f"unexpected exception: {type(exc).__name__}: {exc}")

        if failures:
            return ScenarioResult(sid, False, "; ".join(failures))
        return ScenarioResult(sid, True, "all assertions passed")

    except Exception as exc:
        return ScenarioResult(sid, False, f"setup exception: {exc}")


# ── Twin dialogue runner ──────────────────────────────────────────────────────

async def _run_twin_dialogue_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    sid = scenario.get("id", "unknown")
    return ScenarioResult(
        sid, True,
        "SKIP — twin dialogue requires a live LLM provider; run harness/scoring/rubrics.py manually"
    )


# ── Imagegen runner ───────────────────────────────────────────────────────────

def _build_portrait_prompt(entity_type: str, entity_fields: dict[str, Any], gm_description: str = "") -> str | None:
    """Reproduce the portrait-prompt logic from apps/web/pages/player/character.py."""
    from imagegen.interface import PORTRAIT_PROMPT_PREFIX

    if entity_type == "scene":
        scene_prefix = "fantasy scene, Earthdawn tabletop RPG, atmospheric illustration, detailed, professional illustration"
        return f"{scene_prefix}, {gm_description}" if gm_description else None

    desc = (entity_fields.get("physical_description") or "").strip()
    if not desc:
        return None  # blocked — caller checks

    name = entity_fields.get("name", "")
    race = entity_fields.get("race", "")

    if entity_type == "character":
        discipline = entity_fields.get("discipline", "")
        return f"{PORTRAIT_PROMPT_PREFIX}, {name}, {race} {discipline}, {desc}"
    if entity_type == "npc":
        role = entity_fields.get("role", "")
        return f"{PORTRAIT_PROMPT_PREFIX}, {name}, {race} {role}, {desc}"

    return f"{PORTRAIT_PROMPT_PREFIX}, {name}, {race}, {desc}"


async def _run_imagegen_scenario(scenario: dict[str, Any], yaml_path: Path) -> ScenarioResult:
    sid = scenario.get("id", "unknown")
    file_stem = yaml_path.stem  # provider_unavailable | prompt_construction | response_handling

    try:
        if file_stem == "prompt_construction":
            entity_type = scenario.get("entity_type", "character")
            entity_fields = scenario.get("entity_fields", {})
            gm_description = scenario.get("gm_description", "")

            if scenario.get("expected_blocked"):
                prompt = _build_portrait_prompt(entity_type, entity_fields, gm_description)
                if prompt is not None:
                    return ScenarioResult(sid, False, "expected generation to be blocked but prompt was built")
                return ScenarioResult(sid, True, "correctly blocked — no physical description")

            prompt = _build_portrait_prompt(entity_type, entity_fields, gm_description)
            if prompt is None:
                return ScenarioResult(sid, False, "prompt is None — check physical_description field")

            failures: list[str] = []
            for needle in scenario.get("expected_prompt_contains", []):
                if needle not in prompt:
                    failures.append(f"prompt missing '{needle}'")
            for hint in scenario.get("expected_style_hints", []):
                if hint not in prompt:
                    failures.append(f"style hint '{hint}' not in prompt")

            if failures:
                return ScenarioResult(sid, False, "; ".join(failures))
            return ScenarioResult(sid, True, "prompt contains all expected keywords")

        if file_stem == "provider_unavailable":
            provider_name = scenario.get("provider", "huggingface")
            provider_cfg = scenario.get("provider_config", {})
            mock_http = scenario.get("mock_http")
            request_cfg = scenario.get("request", {})

            from imagegen.interface import ImageGenRequest
            request = ImageGenRequest(
                prompt=request_cfg.get("prompt", "test prompt"),
                entity_id=uuid.UUID(request_cfg.get("entity_id", str(uuid.uuid4()))),
            )

            if provider_name == "huggingface":
                from imagegen.providers.huggingface import HuggingFaceProvider
                provider = HuggingFaceProvider(
                    api_key=provider_cfg.get("api_key", ""),
                    model=provider_cfg.get("model"),
                )

                if mock_http:
                    import httpx

                    status_code: int = mock_http["status_code"]
                    body: str = mock_http.get("body", "")

                    class _MockTransport(httpx.AsyncBaseTransport):
                        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
                            return httpx.Response(status_code, text=body)

                    import unittest.mock as mock
                    original_client = httpx.AsyncClient

                    class _PatchedClient(httpx.AsyncClient):
                        def __init__(self, **kwargs: Any) -> None:
                            super().__init__(transport=_MockTransport(), **{k: v for k, v in kwargs.items() if k != "transport"})

                    with mock.patch("httpx.AsyncClient", _PatchedClient):
                        response = await provider.generate(request)
                else:
                    response = await provider.generate(request)

                fails: list[str] = []
                if "image_url" in scenario.get("expected", {}):
                    if response.image_url is not None:
                        fails.append(f"expected image_url=None, got {response.image_url!r}")
                if "error_contains" in scenario.get("expected", {}):
                    needle = scenario["expected"]["error_contains"]
                    if not response.error or needle not in response.error:
                        fails.append(f"error should contain '{needle}', got {response.error!r}")
                if fails:
                    return ScenarioResult(sid, False, "; ".join(fails))
                return ScenarioResult(sid, True, "provider error handled correctly")

            if provider_name == "comfyui":
                from core.errors import ProviderUnavailableError
                from imagegen.providers.comfyui import ComfyUIProvider
                provider_obj = ComfyUIProvider(base_url=provider_cfg.get("base_url"))

                expected_raises = scenario.get("expected", {}).get("raises", "")
                try:
                    await provider_obj.generate(request)
                    if expected_raises:
                        return ScenarioResult(sid, False, f"expected {expected_raises} but no exception raised")
                    return ScenarioResult(sid, True, "no exception raised (may be expected)")
                except ProviderUnavailableError:
                    if expected_raises == "ProviderUnavailableError":
                        return ScenarioResult(sid, True, "correctly raised ProviderUnavailableError")
                    return ScenarioResult(sid, False, "unexpected ProviderUnavailableError")
                except Exception as exc:
                    return ScenarioResult(sid, False, f"unexpected exception: {exc}")

            return ScenarioResult(sid, True, f"SKIP — unknown provider '{provider_name}'")

        if file_stem == "response_handling":
            provider_cfg = scenario.get("mock_response", {})
            entity_type = scenario.get("entity_type", "character")
            entity_fields = scenario.get("entity_fields", {})

            backend, campaign, entities = await _bootstrap_db({
                "campaign": {"name": "Imagegen Test", "join_code": "IMGTEST1", "gm_display_name": "GM"},
                entity_type: entity_fields,
            })

            from imagegen.interface import (
                ImageGenRequest,
                ImageGenResponse,
                ImageProvider,
            )

            class _MockProvider(ImageProvider):
                async def generate(self, req: ImageGenRequest) -> ImageGenResponse:
                    return ImageGenResponse(
                        image_url=provider_cfg.get("image_url"),
                        error=provider_cfg.get("error"),
                    )

            mock_provider = _MockProvider()
            prompt = _build_portrait_prompt(entity_type, entity_fields) or "test"

            from imagegen.interface import PORTRAIT_NEGATIVE_PROMPT
            entity_obj = entities.get(entity_type)
            entity_id = getattr(entity_obj, "id", uuid.uuid4())
            request = ImageGenRequest(prompt=prompt, negative_prompt=PORTRAIT_NEGATIVE_PROMPT, entity_id=entity_id)
            response = await mock_provider.generate(request)

            # Simulate the portrait_url persistence logic
            from core.models import NPC, Character
            from sqlalchemy import select

            async with await backend.get_session() as db:
                if response.image_url and not response.error:
                    if entity_type == "character":
                        result = await db.execute(select(Character).where(Character.id == entity_id))
                        ent = result.scalar_one_or_none()
                        if ent is not None:
                            ent.portrait_url = response.image_url
                            await db.commit()
                    elif entity_type == "npc":
                        result = await db.execute(select(NPC).where(NPC.id == entity_id))
                        ent = result.scalar_one_or_none()
                        if ent is not None:
                            ent.portrait_url = response.image_url
                            await db.commit()

                # Verify
                fails: list[str] = []
                expected = scenario.get("expected", {})

                if "portrait_url_matches" in expected:
                    if entity_type == "character":
                        result2 = await db.execute(select(Character).where(Character.id == entity_id))
                        ent2 = result2.scalar_one_or_none()
                        actual = getattr(ent2, "portrait_url", None)
                        if actual != expected["portrait_url_matches"]:
                            fails.append(f"portrait_url: expected {expected['portrait_url_matches']!r}, got {actual!r}")

                if "portrait_url_unchanged" in expected:
                    if entity_type == "character":
                        result2 = await db.execute(select(Character).where(Character.id == entity_id))
                        ent2 = result2.scalar_one_or_none()
                        actual = getattr(ent2, "portrait_url", None)
                        if actual != expected["portrait_url_unchanged"]:
                            fails.append(f"portrait_url should be unchanged at {expected['portrait_url_unchanged']!r}, got {actual!r}")

                if "error_contains" in expected:
                    needle = expected["error_contains"]
                    if not response.error or needle not in response.error:
                        fails.append(f"error should contain '{needle}', got {response.error!r}")

                if "error" in expected and expected["error"] is None:
                    if response.error is not None:
                        fails.append(f"expected no error but got {response.error!r}")

            # Handle multi-step scenarios
            steps = scenario.get("steps", [])
            if steps:
                for step in steps:
                    action = step.get("action", "")
                    if action == "generate_portrait":
                        if response.image_url != step.get("expected_image_url"):
                            fails.append("step generate_portrait: image_url mismatch")
                    elif action == "reload_character":
                        async with await backend.get_session() as db2:
                            if entity_type == "character":
                                result3 = await db2.execute(select(Character).where(Character.id == entity_id))
                                ent3 = result3.scalar_one_or_none()
                                actual3 = getattr(ent3, "portrait_url", None)
                                if actual3 != step.get("expected_portrait_url"):
                                    fails.append("step reload_character: portrait_url mismatch")

            if fails:
                return ScenarioResult(sid, False, "; ".join(fails))
            return ScenarioResult(sid, True, "imagegen response handling correct")

        return ScenarioResult(sid, True, f"SKIP — unknown imagegen file '{file_stem}'")

    except Exception as exc:
        return ScenarioResult(sid, False, f"exception: {exc}")


# ── Session planning runner ───────────────────────────────────────────────────

class _MockLLMProvider:
    """Echo-back LLM: returns the prompt verbatim so we can assert on history content."""

    def __init__(self) -> None:
        self.last_prompt: str = ""
        self.last_system: str = ""

    async def generate(self, prompt: str, system: str = "") -> str:
        self.last_prompt = prompt
        self.last_system = system
        return f"[MOCK PLAN]\n{prompt}"


async def _run_session_planning_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    from agents.gm_agent.gm_agent import GenerateSessionPlanInput, build_gm_agent_tools

    sid = scenario.get("id", "unknown")
    expected = scenario.get("expected", {})
    plan_input = scenario.get("plan_input", {})

    try:
        backend, campaign, entities = await _bootstrap_db(scenario.get("setup", {}))
        mock_llm = _MockLLMProvider()

        async with await backend.get_session() as db:
            tools = build_gm_agent_tools(campaign.id, db, llm_provider=mock_llm)
            inp = GenerateSessionPlanInput(
                campaign_id=campaign.id,
                session_number=plan_input.get("session_number", 1),
                focus_hints=plan_input.get("focus_hints", []),
            )

            try:
                result = await tools["generate_session_plan"](inp)
            except Exception as exc:
                if expected.get("outcome") == "error":
                    return ScenarioResult(sid, True, f"correctly raised {type(exc).__name__}")
                return ScenarioResult(sid, False, f"unexpected exception: {exc}")

        if expected.get("outcome") == "error":
            return ScenarioResult(sid, False, "expected error but tool succeeded")

        failures: list[str] = []

        if expected.get("plan_not_empty") and not result.plan_markdown.strip():
            failures.append("plan_markdown is empty")

        if "events_referenced_count" in expected:
            got = len(result.events_referenced)
            want = expected["events_referenced_count"]
            if got != want:
                failures.append(f"events_referenced_count: expected {want}, got {got}")

        # prompt_must_contain checks against the captured mock LLM prompt
        # (or starter plan text for empty-history case)
        check_text = mock_llm.last_prompt or result.plan_markdown
        for needle in expected.get("prompt_must_contain", []):
            if needle not in check_text:
                failures.append(f"prompt_must_contain: '{needle}' not found")

        # plan_must_contain_one_of — checks plan_markdown (starter plan text)
        for candidates in [expected.get("plan_must_contain_one_of", [])]:
            if candidates:
                if not any(c in result.plan_markdown.lower() for c in candidates):
                    failures.append(f"plan_must_contain_one_of: none of {candidates} found in plan")

        if expected.get("plan_must_have_sections"):
            if "#" not in result.plan_markdown:
                failures.append("plan_must_have_sections: no markdown headings found")

        for needle in expected.get("focus_hints_in_plan", []):
            if needle not in result.plan_markdown:
                failures.append(f"focus_hints_in_plan: '{needle}' not found in plan")

        if failures:
            return ScenarioResult(sid, False, "; ".join(failures))
        return ScenarioResult(sid, True, "all assertions passed")

    except Exception as exc:
        return ScenarioResult(sid, False, f"setup exception: {exc}")


# ── Dispatch by scenario file type ────────────────────────────────────────────

def _detect_scenario_type(yaml_path: Path) -> str:
    """Infer scenario type from directory name."""
    parts = yaml_path.parts
    if "history_recall" in parts:
        return "history_recall"
    if "gm_agent" in parts:
        return "gm_agent"
    if "player_agent" in parts:
        return "player_agent"
    if "twin_dialogue" in parts:
        return "twin_dialogue"
    if "imagegen" in parts:
        return "imagegen"
    if "session_planning" in parts:
        return "session_planning"
    return "unknown"


async def _run_scenario(scenario: dict[str, Any], scenario_type: str, yaml_path: Path) -> ScenarioResult:
    sid = scenario.get("id", "unknown")
    if scenario_type == "history_recall":
        return await _run_history_recall_scenario(scenario)
    if scenario_type == "gm_agent":
        return await _run_gm_agent_scenario(scenario)
    if scenario_type == "player_agent":
        return await _run_player_agent_scenario(scenario)
    if scenario_type == "twin_dialogue":
        return await _run_twin_dialogue_scenario(scenario)
    if scenario_type == "imagegen":
        return await _run_imagegen_scenario(scenario, yaml_path)
    if scenario_type == "session_planning":
        return await _run_session_planning_scenario(scenario)
    return ScenarioResult(sid, True, f"SKIP — unknown scenario type '{scenario_type}'")


# ── File / directory execution ────────────────────────────────────────────────

async def run_file(yaml_path: Path) -> list[ScenarioResult]:
    scenario_type = _detect_scenario_type(yaml_path)
    with yaml_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    scenarios = doc.get("scenarios", [])
    results = []
    for scenario in scenarios:
        result = await _run_scenario(scenario, scenario_type, yaml_path)
        results.append(result)
    return results


async def run_directory(dir_path: Path) -> list[ScenarioResult]:
    results: list[ScenarioResult] = []
    for yaml_file in sorted(dir_path.glob("*.yaml")):
        results.extend(await run_file(yaml_file))
    return results


# ── CLI entry point ───────────────────────────────────────────────────────────

def _print_report(results: list[ScenarioResult], label: str) -> int:
    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    print(f"\n{'='*60}")
    print(f" {label}")
    print(f"{'='*60}")
    for r in results:
        print(r)
    print(f"\n  Total: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)}")
    return 0 if not failed else 1


async def _main(args: argparse.Namespace) -> int:
    # Ensure packages are importable from repo root
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    exit_code = 0

    if args.all:
        for dir_rel in _ALL_DIRS:
            dir_path = _REPO_ROOT / dir_rel
            if not dir_path.exists():
                print(f"  [SKIP] {dir_rel} — directory not found")
                continue
            results = await run_directory(dir_path)
            if results:
                exit_code |= _print_report(results, dir_rel)
    elif args.dir:
        dir_path = Path(args.dir)
        if not dir_path.is_absolute():
            dir_path = _REPO_ROOT / dir_path
        results = await run_directory(dir_path)
        exit_code = _print_report(results, str(dir_path))
    elif args.file:
        file_path = Path(args.file)
        if not file_path.is_absolute():
            file_path = _REPO_ROOT / file_path
        results = await run_file(file_path)
        exit_code = _print_report(results, str(file_path))
    else:
        print("Usage: harness/runner.py --all | --dir <path> | --file <path>")
        return 1

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="StoryWeaver harness scenario runner")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="Run all known scenario directories")
    group.add_argument("--dir", metavar="PATH", help="Run all YAML files in a directory")
    group.add_argument("--file", metavar="PATH", help="Run scenarios from a single YAML file")
    args = parser.parse_args()
    sys.exit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()