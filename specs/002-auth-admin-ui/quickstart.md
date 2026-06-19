# Quickstart Validation Guide: Authentication & Admin UI

**Feature**: 002-auth-admin-ui | **Date**: 2026-06-19

This guide proves the feature works end-to-end. Run these scenarios in order after completing implementation. Each scenario is independent — reset the DB or use a fresh test DB between scenarios where indicated.

---

## Prerequisites

```bash
# Install dependencies (uv workspace)
uv sync

# Start the app (new entry point)
uv run uvicorn apps.web.main:app --port 7860 --reload

# Or via Docker
docker compose -f deploy/compose/local.yml up
```

App should be accessible at `http://localhost:7860` (main, requires login) and `http://localhost:7860/register` (registration, no login required).

---

## Scenario 1 — Open Registration

**Covers**: FR-016, FR-017, User Story 1 (registration path)

1. Open `http://localhost:7860/register` in a browser — confirm the page loads without a login prompt.
2. Submit the form with `username=testgm`, `email=testgm@example.com`, `password=hunter2hunter2` (≥8 chars), `confirm=hunter2hunter2`.
3. **Expected**: Success message with a link to sign in. No error.
4. Attempt to register again with the same username.
5. **Expected**: Error message indicating username is taken.
6. Attempt to register with the same email but a different username.
7. **Expected**: Error message indicating email is already registered.

---

## Scenario 2 — GM Login and Session Persistence

**Covers**: FR-001, FR-002, User Story 1 (login path)

1. Open `http://localhost:7860` — confirm the Gradio login screen appears (not the main app).
2. Log in with `testgm / hunter2hunter2` (created in Scenario 1).
3. **Expected**: Login succeeds; Campaign Dashboard is displayed (empty — no campaigns yet).
4. Open a new tab at `http://localhost:7860`.
5. **Expected**: New tab shows Campaign Dashboard directly (session persists via cookie), no re-login required.
6. Refresh the page.
7. **Expected**: Session maintained; still on Campaign Dashboard.

---

## Scenario 3 — Campaign Create and Admin Dashboard

**Covers**: FR-006, FR-003, FR-018, FR-010, FR-011, User Story 3

1. On the Campaign Dashboard, create a campaign named `The Iron Crown` (game system: Earthdawn 4th Ed).
2. **Expected**: Campaign appears in the list with a 6-character UPPERCASE alphanumeric join code (e.g., `A3KP72`).
3. Create a second campaign named `Thornhaven`.
4. **Expected**: Two campaigns listed; each with a distinct join code.
5. Attempt to create a campaign named `the iron crown` (different casing).
6. **Expected**: Error message: "A campaign named 'the iron crown' already exists." (or similar). No new campaign created.
7. Verify the list still shows exactly two campaigns.

---

## Scenario 4 — Campaign Detail and Join Code Copy

**Covers**: FR-007, SC-001, SC-002, User Story 2

1. On the Campaign Dashboard, click "Open →" next to `The Iron Crown`.
2. **Expected**: Campaign Detail screen shows campaign name, join code (6-char UPPERCASE), game system, and created date. Join code has a [copy] button.
3. Click [copy] on the join code.
4. **Expected**: Join code copied to clipboard (paste somewhere to verify).
5. Click [← Back to Campaigns].
6. **Expected**: Returns to Campaign Dashboard in < 3 clicks from login (SC-001).

---

## Scenario 5 — Resume Campaign

**Covers**: FR-004, SC-006, User Story 1 (resume path)

1. In a new browser session (incognito), log in as `testgm`.
2. Navigate to Campaign Dashboard → open `The Iron Crown` → click "Resume Campaign".
3. **Expected**: GM Dashboard loads with story history, characters, and NPCs from the previous session intact.
4. Verify the join code displayed in the GM Dashboard matches the one from Campaign Detail.

---

## Scenario 6 — Player Rejoin

**Covers**: FR-008, FR-009, User Story 2

1. As GM (from Scenario 5), note the join code for `The Iron Crown` (e.g., `A3KP72`).
2. Open an incognito window and go to `http://localhost:7860`.
3. Enter `campaign name = The Iron Crown`, `join code = A3KP72`, `player name = Kira`.
4. **Expected**: Player session loads. No password required.
5. Close the incognito window.
6. Repeat step 3 with the same values.
7. **Expected**: Same player session restored; any character created under "Kira" in the previous session is accessible (SC-006).
8. Repeat step 3 with `player name = kira` (lowercase).
9. **Expected**: Same Player record matched (case-insensitive player name lookup); same character session.

---

## Scenario 7 — Unauthenticated Access Blocked

**Covers**: FR-005, SC-007

1. Clear all cookies/open incognito.
2. Navigate directly to `http://localhost:7860` (or any app URL).
3. **Expected**: Redirected to Gradio login screen within 1 second. No campaign or character data visible.

---

## Scenario 8 — Character Upsert

**Covers**: FR-012, SC-005, User Story 4

1. Log in as GM, resume `The Iron Crown`.
2. In the GM Dashboard > Characters tab, create a character named `Kira` with race `Elf`, discipline `Elementalist`.
3. **Expected**: One character named `Kira` in the list.
4. Create another character named `KIRA` with race `Human`, discipline `Warrior`.
5. **Expected**: Still exactly one character named `Kira`; race and discipline updated to `Human / Warrior`. No duplicate.
6. Create a character named `Bram`.
7. **Expected**: Two characters: `Kira` and `Bram`.

---

## Scenario 9 — NPC Upsert

**Covers**: FR-013, User Story 4

1. In the GM Dashboard > NPCs tab, create an NPC named `Elder Varos` with role `Quest Giver`.
2. **Expected**: One NPC named `Elder Varos`.
3. Create another NPC named `elder varos` with role `Antagonist`.
4. **Expected**: Still one NPC named `Elder Varos`; role updated to `Antagonist`.

---

## Scenario 10 — Invalid Player Join Attempt

**Covers**: Edge case from spec

1. In an incognito window, attempt to join with `campaign name = The Iron Crown`, `join code = WRONG1`, `player name = anyone`.
2. **Expected**: Error message — join code does not match.
3. Attempt with correct join code but wrong campaign name.
4. **Expected**: Error message — campaign not found.

---

## Scenario 11 — Multi-Account Isolation

**Covers**: FR-010 (name uniqueness scoped per user), Assumptions

1. Register a second account `testgm2 / hunter2hunter2`.
2. Log in as `testgm2`, create a campaign named `The Iron Crown`.
3. **Expected**: Succeeds — campaign names are unique per user, not globally.
4. Verify `testgm2`'s dashboard shows only their campaigns (not `testgm`'s).
5. Log in as `testgm`, verify their dashboard shows only their campaigns.

---

## Automated Test Coverage Expected

| Test file | Scenarios covered |
|-----------|------------------|
| `apps/web/tests/test_auth_service.py` | Registration, login validation, duplicate checks, bcrypt verify |
| `apps/web/tests/test_admin_campaigns.py` | Campaign CRUD, name uniqueness, join code generation/uniqueness |
| `apps/web/tests/test_upsert.py` | Character upsert, NPC upsert, case-insensitive matching |
| `apps/web/tests/test_player_join.py` | Player record create/restore, case-insensitive player name |