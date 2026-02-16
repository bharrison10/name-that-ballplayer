#!/usr/bin/env python3
"""
Name That Ballplayer — Lightweight session fix for Render free tier.

Key fix: Store only player ID in session, not entire game state.
Generate everything else on-demand to minimize memory.
"""

import argparse
import os
import random
import sys
import hashlib

import pandas as pd
from flask import Flask, render_template_string, jsonify, request, send_file, session

from game import (
    load_data, get_player_pool,
    get_player_seasons_batting, get_player_seasons_pitching,
    render_stats_image_batting, render_stats_image_pitching,
)

app = Flask(__name__)
# Use deterministic secret key from environment or generate one
app.secret_key = os.environ.get('SECRET_KEY', 'name-that-ballplayer-secret-2026')

# Global shared data (read-only, loaded once)
GLOBAL = {
    "batting": None,
    "pitching": None,
    "people": None,
    "awards_df": None,
    "allstar_df": None,
    "appearances_df": None,
    "awards_share_df": None,
    "pool_batting": [],
    "pool_pitching": [],
    "output_dir": "./output",
}


def get_session_key(key, default=None):
    """Safely get session value."""
    return session.get(key, default)


def set_session_key(key, value):
    """Safely set session value."""
    session[key] = value
    session.modified = True


def init_session():
    """Initialize minimal session state."""
    if 'player_idx' not in session:
        set_session_key('player_idx', 0)
        set_session_key('mode', 'batting')
        set_session_key('score_correct', 0)
        set_session_key('score_total', 0)
        set_session_key('streak', 0)
        set_session_key('best_streak', 0)
        set_session_key('hints_given', 0)
        set_session_key('revealed', False)
        set_session_key('session_hash', hashlib.md5(os.urandom(16)).hexdigest()[:8])


def get_current_player():
    """Get current player info from session."""
    init_session()
    idx = get_session_key('player_idx', 0)
    mode = get_session_key('mode', 'batting')
    
    pool = GLOBAL['pool_batting'] if mode == 'batting' else GLOBAL['pool_pitching']
    
    if idx >= len(pool):
        idx = 0
        set_session_key('player_idx', 0)
    
    return pool[idx] if pool else None


def get_image_filename():
    """Get unique image filename for this session."""
    session_hash = get_session_key('session_hash', 'default')
    return f"player_{session_hash}.png"


