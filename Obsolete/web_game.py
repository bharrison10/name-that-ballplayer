#!/usr/bin/env python3
"""
Name That Ballplayer — Web version with in-browser filters.

Usage:
  python web_game.py --data-dir ./baseballdatabank/core
  Then open http://localhost:5050 in your browser.
"""

import argparse
import os
import random
import sys

import pandas as pd
from flask import Flask, render_template_string, jsonify, request, send_file

from game import (
    load_data, get_player_pool, get_player_seasons,
    render_stats_image, compute_totals,
)

app = Flask(__name__)

STATE = {
    "batting": None,
    "people": None,
    "awards_df": None,
    "allstar_df": None,
    "appearances_df": None,
    "awards_share_df": None,
    "player_ids": [],
    "current_idx": 0,
    "current_name": None,
    "current_seasons": None,
    "score_correct": 0,
    "score_total": 0,
    "streak": 0,
    "best_streak": 0,
    "guesses": [],
    "hints_given": 0,
    "hint_text": "",
    "revealed": False,
    "last_correct": False,
    "output_dir": "./output",
    # Current filter settings
    "filters": {
        "min_years": 5,
        "min_pa": 1500,
        "played_in_start": None,
        "played_in_end": None,
    },
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Name That Ballplayer</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: Helvetica, Arial, sans-serif; background: #f5f3ed; color: #1a1a1a; }

    .topbar {
      background: #8C1515; padding: 10px 20px;
      display: flex; justify-content: space-between; align-items: center;
      border-bottom: 3px solid #5a0f0f; flex-wrap: wrap; gap: 8px;
    }
    .topbar h1 { color: #fff; font-family: Georgia, serif; font-size: 22px; }
    .topbar .subtitle { color: #e8c8c8; font-size: 11px; }
    .scoreboard { display: flex; gap: 20px; color: #fff; font-size: 13px; }
    .scoreboard b { font-size: 16px; }
    .streak-active { color: #90ee90 !important; }
    .best-val { color: #ffd700 !important; }

    .container { max-width: 1150px; margin: 0 auto; padding: 16px 10px; }

    /* Filter panel */
    .filter-bar {
      background: #fff; border: 1px solid #ccc; border-radius: 3px;
      padding: 10px 16px; margin-bottom: 12px;
      display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
      font-size: 13px;
    }
    .filter-bar label { font-weight: bold; color: #555; white-space: nowrap; }
    .filter-bar input[type="number"] {
      width: 70px; padding: 4px 6px; border: 1px solid #bbb; border-radius: 3px;
      font-size: 13px; text-align: center;
    }
    .filter-bar .filter-group { display: flex; align-items: center; gap: 4px; }
    .filter-bar .sep { color: #ccc; font-size: 18px; }
    .filter-bar .btn-apply {
      padding: 6px 16px; background: #8C1515; color: #fff; border: none;
      border-radius: 3px; font-weight: bold; cursor: pointer; font-size: 12px;
    }
    .filter-bar .btn-apply:hover { background: #a52020; }
    .filter-bar .btn-reset {
      padding: 6px 12px; background: #eee; color: #555; border: 1px solid #bbb;
      border-radius: 3px; cursor: pointer; font-size: 12px;
    }
    .filter-bar .pool-count {
      margin-left: auto; color: #888; font-size: 12px; white-space: nowrap;
    }
    .filter-toggle {
      background: none; border: 1px solid #ccc; border-radius: 3px;
      padding: 5px 12px; cursor: pointer; font-size: 12px; color: #555;
      margin-bottom: 8px;
    }
    .filter-toggle:hover { background: #f0f0f0; }

    .player-name-area {
      padding: 8px 0; border-bottom: 1px solid #ccc; margin-bottom: 10px;
      display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap;
    }
    .player-name { font-family: Georgia, serif; font-size: 24px; font-weight: bold; }
    .player-name.hidden { color: #999; }
    .player-name.revealed { color: #00457c; }
    .hint-text { font-family: Georgia, serif; font-size: 18px; color: #00457c; letter-spacing: 2px; }
    .correct-badge { color: #2d8a2d; font-size: 14px; font-weight: bold; }
    .revealed-badge { color: #cc0000; font-size: 14px; }

    .stats-img-container {
      background: #fff; border: 1px solid #ccc; border-radius: 2px;
      overflow-x: auto; margin-bottom: 12px;
    }
    .stats-img-container img { display: block; max-width: 100%; height: auto; }

    .guess-area {
      background: #fff; border: 1px solid #ccc; border-radius: 2px;
      padding: 12px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
    }
    .guess-input {
      flex: 1; min-width: 180px; padding: 9px 14px; font-size: 15px;
      font-family: Georgia, serif; border: 2px solid #8C1515; border-radius: 3px; outline: none;
    }
    .guess-input.disabled { background: #f0f0f0; border-color: #ccc; }

    .btn {
      padding: 9px 20px; font-size: 13px; font-weight: bold;
      border: none; border-radius: 3px; cursor: pointer; color: #fff;
    }
    .btn-guess { background: #8C1515; }
    .btn-hint { background: #555; }
    .btn-giveup { background: #cc0000; }
    .btn-next { background: #2d6b2d; }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }

    .guesses { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px; }
    .guess-tag { padding: 3px 10px; border-radius: 12px; font-size: 12px; }
    .guess-correct { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
    .guess-wrong { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }

    .footer-info { margin-top: 12px; font-size: 11px; color: #888; text-align: center; }
  </style>
</head>
<body>
  <div class="topbar">
    <div>
      <h1>&#9918; Name That Ballplayer</h1>
      <div class="subtitle">Guess the player from their career stats</div>
    </div>
    <div class="scoreboard">
      <span>Score: <b id="score">0/0</b></span>
      <span>Streak: <b id="streak">0</b></span>
      <span>Best: <b id="best" class="best-val">0</b></span>
    </div>
  </div>

  <div class="container">

    <!-- Filter toggle -->
    <button class="filter-toggle" onclick="toggleFilters()">&#9881; Filters</button>

    <!-- Filter panel (hidden by default) -->
    <div id="filterPanel" class="filter-bar" style="display:none;">
      <div class="filter-group">
        <label>Min Seasons:</label>
        <input type="number" id="fMinYears" value="5" min="1" max="30">
      </div>
      <div class="sep">|</div>
      <div class="filter-group">
        <label>Min AB:</label>
        <input type="number" id="fMinPA" value="1500" min="0" max="15000" step="500">
      </div>
      <div class="sep">|</div>
      <div class="filter-group">
        <label>Played in:</label>
        <input type="number" id="fPlayedStart" placeholder="e.g. 2000" min="1871" max="2025" style="width:80px;">
        <span>–</span>
        <input type="number" id="fPlayedEnd" placeholder="e.g. 2025" min="1871" max="2025" style="width:80px;">
      </div>
      <button class="btn-apply" onclick="applyFilters()">Apply &amp; New Game</button>
      <button class="btn-reset" onclick="resetFilters()">Reset</button>
      <div class="pool-count" id="poolCount"></div>
    </div>

    <div class="player-name-area">
      <div id="playerName" class="player-name hidden">??? ???</div>
      <div id="hintText" class="hint-text"></div>
      <div id="resultBadge"></div>
    </div>

    <div class="stats-img-container">
      <img id="statsImg" src="" alt="Loading stats...">
    </div>

    <div class="guess-area">
      <input id="guessInput" class="guess-input" type="text"
             placeholder="Who is this player?" autofocus
             onkeydown="if(event.key==='Enter'){document.getElementById('revealed').value==='true'?nextPlayer():submitGuess()}">
      <button id="btnGuess" class="btn btn-guess" onclick="submitGuess()">Guess</button>
      <button id="btnHint" class="btn btn-hint" onclick="getHint()">&#128161; Hint</button>
      <button id="btnGiveUp" class="btn btn-giveup" onclick="giveUp()">Give Up</button>
      <button id="btnNext" class="btn btn-next" onclick="nextPlayer()" style="display:none">Next Player &rarr;</button>
    </div>
    <input type="hidden" id="revealed" value="false">

    <div id="guessesArea" class="guesses"></div>
    <div class="footer-info" id="footerInfo"></div>
  </div>

  <script>
    let filtersVisible = false;

    function toggleFilters() {
      filtersVisible = !filtersVisible;
      document.getElementById("filterPanel").style.display = filtersVisible ? "flex" : "none";
    }

    function updateUI(data) {
      document.getElementById("score").textContent = data.score_correct + "/" + data.score_total;
      const streakEl = document.getElementById("streak");
      streakEl.textContent = data.streak;
      streakEl.className = data.streak > 0 ? "streak-active" : "";
      document.getElementById("best").textContent = data.best_streak;

      const nameEl = document.getElementById("playerName");
      const input = document.getElementById("guessInput");
      const revHidden = document.getElementById("revealed");

      if (data.revealed) {
        nameEl.textContent = data.player_name;
        nameEl.className = "player-name revealed";
        input.className = "guess-input disabled";
        input.disabled = true;
        input.placeholder = "Press Enter for next player...";
        revHidden.value = "true";
        document.getElementById("btnGuess").style.display = "none";
        document.getElementById("btnHint").style.display = "none";
        document.getElementById("btnGiveUp").style.display = "none";
        document.getElementById("btnNext").style.display = "";
        document.getElementById("hintText").textContent = "";
        if (data.last_correct) {
          document.getElementById("resultBadge").innerHTML = '<span class="correct-badge">&#10003; You got it!</span>';
        } else {
          document.getElementById("resultBadge").innerHTML = '<span class="revealed-badge">Answer revealed</span>';
        }
      } else {
        nameEl.textContent = "??? ???";
        nameEl.className = "player-name hidden";
        input.className = "guess-input";
        input.disabled = false;
        input.placeholder = "Who is this player?";
        input.value = "";
        input.focus();
        revHidden.value = "false";
        document.getElementById("btnGuess").style.display = "";
        document.getElementById("btnHint").style.display = "";
        document.getElementById("btnGiveUp").style.display = "";
        document.getElementById("btnNext").style.display = "none";
        document.getElementById("resultBadge").innerHTML = "";
      }

      if (data.hint_text) {
        document.getElementById("hintText").textContent = "Hint: " + data.hint_text;
      }

      const guessesArea = document.getElementById("guessesArea");
      guessesArea.innerHTML = "";
      (data.guesses || []).forEach(g => {
        const span = document.createElement("span");
        span.className = "guess-tag " + (g.correct ? "guess-correct" : "guess-wrong");
        span.textContent = (g.correct ? "\\u2713 " : "\\u2717 ") + g.text;
        guessesArea.appendChild(span);
      });

      document.getElementById("statsImg").src = "/stats_image?t=" + Date.now();

      // Pool count
      const poolText = "Player pool: " + (data.pool_size || "?") + " players";
      document.getElementById("footerInfo").textContent = poolText;
      document.getElementById("poolCount").textContent = poolText;

      // Update hint button
      const hintBtn = document.getElementById("btnHint");
      if (data.hints_given > 0) {
        hintBtn.innerHTML = "&#128161; Hint (" + data.hints_given + "/3)";
      } else {
        hintBtn.innerHTML = "&#128161; Hint";
      }
      hintBtn.disabled = data.hints_given >= 3;

      // Sync filter inputs with server state
      if (data.filters) {
        document.getElementById("fMinYears").value = data.filters.min_years || 5;
        document.getElementById("fMinPA").value = data.filters.min_pa || 1500;
        document.getElementById("fPlayedStart").value = data.filters.played_in_start || "";
        document.getElementById("fPlayedEnd").value = data.filters.played_in_end || "";
      }
    }

    async function submitGuess() {
      const input = document.getElementById("guessInput");
      const guess = input.value.trim();
      if (!guess) return;
      const resp = await fetch("/guess", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({guess: guess}),
      });
      updateUI(await resp.json());
    }

    async function getHint() {
      const resp = await fetch("/hint", {method: "POST"});
      updateUI(await resp.json());
    }

    async function giveUp() {
      const resp = await fetch("/giveup", {method: "POST"});
      updateUI(await resp.json());
    }

    async function nextPlayer() {
      const resp = await fetch("/next", {method: "POST"});
      updateUI(await resp.json());
    }

    async function applyFilters() {
      const body = {
        min_years: parseInt(document.getElementById("fMinYears").value) || 5,
        min_pa: parseInt(document.getElementById("fMinPA").value) || 1500,
        played_in_start: parseInt(document.getElementById("fPlayedStart").value) || null,
        played_in_end: parseInt(document.getElementById("fPlayedEnd").value) || null,
      };
      const resp = await fetch("/apply_filters", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(body),
      });
      updateUI(await resp.json());
    }

    function resetFilters() {
      document.getElementById("fMinYears").value = 5;
      document.getElementById("fMinPA").value = 1500;
      document.getElementById("fPlayedStart").value = "";
      document.getElementById("fPlayedEnd").value = "";
      applyFilters();
    }

    // Load initial state
    fetch("/state").then(r => r.json()).then(updateUI);
  </script>
</body>
</html>
"""


def get_state_dict():
    return {
        "score_correct": STATE["score_correct"],
        "score_total": STATE["score_total"],
        "streak": STATE["streak"],
        "best_streak": STATE["best_streak"],
        "revealed": STATE["revealed"],
        "player_name": STATE["current_name"] if STATE["revealed"] else "??? ???",
        "guesses": STATE["guesses"],
        "hints_given": STATE["hints_given"],
        "hint_text": STATE.get("hint_text", ""),
        "last_correct": STATE.get("last_correct", False),
        "pool_size": len(STATE["player_ids"]),
        "filters": STATE["filters"],
    }


def rebuild_pool():
    """Rebuild the player pool from current filters and pick a new player."""
    f = STATE["filters"]
    played_in = None
    if f.get("played_in_start") and f.get("played_in_end"):
        played_in = (f["played_in_start"], f["played_in_end"])
    elif f.get("played_in_start"):
        played_in = (f["played_in_start"], 2025)
    elif f.get("played_in_end"):
        played_in = (1871, f["played_in_end"])

    pool = get_player_pool(
        STATE["batting"], STATE["people"],
        min_years=f.get("min_years", 5),
        min_pa=f.get("min_pa", 1500),
        played_in=played_in,
    )
    STATE["player_ids"] = pool["playerID"].tolist()
    random.shuffle(STATE["player_ids"])
    STATE["current_idx"] = 0
    print(f"  Filter applied — pool: {len(STATE['player_ids'])} players")


def load_next_player():
    """Load the next player and generate their stats image."""
    if STATE["current_idx"] >= len(STATE["player_ids"]):
        random.shuffle(STATE["player_ids"])
        STATE["current_idx"] = 0

    pid = STATE["player_ids"][STATE["current_idx"]]
    name, seasons = get_player_seasons(
        STATE["batting"], STATE["people"],
        STATE["awards_df"], STATE["allstar_df"], pid,
        STATE["appearances_df"], STATE["awards_share_df"]
    )

    # Filter out 0 AB seasons
    seasons = [s for s in seasons if s["AB"] > 0]

    if len(seasons) == 0:
        STATE["current_idx"] += 1
        return load_next_player()

    STATE["current_name"] = name
    STATE["current_seasons"] = seasons
    STATE["guesses"] = []
    STATE["hints_given"] = 0
    STATE["hint_text"] = ""
    STATE["revealed"] = False
    STATE["last_correct"] = False

    img_path = os.path.join(STATE["output_dir"], "current_player.png")
    render_stats_image(seasons, img_path, show_name=None)


@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/stats_image")
def stats_image():
    img_path = os.path.join(STATE["output_dir"], "current_player.png")
    if os.path.exists(img_path):
        return send_file(img_path, mimetype="image/png")
    return "No image", 404


@app.route("/state")
def get_state():
    return jsonify(get_state_dict())


@app.route("/guess", methods=["POST"])
def guess():
    if STATE["revealed"]:
        return jsonify(get_state_dict())

    data = request.json
    guess_text = data.get("guess", "").strip()
    if not guess_text:
        return jsonify(get_state_dict())

    def normalize(s):
        return "".join(c for c in s.lower() if c.isalpha())

    correct = normalize(guess_text) == normalize(STATE["current_name"])
    STATE["guesses"].append({"text": guess_text, "correct": correct})

    if correct:
        STATE["revealed"] = True
        STATE["last_correct"] = True
        STATE["score_correct"] += 1
        STATE["score_total"] += 1
        STATE["streak"] += 1
        STATE["best_streak"] = max(STATE["best_streak"], STATE["streak"])

        img_path = os.path.join(STATE["output_dir"], "current_player.png")
        render_stats_image(STATE["current_seasons"], img_path, show_name=STATE["current_name"])

    return jsonify(get_state_dict())


@app.route("/hint", methods=["POST"])
def hint():
    if STATE["revealed"]:
        return jsonify(get_state_dict())

    STATE["hints_given"] += 1
    name_parts = STATE["current_name"].split()

    if STATE["hints_given"] == 1:
        STATE["hint_text"] = " ".join(p[0] + "." for p in name_parts)
    elif STATE["hints_given"] == 2:
        STATE["hint_text"] = name_parts[0] + " " + " ".join(p[0] + "." for p in name_parts[1:])
    elif STATE["hints_given"] >= 3:
        STATE["hint_text"] = name_parts[0] + " " + " ".join(
            p[:max(2, len(p)//2)] + "\u2026" for p in name_parts[1:]
        )

    return jsonify(get_state_dict())


@app.route("/giveup", methods=["POST"])
def giveup():
    if STATE["revealed"]:
        return jsonify(get_state_dict())

    STATE["revealed"] = True
    STATE["last_correct"] = False
    STATE["score_total"] += 1
    STATE["streak"] = 0

    img_path = os.path.join(STATE["output_dir"], "current_player.png")
    render_stats_image(STATE["current_seasons"], img_path, show_name=STATE["current_name"])

    return jsonify(get_state_dict())


@app.route("/next", methods=["POST"])
def next_player():
    STATE["current_idx"] += 1
    load_next_player()
    return jsonify(get_state_dict())


@app.route("/apply_filters", methods=["POST"])
def apply_filters():
    """Apply new filters from the UI, rebuild pool, reset score, load new player."""
    data = request.json
    STATE["filters"] = {
        "min_years": data.get("min_years", 5),
        "min_pa": data.get("min_pa", 1500),
        "played_in_start": data.get("played_in_start"),
        "played_in_end": data.get("played_in_end"),
    }

    rebuild_pool()

    if len(STATE["player_ids"]) == 0:
        # No players match — revert to defaults
        STATE["filters"] = {"min_years": 5, "min_pa": 1500, "played_in_start": None, "played_in_end": None}
        rebuild_pool()

    # Reset score on filter change
    STATE["score_correct"] = 0
    STATE["score_total"] = 0
    STATE["streak"] = 0

    load_next_player()
    return jsonify(get_state_dict())


def main():
    parser = argparse.ArgumentParser(description="Name That Ballplayer — Web version")
    parser.add_argument("--data-dir", required=True, help="Path to Lahman CSV folder")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    print("Loading Lahman database...")
    STATE["batting"], STATE["people"], STATE["awards_df"], STATE["allstar_df"], STATE["appearances_df"], STATE["awards_share_df"] = load_data(args.data_dir)

    STATE["output_dir"] = args.output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(STATE["output_dir"], exist_ok=True)

    rebuild_pool()
    load_next_player()

    print(f"\n  Open http://localhost:{args.port} in your browser!")
    print(f"  Press Ctrl+C to quit.\n")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
