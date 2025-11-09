# Funny Arena

Funny Arena is a lightweight Flask app that lets people pit large language models against each other in a joke-writing arena. Two jokes from the same category are shown side by side, voters pick the funnier one (or call a draw), and the app updates a persistent Elo leaderboard in real time.

## Highlights

- **Instant battles:** `/api/battle` pairs two models that both have jokes for a randomly chosen category.
- **Elo ranking:** Every vote updates model ratings plus per-model vote counts and a global total.
- **Draw support:** Voters can mark a round as a draw to prevent rating swings when both jokes feel equal.
- **Safe persistence:** Leaderboard state lives in `elo_state.json` with file locks (`elo_state.lock`) to avoid corruption when multiple workers run.

## Project layout

| Path | Purpose |
| --- | --- |
| `app.py` | Flask application, REST API, Elo management, file locking. |
| `templates/index.html` | Single-page UI with leaderboard + arena tabs. |
| `static/app.js` | Fetches leaderboard/battles, submits votes, animates UI. |
| `static/style.css` | Styling for the dashboard experience. |
| `models.csv` | Ordered list of model IDs that appear on the leaderboard. |
| `categories.csv` | Joke categories sourced from Wikipedia's joke index. |
| `jokes.json` | `{model: {category: [joke, ...]}}` payload used to surface jokes. |
| `make_jokes.py` | Helper script that re-generates `jokes.json` via OpenRouter. |
| `elo_state.json` | Runtime Elo/vote state (auto-created). |

## Prerequisites

- Python 3.11+ (the type hints assume 3.11 style features).
- `pip` for dependency installation.
- (Optional) OpenRouter API access if you plan to regenerate jokes.

## Quick start

```bash
git clone <repo-url>
cd funny-arena
python -m venv .venv
source .venv/bin/activate        # On Windows use: .venv\Scripts\activate
pip install -r requirements.txt
python app.py                    # Starts on http://127.0.0.1:5000
```

When running behind a reverse proxy (or on a platform that injects `SCRIPT_NAME`), ensure the proxy forwards `X-Forwarded-Prefix` so the `ProxyFix` middleware keeps static URLs correct.

## API reference

- `GET /api/leaderboard` – Returns `leaderboard`, `total_votes`, and a human-readable explanation of the benchmark mechanics.
- `GET /api/battle` – Picks a random category with ≥2 models, returns a `battle_id`, category label, and two contestants (model IDs stay hidden client-side until a vote).
- `POST /api/battle_result` – Body must include `battle_id` and either `winner` (model ID) **or** `draw: true`. The endpoint validates that the winner participated, updates Elo ratings, increments votes/total votes, and replies with the refreshed leaderboard.

Example vote request:

```bash
curl -X POST http://localhost:5000/api/battle_result \
  -H "Content-Type: application/json" \
  -d '{"battle_id": "<uuid>", "winner": "openai/gpt-4o-mini"}'
```

## Data lifecycle

1. **Model roster:** Update `models.csv` to add/remove contenders. Every model gets an initial Elo of `1500`.
2. **Category coverage:** Joke battles only occur for categories where at least two models have jokes. If you add categories, ensure each model has jokes for them.
3. **Joke generation:** `make_jokes.py` calls the OpenRouter API with the template `Make a '{category}' joke.` for each model/category pair, storing results in `jokes.json`.
   - Set `Authorization: Bearer <OPENROUTER_API_KEY>` before running.
   - The script writes to `jokes.json` as it goes; keep a backup if you are iterating.
4. **State reset:** Delete `elo_state.json` (and `.lock`) to reset the leaderboard. The app recreates these files on next start with default ratings/votes.

## Operational notes

- **Concurrency:** File locking uses `fcntl` (POSIX). On Windows, it falls back to a process-local `threading.Lock`, so prefer running a single worker there.
- **Draw handling:** Draws still increment `total_votes` but not per-model vote counts. Elo updates use the standard draw formula with `k=32`.
- **Static assets:** Everything in `static/` is committed—there is no build step. If you change CSS/JS, just restart (or rely on Flask’s reloader in debug mode).
- **Deployment:** For production, run the app under a WSGI server (Gunicorn, uWSGI, etc.) and point it to `app:app`. Ensure the process has write access to the project directory for state files.

## Troubleshooting

- **“Battle expired or unknown.”** – The browser waited too long before submitting a vote; request a fresh battle.
- **Missing categories in the UI.** – Confirm every model has jokes for that category; otherwise the category is filtered out when the index is built.
- **Persistent 500s on vote submission.** – Inspect `elo_state.json` for corruption or manually delete it to allow a clean rebuild.

## Contributing

1. Create a feature branch.
2. Update docs/tests if applicable (there are no automated tests yet; manual verification is the norm).
3. Run the app locally and click through a few battles to ensure the leaderboard updates.
4. Open a pull request describing the change and any data files touched.

Enjoy benchmarking which LLMs actually land the punchline!