# Minimal HTML
HTML = """<!DOCTYPE html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>⚾ Name That Ballplayer</title><style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:Arial,sans-serif;background:linear-gradient(135deg,#1a472a,#2d5a3d);color:#1a1a1a;min-height:100vh}.topbar{background:#8C1515;padding:16px 24px;box-shadow:0 4px 12px rgba(0,0,0,0.3)}.topbar-content{max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px}.topbar h1{color:#fff;font-size:24px}.scoreboard{display:flex;gap:24px;color:#fff;font-size:14px}.scoreboard .score-value{font-size:20px;font-weight:700}.container{max-width:1200px;margin:0 auto;padding:24px 16px}.main-card{background:#fff;border-radius:12px;padding:24px;box-shadow:0 8px 32px rgba(0,0,0,0.2)}.player-name{font-size:28px;font-weight:700;margin-bottom:16px}.player-name.hidden{color:#bbb}.player-name.revealed{color:#00457c}.stats-img{width:100%;border:1px solid #ddd;border-radius:8px;margin:16px 0}.guess-area{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.guess-input{flex:1;min-width:200px;padding:12px;font-size:16px;border:2px solid #8C1515;border-radius:6px}.guess-input.disabled{background:#f0f0f0;border-color:#ccc}.btn{padding:12px 24px;font-size:14px;font-weight:700;border:none;border-radius:6px;cursor:pointer;color:#fff}.btn-guess{background:#8C1515}.btn-hint{background:#555}.btn-giveup{background:#c00}.btn-next{background:#2d6b2d}.btn:disabled{opacity:0.5;cursor:not-allowed}.guesses{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}.guess-tag{padding:4px 12px;border-radius:16px;font-size:12px}.guess-correct{background:#d4edda;color:#155724}.guess-wrong{background:#f8d7da;color:#721c24}.footer{margin-top:16px;font-size:11px;color:#fff;text-align:center;opacity:0.7}</style></head><body><div class="topbar"><div class="topbar-content"><div><h1>⚾ Name That Ballplayer</h1></div><div class="scoreboard"><div>Score: <span class="score-value" id="score">0/0</span></div><div>Streak: <span class="score-value" id="streak">0</span></div><div>Best: <span class="score-value" id="best">0</span></div></div></div></div><div class="container"><div class="main-card"><div id="playerName" class="player-name hidden">??? ???</div><div id="hintText" style="color:#00457c;font-size:18px;margin:8px 0"></div><img id="statsImg" class="stats-img" src="" alt="Loading..."><div class="guess-area"><input id="guessInput" class="guess-input" type="text" placeholder="Who is this player?" autofocus onkeydown="if(event.key==='Enter')submitGuess()"><button class="btn btn-guess" onclick="submitGuess()">Guess</button><button class="btn btn-hint" onclick="getHint()">Hint</button><button class="btn btn-giveup" onclick="giveUp()">Give Up</button><button id="btnNext" class="btn btn-next" onclick="nextPlayer()" style="display:none">Next →</button></div><div id="guessesArea" class="guesses"></div></div><div class="footer">Lightweight • Session-based</div></div><script>function updateUI(d){document.getElementById("score").textContent=d.score_correct+"/"+d.score_total;document.getElementById("streak").textContent=d.streak;document.getElementById("best").textContent=d.best_streak;const n=document.getElementById("playerName");if(d.revealed){n.textContent=d.player_name;n.className="player-name revealed"}else{n.textContent="??? ???";n.className="player-name hidden"}document.getElementById("hintText").textContent=d.hint_text||"";const inp=document.getElementById("guessInput");const btnNext=document.getElementById("btnNext");if(d.revealed){inp.disabled=true;inp.className="guess-input disabled";btnNext.style.display="inline-block"}else{inp.disabled=false;inp.className="guess-input";inp.value="";inp.focus();btnNext.style.display="none"}const ga=document.getElementById("guessesArea");ga.innerHTML="";if(d.guesses){d.guesses.forEach(g=>{const t=document.createElement("span");t.className=g.correct?"guess-tag guess-correct":"guess-tag guess-wrong";t.textContent=g.text;ga.appendChild(t)})}document.getElementById("statsImg").src="/stats_image?"+Date.now()}async function submitGuess(){const g=document.getElementById("guessInput").value.trim();if(!g)return;const r=await fetch("/guess",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({guess:g})});updateUI(await r.json())}async function getHint(){const r=await fetch("/hint",{method:"POST"});updateUI(await r.json())}async function giveUp(){const r=await fetch("/giveup",{method:"POST"});updateUI(await r.json())}async function nextPlayer(){const r=await fetch("/next",{method:"POST"});updateUI(await r.json())}fetch("/state").then(r=>r.json()).then(updateUI)</script></body></html>"""


@app.route("/")
def index():
    init_session()
    return render_template_string(HTML)


@app.route("/stats_image")
def stats_image():
    img_path = os.path.join(GLOBAL["output_dir"], get_image_filename())
    if os.path.exists(img_path):
        return send_file(img_path, mimetype="image/png")
    return "No image", 404


@app.route("/state")
def get_state():
    init_session()
    player = get_current_player()
    
    return jsonify({
        "score_correct": get_session_key('score_correct', 0),
        "score_total": get_session_key('score_total', 0),
        "streak": get_session_key('streak', 0),
        "best_streak": get_session_key('best_streak', 0),
        "revealed": get_session_key('revealed', False),
        "player_name": player if get_session_key('revealed') else "??? ???",
        "guesses": get_session_key('guesses', []),
        "hint_text": get_session_key('hint_text', ""),
    })


@app.route("/guess", methods=["POST"])
def guess():
    init_session()
    if get_session_key('revealed'):
        return get_state()

    data = request.json
    guess_text = data.get("guess", "").strip()
    if not guess_text:
        return get_state()

    player = get_current_player()
    
    def normalize(s):
        return "".join(c for c in s.lower() if c.isalpha())

    correct = normalize(guess_text) == normalize(player)
    guesses = get_session_key('guesses', [])
    guesses.append({"text": guess_text, "correct": correct})
    set_session_key('guesses', guesses)

    if correct:
        set_session_key('revealed', True)
        set_session_key('score_correct', get_session_key('score_correct', 0) + 1)
        set_session_key('score_total', get_session_key('score_total', 0) + 1)
        set_session_key('streak', get_session_key('streak', 0) + 1)
        set_session_key('best_streak', max(get_session_key('best_streak', 0), get_session_key('streak', 0)))

        # Re-render with name
        idx = get_session_key('player_idx', 0)
        mode = get_session_key('mode', 'batting')
        pool = GLOBAL['pool_batting'] if mode == 'batting' else GLOBAL['pool_pitching']
        pid = GLOBAL['pool_batting' if mode == 'batting' else 'pool_pitching'][idx]
        
        if mode == 'batting':
            name, seasons = get_player_seasons_batting(
                GLOBAL["batting"], GLOBAL["people"], GLOBAL["awards_df"],
                GLOBAL["allstar_df"], pid, GLOBAL["appearances_df"], GLOBAL["awards_share_df"]
            )
            img_path = os.path.join(GLOBAL["output_dir"], get_image_filename())
            render_stats_image_batting(seasons, img_path, show_name=name)

    return get_state()


