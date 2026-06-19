# Quickstart Validation Guide: Demo-Readiness QA & Incremental Polish

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

---

## Prerequisites

- Python 3.12+ and `uv` installed
- Project dependencies installed: `uv sync`
- For AI-mode validations: Ollama running locally with a chat model pulled (e.g. `ollama run llama3`); `IMAGE_PROVIDER=comfyui` or similar set if testing image generation
- For degraded-mode validations: Ollama NOT running (or `AI_PROVIDER=none`)

---

## Gate 1 — Full Test Suite Passes

This is the primary gate for spec 003. Run from repo root:

```bash
uv run pytest -v
```

**Expected after fix**: All tests pass, exit code 0, zero failures, zero errors.

Run integration tests in isolation to confirm the fixture fix works:

```bash
uv run pytest tests/integration/ -v
```

**Expected after fix**: 39/39 integration tests PASS (previously 34 failed with `NOT NULL constraint failed: campaigns.owner_id`).

Unit tests:

```bash
uv run pytest apps/web/tests/ -v
```

**Expected**: 31/31 PASS (no change from pre-spec state).

---

## Gate 2 — Linting Clean

```bash
uv run ruff check .
```

**Expected**: Zero violations (after auto-fix run and manual E501 cleanup).

Auto-fix pass (run once before manual cleanup):

```bash
uv run ruff check --fix .
```

Verify auto-fix did not break tests:

```bash
uv run pytest -v
```

---

## Gate 3 — App Starts Without Error

```bash
uv run python -m apps.web.main
```

Or:

```bash
uv run python apps/web/main.py
```

**Expected**: App starts on `http://localhost:7860`, no import errors, no `AttributeError` or `RuntimeError` on startup.

---

## Validation Scenario 1 — Auth Flow (US-1)

1. Open `http://localhost:7860` in browser
2. Click **Create Account** tab; fill in username, email, password (×2); click **Create Account**
3. **Expected**: Admin/campaign dashboard appears immediately; no page reload required
4. Create a campaign named "QA Demo Campaign"; **Expected**: appears in campaign list
5. Click **Sign Out** (or open a new incognito tab and sign in)
6. On Sign In tab: enter username + password; click **Sign In**
7. **Expected**: Campaign list shows "QA Demo Campaign"

---

## Validation Scenario 2 — GM Experience (US-2)

1. Sign in as GM; select "QA Demo Campaign"; click **Resume Campaign →**
2. **Expected**: GM Dashboard opens, join code (6 uppercase chars) shown at top
3. Go to NPCs tab; enter name "Elder Varos", personality "Wise elder", background "Ancient mage"; click **Save NPC**
4. **Expected**: "Elder Varos" appears in NPC selector dropdown
5. Go to Story History tab; enter "The party discovers a hidden vault"; select event type; click **Log Event**
6. **Expected**: Event appears in the event timeline immediately

---

## Validation Scenario 3 — Player Experience (US-3)

1. Copy join code from campaign detail
2. Open incognito tab; enter campaign name, join code, and player name "Alice"; click **Join Campaign**
3. **Expected**: Player Dashboard shows "Joined! Welcome, Alice."
4. Fill in character form (name "Brekk", race "Ork", discipline "Warrior", circle 1, attributes, background); click **Save Character**
5. **Expected**: "Brekk" appears in character selector dropdown
6. Select "Brekk"; **Expected**: character sheet renders with all saved fields
7. Close incognito tab; open new incognito tab; rejoin with same join code and player name "Alice"
8. **Expected**: "Brekk" already available in selector without re-creation

---

## Validation Scenario 4 — Session Summary (US-5)

**AI mode** (Ollama running):

1. Log at least 3 events of different types in a session
2. In Story History tab, select the session in the filter dropdown
3. Click **Generate Session Summary**
4. **Expected**: A narrative paragraph appears (not a raw event list); output is non-empty

**Degraded mode** (Ollama not running):

1. Same setup; click **Generate Session Summary**
2. **Expected**: A formatted event list appears; no exception; no blank output

---

## Validation Scenario 5 — Scene Pre-population (US-6)

1. Log 2+ events in a session
2. In Story History tab, select the session in the filter dropdown
3. Scroll to Scene Illustration section
4. **Expected**: "Scene Description" input is pre-filled with a brief text summary of the session events

---

## Validation Scenario 6 — Portrait Generation (US-4)

**AI mode**:

1. Create a character with a physical description field filled in
2. Click **Generate Portrait**
3. **Expected**: Portrait image appears; button was disabled during generation
4. Select a different character and back; **Expected**: portrait persists, re-displayed on reselection

**Degraded mode**:

1. Ensure Ollama not running / image provider not configured
2. Navigate to character tab
3. **Expected**: **Generate Portrait** button is visually disabled; AI-unavailable banner shown