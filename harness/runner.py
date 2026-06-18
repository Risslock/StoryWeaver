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


# ── History recall runner ─────────────────────────────────────────────────────

async def _run_history_recall_scenario(scenario: dict[str, Any]) -> ScenarioResult:
    """Execute a single history_recall scenario against an in-memory SQLite DB."""
    from storage.sqlite.adapter import SQLiteBackend
    from story.history import create_event, list_events
    from core.models import Campaign, Session as GameSession

    sid = scenario.get("id", "unknown")

    try:
        backend = SQLiteBackend("sqlite+aiosqlite:///:memory:")
        await backend.initialize_db()

        setup = scenario.get("setup", {})
        campaign_cfg = setup.get("campaign", {})
        session_cfgs = setup.get("sessions", [])
        event_cfgs = setup.get("events", [])

        created_sessions: list[GameSession] = []

        async with await backend.get_session() as db:
            # Create campaign
            campaign = Campaign(
                id=uuid.uuid4(),
                name=campaign_cfg.get("name", "Test Campaign"),
                join_code=campaign_cfg.get("join_code", "TEST0000"),
                gm_display_name=campaign_cfg.get("gm_display_name", "GM"),
            )
            db.add(campaign)
            await db.commit()
            await db.refresh(campaign)

            # Create sessions
            from story.session import create_session as _create_session
            for scfg in session_cfgs:
                date_str = scfg.get("date_played", "2026-01-01")
                d = date.fromisoformat(date_str)
                s = await _create_session(
                    db,
                    campaign_id=campaign.id,
                    title=scfg.get("title", "Untitled Session"),
                    date_played=d,
                )
                created_sessions.append(s)

            # Create events
            for ecfg in event_cfgs:
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

            # Run query
            query = scenario.get("query", {})
            role = query.get("role", "gm")
            session_id_spec = query.get("session_id")
            filter_session_id: uuid.UUID | None = None
            if isinstance(session_id_spec, int) and session_id_spec < len(created_sessions):
                filter_session_id = created_sessions[session_id_spec].id

            events = await list_events(db, campaign.id, role=role, session_id=filter_session_id)

        # Check expectations
        expected = scenario.get("expected", {})
        failures: list[str] = []

        # event_count
        if "event_count" in expected:
            want = expected["event_count"]
            got = len(events)
            if got != want:
                failures.append(f"event_count: expected {want}, got {got}")

        contents = [e.content for e in events]

        # must_contain_content
        for needle in expected.get("must_contain_content", []):
            if not any(needle in c for c in contents):
                failures.append(f"must_contain_content: '{needle}' not found in any event")

        # must_not_contain_content
        for needle in expected.get("must_not_contain_content", []):
            if any(needle in c for c in contents):
                failures.append(f"must_not_contain_content: '{needle}' unexpectedly found")

        # ordered_content
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


async def _run_scenario(scenario: dict[str, Any], scenario_type: str) -> ScenarioResult:
    sid = scenario.get("id", "unknown")
    if scenario_type == "history_recall":
        return await _run_history_recall_scenario(scenario)
    # Remaining types (gm_agent, player_agent, twin_dialogue, imagegen, session_planning)
    # require their respective infrastructure. Return a skip result until implemented.
    return ScenarioResult(sid, True, f"SKIP — runner support for '{scenario_type}' not yet implemented")


# ── File / directory execution ────────────────────────────────────────────────

async def run_file(yaml_path: Path) -> list[ScenarioResult]:
    scenario_type = _detect_scenario_type(yaml_path)
    with yaml_path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    scenarios = doc.get("scenarios", [])
    results = []
    for scenario in scenarios:
        result = await _run_scenario(scenario, scenario_type)
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