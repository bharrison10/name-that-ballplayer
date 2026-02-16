#!/usr/bin/env python3
"""
Name That Ballplayer — Web version with BATTING and PITCHING support.

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
    load_data, get_player_pool,
    get_player_seasons_batting, get_player_seasons_pitching,
    render_stats_image_batting, render_stats_image_pitching,
    compute_totals_batting, compute_totals_pitching,
)

app = Flask(__name__)

STATE = {
    "batting": None,
    "pitching": None,
    "people": None,
    "awards_df": None,
    "allstar_df": None,
    "appearances_df": None,
    "awards_share_df": None,
    "player_ids": [],
    "current_idx": 0,
    "current_name": None,
    "current_seasons": None,
    "current_type": None,  # "batting" or "pitching"
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
        "mode": "batting",
        "min_years": 5,
        "min_pa": 1500,
        "min_ip": 1000,
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
  <title>⚾ Name That Ballplayer</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { 
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; 
      background: linear-gradient(135deg, #1a472a 0%, #2d5a3d 50%, #1a472a 100%);
      color: #1a1a1a; 
      min-height: 100vh;
    }

    .topbar {
      background: linear-gradient(to right, #8C1515 0%, #a52020 100%);
      padding: 16px 24px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      border-bottom: 3px solid #5a0f0f;
    }
    
    .topbar-content {
      max-width: 1200px;
      margin: 0 auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    
    .topbar h1 { 
      color: #fff; 
      font-family: Georgia, 'Times New Roman', serif; 
      font-size: 28px;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
      letter-spacing: -0.5px;
    }
    
    .topbar .subtitle { 
      color: #ffd6d6; 
      font-size: 12px; 
      font-weight: 300;
      margin-top: 2px;
    }
    
    .scoreboard { 
      display: flex; 
      gap: 28px; 
      color: #fff; 
      font-size: 14px;
      font-weight: 300;
    }
    
    .scoreboard .score-item {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 2px;
    }
    
    .scoreboard .score-label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      opacity: 0.8;
    }
    
    .scoreboard .score-value { 
      font-size: 22px;
      font-weight: 700;
      font-family: 'Courier New', monospace;
    }
    
    .streak-active { 
      color: #90ee90 !important; 
      text-shadow: 0 0 8px rgba(144, 238, 144, 0.5);
    }
    
    .best-val { 
      color: #ffd700 !important;
      text-shadow: 0 0 8px rgba(255, 215, 0, 0.5);
    }

    .container { 
      max-width: 1200px; 
      margin: 0 auto; 
      padding: 24px 16px; 
    }

    /* Filter panel */
    .filter-toggle {
      background: rgba(255,255,255,0.95);
      border: 2px solid #ddd;
      border-radius: 8px;
      padding: 10px 20px;
      cursor: pointer;
      font-size: 13px;
      font-weight: 600;
      color: #555;
      margin-bottom: 16px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.1);
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    
    .filter-toggle:hover { 
      background: #fff;
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }

    .filter-bar {
      background: rgba(255,255,255,0.97);
      border: 2px solid #ddd;
      border-radius: 12px;
      padding: 20px 24px;
      margin-bottom: 20px;
      box-shadow: 0 4px 16px rgba(0,0,0,0.15);
      display: flex;
      align-items: center;
      gap: 20px;
      flex-wrap: wrap;
      font-size: 13px;
    }
    
    .filter-bar label { 
      font-weight: 700; 
      color: #333; 
      white-space: nowrap;
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: 0.5px;
    }
    
    .filter-bar input[type="number"],
    .filter-bar select {
      padding: 8px 12px;
      border: 2px solid #ccc;
      border-radius: 6px;
      font-size: 14px;
      text-align: center;
      transition: border-color 0.2s;
      font-family: 'Courier New', monospace;
      font-weight: 600;
    }
    
    .filter-bar input[type="number"] {
      width: 80px;
    }
    
    .filter-bar select {
      width: 120px;
      text-align: left;
    }
    
    .filter-bar input:focus,
    .filter-bar select:focus {
      outline: none;
      border-color: #8C1515;
    }
    
    .filter-bar .filter-group { 
      display: flex; 
      align-items: center; 
      gap: 8px;
      background: rgba(140, 21, 21, 0.05);
      padding: 8px 12px;
      border-radius: 8px;
    }
    
    .filter-bar .sep { 
      color: #ccc; 
      font-size: 20px; 
      margin: 0 4px;
    }
    
    .filter-bar .btn-apply {
      padding: 10px 24px;
      background: linear-gradient(135deg, #8C1515 0%, #a52020 100%);
      color: #fff;
      border: none;
      border-radius: 8px;
      font-weight: 700;
      cursor: pointer;
      font-size: 13px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      box-shadow: 0 2px 8px rgba(140, 21, 21, 0.3);
      transition: all 0.2s;
    }
    
    .filter-bar .btn-apply:hover { 
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(140, 21, 21, 0.4);
    }
    
    .filter-bar .btn-reset {
      padding: 10px 20px;
      background: #f5f5f5;
      color: #666;
      border: 2px solid #ddd;
      border-radius: 8px;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
      transition: all 0.2s;
    }
    
    .filter-bar .btn-reset:hover {
      background: #fff;
      border-color: #999;
    }
    
    .filter-bar .pool-count {
      margin-left: auto;
      color: #666;
      font-size: 12px;
      white-space: nowrap;
      padding: 6px 14px;
      background: rgba(140, 21, 21, 0.08);
      border-radius: 20px;
      font-weight: 600;
    }

    .main-card {
      background: rgba(255,255,255,0.97);
      border-radius: 16px;
      padding: 28px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.2);
      backdrop-filter: blur(10px);
    }

    .player-name-area {
      padding: 16px 0;
      border-bottom: 3px solid #e0e0e0;
      margin-bottom: 20px;
      display: flex;
      align-items: baseline;
      gap: 16px;
      flex-wrap: wrap;
    }
    
    .player-name { 
      font-family: Georgia, 'Times New Roman', serif; 
      font-size: 32px; 
      font-weight: 700;
      letter-spacing: -0.5px;
    }
    
    .player-name.hidden { 
      color: #bbb;
      text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    .player-name.revealed { 
      color: #00457c;
      animation: revealPulse 0.5s ease-out;
    }
    
    @keyframes revealPulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.05); }
    }
    
    .hint-text { 
      font-family: Georgia, serif; 
      font-size: 22px; 
      color: #00457c; 
      letter-spacing: 3px;
      font-weight: 500;
    }
    
    .correct-badge { 
      color: #2d8a2d; 
      font-size: 16px; 
      font-weight: 700;
      padding: 6px 14px;
      background: rgba(45, 138, 45, 0.1);
      border-radius: 20px;
      animation: badgePop 0.3s ease-out;
    }
    
    .revealed-badge { 
      color: #cc0000; 
      font-size: 16px;
      font-weight: 700;
      padding: 6px 14px;
      background: rgba(204, 0, 0, 0.1);
      border-radius: 20px;
    }
    
    @keyframes badgePop {
      0% { transform: scale(0.8); opacity: 0; }
      100% { transform: scale(1); opacity: 1; }
    }

    .stats-img-container {
      background: #fff;
      border: 2px solid #e0e0e0;
      border-radius: 12px;
      overflow: hidden;
      margin-bottom: 20px;
      box-shadow: inset 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .stats-img-container img { 
      display: block; 
      max-width: 100%; 
      height: auto;
      transition: opacity 0.3s;
    }

    .guess-area {
      background: linear-gradient(135deg, #f8f9fa 0%, #ffffff 100%);
      border: 2px solid #e0e0e0;
      border-radius: 12px;
      padding: 20px;
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .guess-input {
      flex: 1;
      min-width: 200px;
      padding: 14px 18px;
      font-size: 16px;
      font-family: Georgia, serif;
      border: 3px solid #8C1515;
      border-radius: 8px;
      outline: none;
      transition: all 0.2s;
    }
    
    .guess-input:focus {
      border-color: #a52020;
      box-shadow: 0 0 0 4px rgba(140, 21, 21, 0.1);
    }
    
    .guess-input.disabled { 
      background: #f5f5f5; 
      border-color: #ccc;
      cursor: not-allowed;
    }

    .btn {
      padding: 14px 28px;
      font-size: 14px;
      font-weight: 700;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      color: #fff;
      transition: all 0.2s;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    }
    
    .btn:hover:not(:disabled) {
      transform: translateY(-2px);
      box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    }
    
    .btn:active:not(:disabled) {
      transform: translateY(0);
    }
    
    .btn-guess { 
      background: linear-gradient(135deg, #8C1515 0%, #a52020 100%);
    }
    
    .btn-hint { 
      background: linear-gradient(135deg, #555 0%, #666 100%);
    }
    
    .btn-giveup { 
      background: linear-gradient(135deg, #cc0000 0%, #dd1111 100%);
    }
    
    .btn-next { 
      background: linear-gradient(135deg, #2d6b2d 0%, #3a8a3a 100%);
    }
    
    .btn:disabled { 
      opacity: 0.4; 
      cursor: not-allowed;
      transform: none !important;
    }

    .guesses { 
      margin-top: 16px; 
      display: flex; 
      flex-wrap: wrap; 
      gap: 10px;
    }
    
    .guess-tag { 
      padding: 6px 16px; 
      border-radius: 20px; 
      font-size: 13px;
      font-weight: 600;
      animation: tagSlideIn 0.3s ease-out;
    }
    
    @keyframes tagSlideIn {
      from { opacity: 0; transform: translateX(-10px); }
      to { opacity: 1; transform: translateX(0); }
    }
    
    .guess-correct { 
      background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
      color: #155724; 
      border: 2px solid #b1dfbb;
      box-shadow: 0 2px 4px rgba(21, 87, 36, 0.1);
    }
    
    .guess-wrong { 
      background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
      color: #721c24; 
      border: 2px solid #f1b0b7;
      box-shadow: 0 2px 4px rgba(114, 28, 36, 0.1);
    }

    .footer-info { 
      margin-top: 20px; 
      font-size: 11px; 
      color: rgba(255,255,255,0.6); 
      text-align: center;
      font-weight: 300;
      letter-spacing: 0.5px;
    }
    
    .mode-badge {
      display: inline-block;
      padding: 4px 12px;
      background: rgba(255,255,255,0.15);
      border-radius: 12px;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-left: 12px;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-content">
      <div>
        <h1>⚾ Name That Ballplayer</h1>
        <div class="subtitle">Guess the player from their career stats</div>
      </div>
      <div class="scoreboard">
        <div class="score-item">
          <div class="score-label">Score</div>
          <div class="score-value" id="score">0/0</div>
        </div>
        <div class="score-item">
          <div class="score-label">Streak</div>
          <div class="score-value" id="streak">0</div>
        </div>
        <div class="score-item">
          <div class="score-label">Best</div>
          <div class="score-value best-val" id="best">0</div>
        </div>
      </div>
    </div>
  </div>

  <div class="container">

    <!-- Filter toggle -->
    <button class="filter-toggle" onclick="toggleFilters()">⚙️ Filters & Mode</button>

    <!-- Filter panel (hidden by default) -->
    <div id="filterPanel" class="filter-bar" style="display:none;">
      <div class="filter-group">
        <label>Game Mode:</label>
        <select id="fMode">
          <option value="batting">Batting</option>
          <option value="pitching">Pitching</option>
          <option value="both">Both</option>
        </select>
      </div>
      <div class="sep">|</div>
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
        <label>Min IP:</label>
        <input type="number" id="fMinIP" value="1000" min="0" max="5000" step="100">
      </div>
      <div class="sep">|</div>
      <div class="filter-group">
        <label>Played in:</label>
        <input type="number" id="fPlayedStart" placeholder="e.g. 2000" min="1871" max="2025" style="width:90px;">
        <span>–</span>
        <input type="number" id="fPlayedEnd" placeholder="e.g. 2025" min="1871" max="2025" style="width:90px;">
      </div>
      <button class="btn-apply" onclick="applyFilters()">Apply & New Game</button>
      <button class="btn-reset" onclick="resetFilters()">Reset</button>
      <div class="pool-count" id="poolCount"></div>
    </div>

    <div class="main-card">
      <div class="player-name-area">
        <div id="playerName" class="player-name hidden">??? ???</div>
        <div id="hintText" class="hint-text"></div>
        <div id="resultBadge"></div>
        <span id="modeBadge" class="mode-badge"></span>
      </div>

      <div class="stats-img-container">
        <img id="statsImg" src="" alt="Loading stats...">
      </div>

      <div class="guess-area">
        <input id="guessInput" class="guess-input" type="text"
               placeholder="Who is this player?" autofocus
               onkeydown="if(event.key==='Enter'){document.getElementById('revealed').value==='true'?nextPlayer():submitGuess()}">
        <button id="btnGuess" class="btn btn-guess" onclick="submitGuess()">Guess</button>
        <button id="btnHint" class="btn btn-hint" onclick="getHint()">💡 Hint</button>
        <button id="btnGiveUp" class="btn btn-giveup" onclick="giveUp()">Give Up</button>
        <button id="btnNext" class="btn btn-next" onclick="nextPlayer()" style="display:none">Next Player →</button>
      </div>
      <input type="hidden" id="revealed" value="false">

      <div id="guessesArea" class="guesses"></div>
    </div>
    
    <div class="footer-info" id="footerInfo">Enhanced with Batting & Pitching Support</div>
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
      if (data.streak > 0) {
        streakEl.classList.add("streak-active");
      } else {
        streakEl.classList.remove("streak-active");
      }
      document.getElementById("best").textContent = data.best_streak;

      const nameEl = document.getElementById("playerName");
      if (data.revealed) {
        nameEl.textContent = data.player_name;
        nameEl.classList.remove("hidden");
        nameEl.classList.add("revealed");
      } else {
        nameEl.textContent = "??? ???";
        nameEl.classList.add("hidden");
        nameEl.classList.remove("revealed");
      }

      document.getElementById("hintText").textContent = data.hint_text || "";

      const badgeEl = document.getElementById("resultBadge");
      if (data.revealed) {
        if (data.last_correct) {
          badgeEl.textContent = "✅ Correct!";
          badgeEl.className = "correct-badge";
        } else {
          badgeEl.textContent = "❌ Gave Up";
          badgeEl.className = "revealed-badge";
        }
      } else {
        badgeEl.textContent = "";
        badgeEl.className = "";
      }

      // Update mode badge
      const modeBadge = document.getElementById("modeBadge");
      if (data.current_type) {
        modeBadge.textContent = data.current_type;
        modeBadge.style.display = "inline-block";
      } else {
        modeBadge.style.display = "none";
      }

      const guessInput = document.getElementById("guessInput");
      const btnGuess = document.getElementById("btnGuess");
      const btnHint = document.getElementById("btnHint");
      const btnGiveUp = document.getElementById("btnGiveUp");
      const btnNext = document.getElementById("btnNext");

      if (data.revealed) {
        guessInput.disabled = true;
        guessInput.classList.add("disabled");
        btnGuess.style.display = "none";
        btnHint.style.display = "none";
        btnGiveUp.style.display = "none";
        btnNext.style.display = "inline-block";
      } else {
        guessInput.disabled = false;
        guessInput.classList.remove("disabled");
        guessInput.value = "";
        guessInput.focus();
        btnGuess.style.display = "inline-block";
        btnHint.style.display = "inline-block";
        btnGiveUp.style.display = "inline-block";
        btnNext.style.display = "none";
      }

      const guessesEl = document.getElementById("guessesArea");
      guessesEl.innerHTML = "";
      if (data.guesses && data.guesses.length > 0) {
        data.guesses.forEach(g => {
          const tag = document.createElement("span");
          tag.className = g.correct ? "guess-tag guess-correct" : "guess-tag guess-wrong";
          tag.textContent = g.text;
          guessesEl.appendChild(tag);
        });
      }

      document.getElementById("statsImg").src = "/stats_image?" + Date.now();

      // Update pool count if filter data present
      if (data.pool_size !== undefined) {
        document.getElementById("poolCount").textContent = 
          data.pool_size + " players in pool";
      }

      // Update filter inputs
      if (data.filters) {
        document.getElementById("fMode").value = data.filters.mode || "batting";
        document.getElementById("fMinYears").value = data.filters.min_years || 5;
        document.getElementById("fMinPA").value = data.filters.min_pa || 1500;
        document.getElementById("fMinIP").value = data.filters.min_ip || 1000;
        document.getElementById("fPlayedStart").value = data.filters.played_in_start || "";
        document.getElementById("fPlayedEnd").value = data.filters.played_in_end || "";
      }
    }

    async function submitGuess() {
      const guess = document.getElementById("guessInput").value.trim();
      if (!guess) return;
      const resp = await fetch("/guess", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ guess }),
      });
      updateUI(await resp.json());
    }

    async function getHint() {
      const resp = await fetch("/hint", { method: "POST" });
      updateUI(await resp.json());
    }

    async function giveUp() {
      const resp = await fetch("/giveup", { method: "POST" });
      updateUI(await resp.json());
    }

    async function nextPlayer() {
      document.getElementById("revealed").value = "false";
      const resp = await fetch("/next", { method: "POST" });
      updateUI(await resp.json());
    }

    async function applyFilters() {
      const body = {
        mode: document.getElementById("fMode").value,
        min_years: parseInt(document.getElementById("fMinYears").value) || 5,
        min_pa: parseInt(document.getElementById("fMinPA").value) || 1500,
        min_ip: parseInt(document.getElementById("fMinIP").value) || 1000,
        played_in_start: parseInt(document.getElementById("fPlayedStart").value) || null,
        played_in_end: parseInt(document.getElementById("fPlayedEnd").value) || null,
      };
      const resp = await fetch("/apply_filters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      updateUI(await resp.json());
    }

    function resetFilters() {
      document.getElementById("fMode").value = "batting";
      document.getElementById("fMinYears").value = 5;
      document.getElementById("fMinPA").value = 1500;
      document.getElementById("fMinIP").value = 1000;
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
        "current_type": STATE["current_type"],
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
        STATE["batting"], STATE["pitching"], STATE["people"],
        mode=f.get("mode", "batting"),
        min_years=f.get("min_years", 5),
        min_pa=f.get("min_pa", 1500),
        min_ip=f.get("min_ip", 1000),
        played_in=played_in,
    )
    STATE["player_ids"] = pool["playerID"].tolist()
    random.shuffle(STATE["player_ids"])
    STATE["current_idx"] = 0
    print(f"  Filter applied — pool: {len(STATE['player_ids'])} players (mode: {f.get('mode', 'batting')})")


def load_next_player():
    """Load the next player and generate their stats image."""
    if STATE["current_idx"] >= len(STATE["player_ids"]):
        random.shuffle(STATE["player_ids"])
        STATE["current_idx"] = 0

    pid = STATE["player_ids"][STATE["current_idx"]]
    
    # Determine if this is a batter or pitcher
    mode = STATE["filters"].get("mode", "batting")
    f = STATE["filters"]
    
    is_batter = False
    is_pitcher = False
    
    if mode == "batting":
        is_batter = True
    elif mode == "pitching":
        is_pitcher = True
    else:  # mode == "both"
        batter_ab = STATE["batting"][STATE["batting"]["playerID"] == pid]["AB"].sum() if STATE["batting"] is not None else 0
        pitcher_ip = STATE["pitching"][STATE["pitching"]["playerID"] == pid]["IPouts"].sum() / 3.0 if STATE["pitching"] is not None else 0
        
        min_pa = f.get("min_pa", 1500)
        min_ip = f.get("min_ip", 1000)
        
        if batter_ab >= min_pa and pitcher_ip >= min_ip:
            is_batter = random.choice([True, False])
            is_pitcher = not is_batter
        elif batter_ab >= min_pa:
            is_batter = True
        else:
            is_pitcher = True

    if is_batter:
        name, seasons = get_player_seasons_batting(
            STATE["batting"], STATE["people"],
            STATE["awards_df"], STATE["allstar_df"], pid,
            STATE["appearances_df"], STATE["awards_share_df"]
        )
        seasons = [s for s in seasons if s["AB"] > 0]
        if len(seasons) == 0:
            STATE["current_idx"] += 1
            return load_next_player()
        
        STATE["current_type"] = "batting"
        img_path = os.path.join(STATE["output_dir"], "current_player.png")
        render_stats_image_batting(seasons, img_path, show_name=None)
    else:
        name, seasons = get_player_seasons_pitching(
            STATE["pitching"], STATE["people"],
            STATE["awards_df"], STATE["allstar_df"], pid,
            STATE["awards_share_df"]
        )
        seasons = [s for s in seasons if s["IP"] > 0]
        if len(seasons) == 0:
            STATE["current_idx"] += 1
            return load_next_player()
        
        STATE["current_type"] = "pitching"
        img_path = os.path.join(STATE["output_dir"], "current_player.png")
        render_stats_image_pitching(seasons, img_path, show_name=None)

    STATE["current_name"] = name
    STATE["current_seasons"] = seasons
    STATE["guesses"] = []
    STATE["hints_given"] = 0
    STATE["hint_text"] = ""
    STATE["revealed"] = False
    STATE["last_correct"] = False


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
        if STATE["current_type"] == "batting":
            render_stats_image_batting(STATE["current_seasons"], img_path, show_name=STATE["current_name"])
        else:
            render_stats_image_pitching(STATE["current_seasons"], img_path, show_name=STATE["current_name"])

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
    if STATE["current_type"] == "batting":
        render_stats_image_batting(STATE["current_seasons"], img_path, show_name=STATE["current_name"])
    else:
        render_stats_image_pitching(STATE["current_seasons"], img_path, show_name=STATE["current_name"])

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
        "mode": data.get("mode", "batting"),
        "min_years": data.get("min_years", 5),
        "min_pa": data.get("min_pa", 1500),
        "min_ip": data.get("min_ip", 1000),
        "played_in_start": data.get("played_in_start"),
        "played_in_end": data.get("played_in_end"),
    }

    rebuild_pool()

    if len(STATE["player_ids"]) == 0:
        # No players match — revert to defaults
        STATE["filters"] = {
            "mode": "batting",
            "min_years": 5,
            "min_pa": 1500,
            "min_ip": 1000,
            "played_in_start": None,
            "played_in_end": None
        }
        rebuild_pool()

    # Reset score on filter change
    STATE["score_correct"] = 0
    STATE["score_total"] = 0
    STATE["streak"] = 0

    load_next_player()
    return jsonify(get_state_dict())


def main():
    parser = argparse.ArgumentParser(description="Name That Ballplayer — Web version with Batting & Pitching")
    parser.add_argument("--data-dir", required=True, help="Path to Lahman CSV folder")
    parser.add_argument("--port", type=int, default=5050)
    parser.add_argument("--output-dir", type=str, default=None)
    args = parser.parse_args()

    print("Loading Lahman database...")
    STATE["batting"], STATE["pitching"], STATE["people"], STATE["awards_df"], STATE["allstar_df"], STATE["appearances_df"], STATE["awards_share_df"] = load_data(args.data_dir)

    STATE["output_dir"] = args.output_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(STATE["output_dir"], exist_ok=True)

    rebuild_pool()
    load_next_player()

    print(f"\n  🎯 Open http://localhost:{args.port} in your browser!")
    print(f"  Press Ctrl+C to quit.\n")
    app.run(host="0.0.0.0", port=args.port, debug=False)


if __name__ == "__main__":
    main()
