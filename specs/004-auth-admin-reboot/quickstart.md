# Quickstart: Auth & Admin Reboot

## Prerequisites
- Ensure the repository dependencies are installed and the Python environment is activated.
- Initialize or migrate the SQLite database:
  ```powershell
  cd C:\Users\juane\Documents\personal\projects\StoryWeaver
  uv run alembic upgrade head
  ```

## Launch the App
1. Start the pure Gradio app from the web package:
   ```powershell
   cd apps/web
   uv run python app.py
   ```
2. Open the browser at the URL shown in the terminal (usually `http://127.0.0.1:7860`).

## Validation Scenarios

### 1. GM Auth Flow
- On the landing screen, use the **Create Account** tab to register a new GM account.
- Confirm the page displays a success message and the app transitions into the campaign dashboard.
- Sign out and sign in again from the **Sign In** tab with the same credentials.
- Expected outcome: the campaign dashboard appears immediately after sign-in.

### 2. Campaign Creation and Join Code
- In the GM dashboard, create a new campaign with a unique name.
- Verify the campaign appears in the campaign table with a 6-character join code.
- Select the campaign row, then click **Resume Campaign →**.
- Expected outcome: the GM dashboard shows the campaign join code at the top of the page.

### 3. Player Join Flow
- In a separate browser tab or private window, enter the campaign's join code and a player name.
- Do not enter a campaign name.
- Expected outcome: the player dashboard loads with character, twin chat, and history tabs available.

### 4. Player Rejoin Persistence
- Reopen the join flow and reuse the same join code and player name.
- Expected outcome: the same `Player` record is restored and character/story history is preserved.

### 5. AI Degradation
- If Ollama or ComfyUI are not running, verify the UI shows visible placeholder messages instead of blank tabs or crashes.
- Expected outcome: AI-dependent tabs render a clear unavailable state and non-AI tabs remain interactive.

### 6. Session Creation and Story Event Logging
- As GM, enter a campaign and navigate to the **Story History** tab.
- Create a new session with a title (e.g. "Session 1 — The Kaer") and today's date.
- Select the session from the dropdown and log a story event (e.g. "The party discovered the sealed kaer entrance.").
- Expected outcome: the history view shows the session as a header with the logged event beneath it.

### 7. Players Tab
- As GM, navigate to the **Players** tab.
- Expected outcome: a read-only table shows all players who have joined the campaign with their player name and character name (or "—" if no character created yet). No edit or remove actions are present.

### 8. Campaign Archive
- On the campaign dashboard, select a campaign and click **Archive**.
- Expected outcome: a visible confirmation message appears and the campaign no longer appears in the campaign table. Rejoining via the original join code returns "No campaign found with that join code" (the campaign is soft-deleted, not physically removed).

## Notes
- The app should not require `uvicorn` as the standard runtime after this feature is implemented.
- If local AI services are unavailable, the app should still launch and allow auth, campaign management, and player join.
