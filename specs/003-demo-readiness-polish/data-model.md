# Data Model: Demo-Readiness QA & Incremental Polish

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

---

## Summary

No new database tables or Alembic migrations are required for this cycle. The schema is correct as-of spec 002. All data model work is confined to fixing integration test fixtures that pre-date the `campaigns.owner_id NOT NULL` constraint added in migration `0002_auth_admin_ui.py`.

---

## Existing Entities Relevant to This Cycle

### User

**Table**: `users` | **Defined in**: `packages/core/core/models.py`

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `username` | String | UNIQUE, NOT NULL, case-insensitive index |
| `email` | String | UNIQUE, NOT NULL |
| `hashed_password` | String | NOT NULL |
| `created_at` | DateTime | NOT NULL, default=now() |

**Relevant to fix**: Integration test `campaign` fixtures must create a `User` row first and use `user.id` as `owner_id` when constructing `Campaign`. Use `hash_password("testpassword")` from `apps/web/services/auth` to generate the `hashed_password` field.

### Campaign

**Table**: `campaigns` | **Defined in**: `packages/core/core/models.py`

| Field | Type | Constraints |
|-------|------|-------------|
| `id` | UUID | PK |
| `name` | String | NOT NULL |
| `join_code` | String(6) | UNIQUE, NOT NULL |
| `gm_display_name` | String | NOT NULL |
| `owner_id` | UUID | FK → `users.id`, **NOT NULL** ← this is the missing field in all failing test fixtures |
| `created_at` | DateTime | NOT NULL |

**Index**: `ix_campaigns_owner_name_lower` — `(owner_id, lower(name))` UNIQUE — enforces case-insensitive name uniqueness per user.

### Character / NPC / StoryEvent

These tables are unchanged from spec 001. No modifications required.

---

## Test Fixture Pattern (Required)

The correct pattern for all `campaign` fixtures in `tests/integration/` after this fix:

```python
# tests/integration/conftest.py
import uuid
import pytest_asyncio
from core.models import User
from storage.sqlite.adapter import SQLiteBackend
from apps.web.services.auth import hash_password  # or inline bcrypt

@pytest_asyncio.fixture
async def test_owner_id(backend: SQLiteBackend) -> uuid.UUID:
    """Create a minimal GM user and return their id for use in campaign fixtures."""
    async with await backend.get_session() as session:
        user = User(
            id=uuid.uuid4(),
            username="testgm",
            email="testgm@example.com",
            hashed_password=hash_password("testpassword"),
        )
        session.add(user)
        await session.commit()
        return user.id
```

Then in each test file's `campaign` fixture:

```python
@pytest_asyncio.fixture
async def campaign(backend: SQLiteBackend, test_owner_id: uuid.UUID) -> Campaign:
    async with await backend.get_session() as session:
        c = Campaign(
            id=uuid.uuid4(),
            name="Test Campaign",
            join_code="TESTC001",
            gm_display_name="TestGM",
            owner_id=test_owner_id,   # ← was missing before this fix
        )
        session.add(c)
        await session.commit()
        await session.refresh(c)
        return c
```

---

## Import Path Note

`hash_password` lives in `apps/web/services/auth`. This function is not yet re-exported from `packages/core` or `packages/storage`. When used in `tests/integration/conftest.py`, import it with:

```python
from apps.web.services.auth import hash_password
```

The `apps/web` package is on the import path during pytest runs (it is declared as a workspace member in `pyproject.toml`).

---

## No Migration Required

The `campaigns.owner_id NOT NULL` constraint already exists in migration `0002_auth_admin_ui.py`. There is no schema gap — the tests were just not updated after the migration was written. No new Alembic migration file is needed for this spec.