@app.route("/hint", methods=["POST"])
def hint():
    init_session()
    if get_session_key('revealed'):
        return get_state()

    hints_given = get_session_key('hints_given', 0) + 1
    set_session_key('hints_given', hints_given)
    
    player = get_current_player()
    parts = player.split()

    if hints_given == 1:
        hint_text = " ".join(p[0] + "." for p in parts)
    elif hints_given == 2:
        hint_text = parts[0] + " " + " ".join(p[0] + "." for p in parts[1:])
    else:
        hint_text = parts[0] + " " + " ".join(p[:2] + "…" for p in parts[1:])
    
    set_session_key('hint_text', hint_text)
    return get_state()


@app.route("/giveup", methods=["POST"])
def giveup():
    init_session()
    if get_session_key('revealed'):
        return get_state()

    set_session_key('revealed', True)
    set_session_key('score_total', get_session_key('score_total', 0) + 1)
    set_session_key('streak', 0)

    # Re-render with name
    idx = get_session_key('player_idx', 0)
    mode = get_session_key('mode', 'batting')
    pid = GLOBAL['pool_batting' if mode == 'batting' else 'pool_pitching'][idx]
    
    if mode == 'batting':
        name, seasons = get_player_seasons_batting(
            GLOBAL["batting"], GLOBAL["people"], GLOBAL["awards_df"],
            GLOBAL["allstar_df"], pid, GLOBAL["appearances_df"], GLOBAL["awards_share_df"]
        )
        img_path = os.path.join(GLOBAL["output_dir"], get_image_filename())
        render_stats_image_batting(seasons, img_path, show_name=name)

    return get_state()


@app.route("/next", methods=["POST"])
def next_player():
    init_session()
    
    # Move to next player
    idx = get_session_key('player_idx', 0) + 1
    mode = get_session_key('mode', 'batting')
    pool = GLOBAL['pool_batting'] if mode == 'batting' else GLOBAL['pool_pitching']
    
    if idx >= len(pool):
        idx = 0
    
    set_session_key('player_idx', idx)
    set_session_key('revealed', False)
    set_session_key('guesses', [])
    set_session_key('hints_given', 0)
    set_session_key('hint_text', "")
    
    # Generate new player image
    pid = pool[idx]
    if mode == 'batting':
        name, seasons = get_player_seasons_batting(
            GLOBAL["batting"], GLOBAL["people"], GLOBAL["awards_df"],
            GLOBAL["allstar_df"], pid, GLOBAL["appearances_df"], GLOBAL["awards_share_df"]
        )
        img_path = os.path.join(GLOBAL["output_dir"], get_image_filename())
        render_stats_image_batting(seasons, img_path, show_name=None)
    
    return get_state()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    print("Loading Lahman database...")
    GLOBAL["batting"], GLOBAL["pitching"], GLOBAL["people"], \
    GLOBAL["awards_df"], GLOBAL["allstar_df"], GLOBAL["appearances_df"], \
    GLOBAL["awards_share_df"] = load_data(args.data_dir)

    GLOBAL["output_dir"] = args.output_dir or "./output"
    os.makedirs(GLOBAL["output_dir"], exist_ok=True)

    # Build player pools once at startup
    print("Building player pools...")
    pool = get_player_pool(
        GLOBAL["batting"], GLOBAL["pitching"], GLOBAL["people"],
        mode="batting", min_years=5, min_pa=1500, min_ip=1000
    )
    GLOBAL["pool_batting"] = pool["playerID"].tolist()
    random.shuffle(GLOBAL["pool_batting"])
    
    # Generate first player image
    pid = GLOBAL["pool_batting"][0]
    name, seasons = get_player_seasons_batting(
        GLOBAL["batting"], GLOBAL["people"], GLOBAL["awards_df"],
        GLOBAL["allstar_df"], pid, GLOBAL["appearances_df"], GLOBAL["awards_share_df"]
    )
    render_stats_image_batting(seasons, os.path.join(GLOBAL["output_dir"], "player_default.png"), show_name=None)

    port = args.port or int(os.environ.get("PORT", 5050))
    print(f"\n🎯 Starting on port {port}\n")
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
