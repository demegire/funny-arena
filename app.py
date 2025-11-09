from __future__ import annotations

import contextlib
import csv
import json
import random
import threading
import uuid
from pathlib import Path
from typing import Callable, TypeVar, TypedDict

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None

BASE_DIR = Path(__file__).resolve().parent
MODELS_FILE = BASE_DIR / "models.csv"
JOKES_FILE = BASE_DIR / "jokes.json"
ELO_FILE = BASE_DIR / "elo_state.json"
STATE_LOCK_FILE = ELO_FILE.with_suffix(".lock")
BENCHMARK_EXPLANATION = (
    " Funny Arena pairs two jokes from the same category and lets visitors decide which model"
    " delivered the better punchline. Each click records a head-to-head result, updates the Elo"
    " ratings, and instantly refreshes the leaderboard."
    " Jokes categories are picked from https://en.wikipedia.org/wiki/Index_of_joke_types"
)

app = Flask(__name__, static_url_path="/funny-arena/static", static_folder="static")
app.wsgi_app = ProxyFix(app.wsgi_app, x_prefix=1)
lock = threading.Lock()
state_thread_lock = threading.Lock()
T = TypeVar("T")


class EloState(TypedDict):
    elos: dict[str, float]
    votes: dict[str, int]
    total_votes: int


@contextlib.contextmanager
def _state_guard(shared: bool) -> None:
    if fcntl is None:
        with state_thread_lock:
            yield
        return

    STATE_LOCK_FILE.touch(exist_ok=True)
    with STATE_LOCK_FILE.open("w") as handle:
        flag = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        fcntl.flock(handle, flag)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _load_models() -> list[str]:
    with MODELS_FILE.open() as handle:
        reader = csv.reader(handle)
        return [row[0].strip() for row in reader if row]


def _load_jokes() -> dict[str, dict[str, list[str]]]:
    with JOKES_FILE.open() as handle:
        return json.load(handle)


MODELS = _load_models()
JOKES = _load_jokes()


def _build_category_index() -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for model in MODELS:
        for category, jokes in JOKES.get(model, {}).items():
            if jokes:
                index.setdefault(category, []).append(model)
    return {category: models for category, models in index.items() if len(models) >= 2}


CATEGORY_INDEX = _build_category_index()
ACTIVE_BATTLES: dict[str, dict[str, str]] = {}


def _load_state() -> EloState:
    if ELO_FILE.exists():
        with ELO_FILE.open() as handle:
            stored = json.load(handle)
    else:
        stored = {}

    if "elos" in stored:
        elos = stored.get("elos", {})
        votes = stored.get("votes", {})
        total_votes = stored.get("total_votes", 0)
    else:
        elos = stored
        votes = {}
        total_votes = 0

    for model in MODELS:
        elos.setdefault(model, 1500.0)
        votes.setdefault(model, 0)

    return {
        "elos": elos,
        "votes": votes,
        "total_votes": int(total_votes),
    }


def _save_state(state: EloState) -> None:
    with ELO_FILE.open("w") as handle:
        json.dump(state, handle, indent=2)


def read_state() -> EloState:
    with _state_guard(shared=True):
        return _load_state()


def update_state(mutator: Callable[[EloState], T]) -> tuple[EloState, T]:
    with _state_guard(shared=False):
        state = _load_state()
        result = mutator(state)
        _save_state(state)
        return state, result


def build_leaderboard(
    elos: dict[str, float], votes: dict[str, int]
) -> list[dict[str, str | int | float]]:
    ordered = sorted(elos.items(), key=lambda item: item[1], reverse=True)
    leaderboard = []
    for position, (model, score) in enumerate(ordered, start=1):
        leaderboard.append(
            {
                "rank": position,
                "model": model,
                "elo": round(score, 1),
                "votes": votes.get(model, 0),
            }
        )
    return leaderboard


def elo_update(elos: dict[str, float], winner: str, loser: str, k: float = 32.0) -> None:
    winner_rating = elos[winner]
    loser_rating = elos[loser]
    expected_winner = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    expected_loser = 1 / (1 + 10 ** ((winner_rating - loser_rating) / 400))

    elos[winner] = winner_rating + k * (1 - expected_winner)
    elos[loser] = loser_rating + k * (0 - expected_loser)


def select_battle() -> dict[str, str | list[dict[str, str | int]]]:
    if not CATEGORY_INDEX:
        raise RuntimeError("No overlapping joke categories with at least two models.")
    state = read_state()
    leaderboard = build_leaderboard(state["elos"], state["votes"])
    rank_lookup = {entry["model"]: entry["rank"] for entry in leaderboard}

    category = random.choice(list(CATEGORY_INDEX.keys()))
    model_a, model_b = random.sample(CATEGORY_INDEX[category], 2)
    contestants = []
    for model in (model_a, model_b):
        joke = random.choice(JOKES[model][category])
        contestants.append(
            {
                "id": model,
                "joke": joke,
                "rank": rank_lookup.get(model, "-"),
            }
        )
    battle_id = str(uuid.uuid4())
    ACTIVE_BATTLES[battle_id] = {"winner": None, "model_a": model_a, "model_b": model_b}
    return {"battle_id": battle_id, "category": category, "contestants": contestants}


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/leaderboard")
def api_leaderboard():
    state = read_state()
    return jsonify(
        {
            "leaderboard": build_leaderboard(state["elos"], state["votes"]),
            "explanation": BENCHMARK_EXPLANATION,
            "total_votes": state["total_votes"],
        }
    )


@app.get("/api/battle")
def api_battle():
    battle = select_battle()
    return jsonify(battle)


@app.post("/api/battle_result")
def api_battle_result():
    payload = request.get_json(force=True) or {}
    battle_id = payload.get("battle_id")
    winner = payload.get("winner")

    if not battle_id or not winner:
        return jsonify({"error": "battle_id and winner are required."}), 400

    with lock:
        battle = ACTIVE_BATTLES.pop(battle_id, None)
        if not battle:
            return jsonify({"error": "Battle expired or unknown."}), 400

        contenders = {battle["model_a"], battle["model_b"]}
        if winner not in contenders:
            return jsonify({"error": "Winner must be part of the battle."}), 400

        loser = (contenders - {winner}).pop()
        state, leaderboard = update_state(
            lambda elo_state: _record_battle_result(elo_state, winner, loser)
        )

    return jsonify({"leaderboard": leaderboard, "total_votes": state["total_votes"]})


def _record_battle_result(state: EloState, winner: str, loser: str) -> list[dict[str, str | int | float]]:
    elo_update(state["elos"], winner, loser)
    state["votes"][winner] = state["votes"].get(winner, 0) + 1
    state["total_votes"] += 1
    return build_leaderboard(state["elos"], state["votes"])


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
