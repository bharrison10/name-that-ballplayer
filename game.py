#!/usr/bin/env python3
"""
Name That Ballplayer — A baseball stats guessing game with BATTING and PITCHING support.

Reads the Lahman Baseball Database CSVs, picks a random player,
renders their year-by-year stats as a Baseball Reference–style
PNG image, and lets you guess who it is.

Setup:
  1. Download the Lahman database from https://github.com/chadwickbureau/baseballdatabank
     (or https://www.seanlahman.com/baseball-archive/statistics/)
  2. Place (or symlink) the CSV folder so that this script can find:
       <data_dir>/Batting.csv
       <data_dir>/Pitching.csv
       <data_dir>/People.csv
       <data_dir>/AwardsPlayers.csv
       <data_dir>/AllstarFull.csv
       <data_dir>/Appearances.csv
  3. pip install matplotlib pandas Pillow
  4. python game.py --data-dir /path/to/baseballdatabank/core --mode batting
     python game.py --data-dir /path/to/baseballdatabank/core --mode pitching
     python game.py --data-dir /path/to/baseballdatabank/core --mode both

Usage:
  python game.py --data-dir ./core --mode batting
  python game.py --data-dir ./core --mode pitching --min-ip 1000
  python game.py --data-dir ./core --mode both --era 1990-2020
"""

import argparse
import os
import random
import sys
import textwrap

import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import FancyBboxPatch
from PIL import Image


# ─── Data Loading ───────────────────────────────────────────────────────────

def load_data(data_dir):
    """Load and merge Lahman CSVs into usable dataframes."""
    batting_path     = os.path.join(data_dir, "Batting.csv")
    pitching_path    = os.path.join(data_dir, "Pitching.csv")
    people_path      = os.path.join(data_dir, "People.csv")
    awards_path      = os.path.join(data_dir, "AwardsPlayers.csv")
    allstar_path     = os.path.join(data_dir, "AllstarFull.csv")
    appearances_path = os.path.join(data_dir, "Appearances.csv")

    if not os.path.exists(people_path):
        print(f"ERROR: Required file not found: {people_path}")
        print(f"Make sure --data-dir points to the folder containing People.csv, etc.")
        sys.exit(1)

    batting = pd.read_csv(batting_path) if os.path.exists(batting_path) else None
    pitching = pd.read_csv(pitching_path) if os.path.exists(pitching_path) else None
    people  = pd.read_csv(people_path)

    if batting is not None:
        print(f"  Loaded Batting.csv ({len(batting)} rows)")
    if pitching is not None:
        print(f"  Loaded Pitching.csv ({len(pitching)} rows)")

    # Load awards if available
    awards_df = None
    if os.path.exists(awards_path):
        awards_df = pd.read_csv(awards_path)

    allstar_df = None
    if os.path.exists(allstar_path):
        allstar_df = pd.read_csv(allstar_path)

    appearances_df = None
    if os.path.exists(appearances_path):
        appearances_df = pd.read_csv(appearances_path)
        print(f"  Loaded Appearances.csv ({len(appearances_df)} rows)")
    else:
        print(f"  Warning: Appearances.csv not found — position data will be unavailable")

    # Load award vote shares for MVP/CY ranking (e.g. MVP-3, CY-2)
    awards_share_path = os.path.join(data_dir, "AwardsSharePlayers.csv")
    awards_share_df = None
    if os.path.exists(awards_share_path):
        awards_share_df = pd.read_csv(awards_share_path)
        # Precompute rankings per award/year/league
        for award_name in awards_share_df["awardID"].unique():
            mask = awards_share_df["awardID"] == award_name
            awards_share_df.loc[mask, "rank"] = (
                awards_share_df.loc[mask]
                .groupby(["yearID", "lgID"])["pointsWon"]
                .rank(method="min", ascending=False)
            )
        awards_share_df["rank"] = awards_share_df["rank"].fillna(99).astype(int)
        print(f"  Loaded AwardsSharePlayers.csv ({len(awards_share_df)} rows)")
    else:
        print(f"  Warning: AwardsSharePlayers.csv not found — MVP/CY vote rankings unavailable")

    return batting, pitching, people, awards_df, allstar_df, appearances_df, awards_share_df


def get_player_pool(batting, pitching, people, mode="batting", 
                   min_years=None, era=None, min_pa=1000, min_ip=1000, played_in=None):
    """Filter to a pool of eligible players based on mode.
    
    Args:
        mode: "batting", "pitching", or "both"
        min_pa: minimum plate appearances (for batters)
        min_ip: minimum innings pitched (for pitchers)
        played_in: tuple (start, end) — require player to have played at least one season 
                   where yearID falls within [start, end].
    """
    
    if mode == "batting" and batting is None:
        print("ERROR: Batting.csv not found. Cannot filter batters.")
        sys.exit(1)
    if mode == "pitching" and pitching is None:
        print("ERROR: Pitching.csv not found. Cannot filter pitchers.")
        sys.exit(1)
    if mode == "both" and (batting is None or pitching is None):
        print("ERROR: Both Batting.csv and Pitching.csv required for 'both' mode.")
        sys.exit(1)

    eligible_players = set()

    # Batters
    if mode in ("batting", "both") and batting is not None:
        career = batting.groupby("playerID").agg(
            total_AB=("AB", "sum"),
            num_seasons=("yearID", "nunique"),
            first_year=("yearID", "min"),
            last_year=("yearID", "max"),
        ).reset_index()

        career = career[career["total_AB"] >= min_pa]
        if min_years:
            career = career[career["num_seasons"] >= min_years]
        if era:
            start, end = era
            career = career[(career["first_year"] >= start) & (career["first_year"] <= end)]
        if played_in:
            start, end = played_in
            career = career[(career["last_year"] >= start) & (career["first_year"] <= end)]
        
        eligible_players.update(career["playerID"].tolist())

    # Pitchers
    if mode in ("pitching", "both") and pitching is not None:
        # IPouts is outs recorded (IP * 3)
        career = pitching.groupby("playerID").agg(
            total_IPouts=("IPouts", "sum"),
            num_seasons=("yearID", "nunique"),
            first_year=("yearID", "min"),
            last_year=("yearID", "max"),
        ).reset_index()
        
        career["total_IP"] = career["total_IPouts"] / 3.0
        career = career[career["total_IP"] >= min_ip]
        
        if min_years:
            career = career[career["num_seasons"] >= min_years]
        if era:
            start, end = era
            career = career[(career["first_year"] >= start) & (career["first_year"] <= end)]
        if played_in:
            start, end = played_in
            career = career[(career["last_year"] >= start) & (career["first_year"] <= end)]
        
        eligible_players.update(career["playerID"].tolist())

    # Merge with people to get names
    pool = people[people["playerID"].isin(eligible_players)].copy()
    pool["full_name"] = pool["nameFirst"].fillna("") + " " + pool["nameLast"].fillna("")
    pool = pool.dropna(subset=["nameFirst", "nameLast"])

    return pool


def _derive_position_string(appearances_df, player_id, year, team_id):
    """
    Derive a Baseball Reference-style position string from Appearances.csv.
    
    Format examples: *8/DH, 9/7H, *6, DH, 1/DH
    The primary position gets a * prefix. Positions are listed by most games played.
    """
    if appearances_df is None:
        return ""

    POS_MAP = [
        ("G_c",  "2"),    # Catcher
        ("G_1b", "3"),    # First base
        ("G_2b", "4"),    # Second base
        ("G_3b", "5"),    # Third base
        ("G_ss", "6"),    # Shortstop
        ("G_lf", "7"),    # Left field
        ("G_cf", "8"),    # Center field
        ("G_rf", "9"),    # Right field
        ("G_dh", "D"),    # Designated hitter
        ("G_p",  "1"),    # Pitcher
        ("G_of", "O"),    # Outfield (generic)
    ]
    
    mask = (appearances_df["playerID"] == player_id) & (appearances_df["yearID"] == year)
    if team_id:
        mask_team = mask & (appearances_df["teamID"] == team_id)
        rows = appearances_df[mask_team]
        if len(rows) == 0:
            rows = appearances_df[mask]
    else:
        rows = appearances_df[mask]
    
    if len(rows) == 0:
        return ""
    
    pos_games = {}
    for col, code in POS_MAP:
        if col in rows.columns:
            total = rows[col].fillna(0).sum()
            if total > 0:
                pos_games[code] = int(total)
    
    if not pos_games:
        return ""
    
    has_specific_of = any(pos_games.get(c, 0) > 0 for c in ("7", "8", "9"))
    if has_specific_of and "O" in pos_games:
        del pos_games["O"]
    
    sorted_pos = sorted(pos_games.items(), key=lambda x: -x[1])
    
    primary_code = sorted_pos[0][0]
    primary_games = sorted_pos[0][1]
    
    parts = []
    for code, games in sorted_pos:
        if len(parts) > 0 and games < 3:
            continue
        if len(parts) >= 4:
            break
        parts.append(code)
    
    if not parts:
        return ""
    
    result = "*" + parts[0]
    if len(parts) > 1:
        result += "/" + "/".join(parts[1:])
    
    result = result.replace("O", "OF")
    result = result.replace("D", "DH")
    
    return result


def get_player_seasons_batting(batting, people, awards_df, allstar_df, player_id, appearances_df=None, awards_share_df=None):
    """Get year-by-year batting stats for a player, with awards and positions."""

    TEAM_DISPLAY = {
        "LAN": "LAD", "SLN": "STL", "CHN": "CHC", "SFN": "SFG", "NYN": "NYM",
        "SDN": "SDP", "CIN": "CIN", "PIT": "PIT", "MIL": "MIL", "ARI": "ARI",
        "COL": "COL", "ATL": "ATL", "MIA": "MIA", "WAS": "WSN", "PHI": "PHI",
        "CHA": "CHW", "KCA": "KCR", "ANA": "ANA", "LAA": "LAA", "OAK": "OAK",
        "SEA": "SEA", "TEX": "TEX", "MIN": "MIN", "DET": "DET", "CLE": "CLE",
        "TOR": "TOR", "BAL": "BAL", "BOS": "BOS", "NYA": "NYY", "TBA": "TBR",
        "HOU": "HOU", "FLO": "FLA", "MON": "MON", "ML4": "MIL", "SE1": "SEA",
        "CAL": "CAL", "WSA": "WSA", "PHA": "PHA", "SLA": "STL", "BRO": "BKN",
        "NY1": "NYG", "BSN": "BSN", "MLN": "MLN", "WS1": "WSH", "WS2": "WSH",
        "BL2": "BAL", "BL3": "BAL", "BL4": "BAL",
        "PT1": "PIT", "RC1": "ROC", "CN1": "CIN", "CN2": "CIN",
        "CH1": "CHC", "CH2": "CHW", "CL4": "CLE", "CL5": "CLE", "CL6": "CLE",
        "PHN": "PHI", "SLF": "STL", "TBD": "TBD",
    }

    pdf = batting[batting["playerID"] == player_id].copy()
    pdf = pdf.sort_values("yearID")

    person = people[people["playerID"] == player_id].iloc[0]
    name = f"{person['nameFirst']} {person['nameLast']}"
    birth_year = person.get("birthYear", None)

    seasons = []
    for _, row in pdf.iterrows():
        def safe_int(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return 0
            return int(val)

        year = int(row["yearID"])
        team_raw = str(row.get("teamID", "???"))
        team = TEAM_DISPLAY.get(team_raw, team_raw)
        lg   = row.get("lgID", "??")
        G    = safe_int(row.get("G", 0))
        AB   = safe_int(row.get("AB", 0))
        R    = safe_int(row.get("R", 0))
        H    = safe_int(row.get("H", 0))
        _2B  = safe_int(row.get("2B", 0))
        _3B  = safe_int(row.get("3B", 0))
        HR   = safe_int(row.get("HR", 0))
        RBI  = safe_int(row.get("RBI", 0))
        SB   = safe_int(row.get("SB", 0))
        CS   = safe_int(row.get("CS", 0))
        BB   = safe_int(row.get("BB", 0))
        SO   = safe_int(row.get("SO", 0))
        IBB  = safe_int(row.get("IBB", 0))
        HBP  = safe_int(row.get("HBP", 0))
        SF   = safe_int(row.get("SF", 0))

        BA  = H / AB if AB > 0 else 0
        obp_denom = AB + BB + HBP + SF
        OBP = (H + BB + HBP) / obp_denom if obp_denom > 0 else 0
        TB  = H + _2B + 2 * _3B + 3 * HR
        SLG = TB / AB if AB > 0 else 0
        OPS = OBP + SLG

        age = year - birth_year if birth_year and not pd.isna(birth_year) else ""

        # Awards
        awards_list = []
        if allstar_df is not None:
            if ((allstar_df["playerID"] == player_id) & (allstar_df["yearID"] == year)).any():
                awards_list.append("AS")

        mvp_rank = None
        cy_rank = None
        if awards_share_df is not None:
            player_shares = awards_share_df[
                (awards_share_df["playerID"] == player_id) &
                (awards_share_df["yearID"] == year)
            ]
            for _, srow in player_shares.iterrows():
                aid = srow.get("awardID", "")
                rank = int(srow.get("rank", 99))
                if "Valuable" in aid or "MVP" in aid:
                    mvp_rank = rank
                elif "Cy Young" in aid:
                    cy_rank = rank
                elif "Rookie" in aid:
                    if rank == 1:
                        awards_list.append("ROY")
                    else:
                        awards_list.append(f"ROY-{rank}")

        if mvp_rank is not None:
            awards_list.append("MVP" if mvp_rank == 1 else f"MVP-{mvp_rank}")
        if cy_rank is not None:
            awards_list.append("CY" if cy_rank == 1 else f"CY-{cy_rank}")

        if awards_df is not None:
            yr_awards = awards_df[(awards_df["playerID"] == player_id) & (awards_df["yearID"] == year)]
            for _, arow in yr_awards.iterrows():
                aid = arow.get("awardID", "")
                if "Gold Glove" in aid:
                    awards_list.append("GG")
                elif "Silver Slugger" in aid:
                    awards_list.append("SS")
                elif "Rookie" in aid and "ROY" not in [a.split("-")[0] for a in awards_list]:
                    awards_list.append("ROY")

        awards_str = ",".join(sorted(set(awards_list)))
        pos_str = _derive_position_string(appearances_df, player_id, year, team)

        seasons.append({
            "Year": year, "Age": age, "Tm": team, "Lg": lg,
            "G": G, "AB": AB, "R": R, "H": H,
            "2B": _2B, "3B": _3B, "HR": HR, "RBI": RBI,
            "SB": SB, "CS": CS, "BB": BB, "SO": SO,
            "BA": BA, "OBP": OBP, "SLG": SLG, "OPS": OPS,
            "Pos": pos_str, "Awards": awards_str,
        })

    return name, seasons


def get_player_seasons_pitching(pitching, people, awards_df, allstar_df, player_id, awards_share_df=None):
    """Get year-by-year pitching stats for a player, with awards."""

    TEAM_DISPLAY = {
        "LAN": "LAD", "SLN": "STL", "CHN": "CHC", "SFN": "SFG", "NYN": "NYM",
        "SDN": "SDP", "CIN": "CIN", "PIT": "PIT", "MIL": "MIL", "ARI": "ARI",
        "COL": "COL", "ATL": "ATL", "MIA": "MIA", "WAS": "WSN", "PHI": "PHI",
        "CHA": "CHW", "KCA": "KCR", "ANA": "ANA", "LAA": "LAA", "OAK": "OAK",
        "SEA": "SEA", "TEX": "TEX", "MIN": "MIN", "DET": "DET", "CLE": "CLE",
        "TOR": "TOR", "BAL": "BAL", "BOS": "BOS", "NYA": "NYY", "TBA": "TBR",
        "HOU": "HOU", "FLO": "FLA", "MON": "MON", "ML4": "MIL", "SE1": "SEA",
        "CAL": "CAL", "WSA": "WSA", "PHA": "PHA", "SLA": "STL", "BRO": "BKN",
        "NY1": "NYG", "BSN": "BSN", "MLN": "MLN", "WS1": "WSH", "WS2": "WSH",
        "BL2": "BAL", "BL3": "BAL", "BL4": "BAL",
        "PT1": "PIT", "RC1": "ROC", "CN1": "CIN", "CN2": "CIN",
        "CH1": "CHC", "CH2": "CHW", "CL4": "CLE", "CL5": "CLE", "CL6": "CLE",
        "PHN": "PHI", "SLF": "STL", "TBD": "TBD",
    }

    pdf = pitching[pitching["playerID"] == player_id].copy()
    pdf = pdf.sort_values("yearID")

    person = people[people["playerID"] == player_id].iloc[0]
    name = f"{person['nameFirst']} {person['nameLast']}"
    birth_year = person.get("birthYear", None)

    seasons = []
    for _, row in pdf.iterrows():
        def safe_int(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return 0
            return int(val)

        def safe_float(val):
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return 0.0
            return float(val)

        year = int(row["yearID"])
        team_raw = str(row.get("teamID", "???"))
        team = TEAM_DISPLAY.get(team_raw, team_raw)
        lg   = row.get("lgID", "??")
        
        W    = safe_int(row.get("W", 0))
        L    = safe_int(row.get("L", 0))
        G    = safe_int(row.get("G", 0))
        GS   = safe_int(row.get("GS", 0))
        CG   = safe_int(row.get("CG", 0))
        SHO  = safe_int(row.get("SHO", 0))
        SV   = safe_int(row.get("SV", 0))
        IPouts = safe_int(row.get("IPouts", 0))
        H    = safe_int(row.get("H", 0))
        ER   = safe_int(row.get("ER", 0))
        HR   = safe_int(row.get("HR", 0))
        BB   = safe_int(row.get("BB", 0))
        SO   = safe_int(row.get("SO", 0))
        
        IP = IPouts / 3.0  # Convert outs to innings
        ERA = (ER * 9.0 / IP) if IP > 0 else 0.0
        WHIP = (H + BB) / IP if IP > 0 else 0.0

        age = year - birth_year if birth_year and not pd.isna(birth_year) else ""

        # Awards
        awards_list = []
        if allstar_df is not None:
            if ((allstar_df["playerID"] == player_id) & (allstar_df["yearID"] == year)).any():
                awards_list.append("AS")

        mvp_rank = None
        cy_rank = None
        if awards_share_df is not None:
            player_shares = awards_share_df[
                (awards_share_df["playerID"] == player_id) &
                (awards_share_df["yearID"] == year)
            ]
            for _, srow in player_shares.iterrows():
                aid = srow.get("awardID", "")
                rank = int(srow.get("rank", 99))
                if "Valuable" in aid or "MVP" in aid:
                    mvp_rank = rank
                elif "Cy Young" in aid:
                    cy_rank = rank
                elif "Rookie" in aid:
                    if rank == 1:
                        awards_list.append("ROY")
                    else:
                        awards_list.append(f"ROY-{rank}")

        if mvp_rank is not None:
            awards_list.append("MVP" if mvp_rank == 1 else f"MVP-{mvp_rank}")
        if cy_rank is not None:
            awards_list.append("CY" if cy_rank == 1 else f"CY-{cy_rank}")

        if awards_df is not None:
            yr_awards = awards_df[(awards_df["playerID"] == player_id) & (awards_df["yearID"] == year)]
            for _, arow in yr_awards.iterrows():
                aid = arow.get("awardID", "")
                if "Gold Glove" in aid:
                    awards_list.append("GG")
                elif "Rookie" in aid and "ROY" not in [a.split("-")[0] for a in awards_list]:
                    awards_list.append("ROY")

        awards_str = ",".join(sorted(set(awards_list)))

        seasons.append({
            "Year": year, "Age": age, "Tm": team, "Lg": lg,
            "W": W, "L": L, "ERA": ERA, "G": G, "GS": GS, "CG": CG,
            "SHO": SHO, "SV": SV, "IP": IP, "H": H, "ER": ER, "HR": HR,
            "BB": BB, "SO": SO, "WHIP": WHIP, "Awards": awards_str,
        })

    return name, seasons


def compute_totals_batting(seasons):
    """Compute career totals row from batting season dicts."""
    keys_sum = ["G","AB","R","H","2B","3B","HR","RBI","SB","CS","BB","SO"]
    totals = {k: sum(s[k] for s in seasons) for k in keys_sum}
    AB = totals["AB"]
    H  = totals["H"]
    BB = totals["BB"]
    totals["BA"]  = H / AB if AB > 0 else 0
    PA = AB + BB
    totals["OBP"] = (H + BB) / PA if PA > 0 else 0
    TB = H + totals["2B"] + 2 * totals["3B"] + 3 * totals["HR"]
    totals["SLG"] = TB / AB if AB > 0 else 0
    totals["OPS"] = totals["OBP"] + totals["SLG"]
    unique_years = len(set(s["Year"] for s in seasons))
    totals["label"] = f"{unique_years} Yrs"
    return totals


def compute_totals_pitching(seasons):
    """Compute career totals row from pitching season dicts."""
    keys_sum = ["W","L","G","GS","CG","SHO","SV","IP","H","ER","HR","BB","SO"]
    totals = {k: sum(s[k] for s in seasons) for k in keys_sum}
    IP = totals["IP"]
    ER = totals["ER"]
    H  = totals["H"]
    BB = totals["BB"]
    totals["ERA"]  = (ER * 9.0 / IP) if IP > 0 else 0.0
    totals["WHIP"] = (H + BB) / IP if IP > 0 else 0.0
    unique_years = len(set(s["Year"] for s in seasons))
    totals["label"] = f"{unique_years} Yrs"
    return totals


# ─── Image Rendering ────────────────────────────────────────────────────────

# Baseball Reference color palette
BR_RED       = "#8C1515"
BR_DARK_RED  = "#5a0f0f"
BR_BG        = "#f7f7f0"
BR_BG_ALT    = "#ffffff"
BR_HEADER_BG = "#dddddd"
BR_BORDER    = "#cccccc"
BR_LINK      = "#00457c"
BR_TEXT      = "#1a1a1a"
BR_AWARD     = "#00457c"
BR_HIGHLIGHT = "#8C1515"

COLUMNS_BATTING = [
    ("Year",  4.5, "left"),
    ("Age",   3.0, "right"),
    ("Tm",    3.5, "left"),
    ("Lg",    2.5, "center"),
    ("G",     3.5, "right"),
    ("AB",    4.0, "right"),
    ("R",     3.5, "right"),
    ("H",     3.5, "right"),
    ("2B",    3.0, "right"),
    ("3B",    3.0, "right"),
    ("HR",    3.5, "right"),
    ("RBI",   3.5, "right"),
    ("SB",    3.0, "right"),
    ("CS",    3.0, "right"),
    ("BB",    3.5, "right"),
    ("SO",    3.5, "right"),
    ("BA",    4.5, "right"),
    ("OBP",   4.5, "right"),
    ("SLG",   4.5, "right"),
    ("OPS",   4.5, "right"),
    ("Pos",   5.5, "left"),
    ("Awards",7.0, "left"),
]

COLUMNS_PITCHING = [
    ("Year",  4.5, "left"),
    ("Age",   3.0, "right"),
    ("Tm",    3.5, "left"),
    ("Lg",    2.5, "center"),
    ("W",     3.0, "right"),
    ("L",     3.0, "right"),
    ("ERA",   4.5, "right"),
    ("G",     3.5, "right"),
    ("GS",    3.5, "right"),
    ("CG",    3.0, "right"),
    ("SHO",   3.0, "right"),
    ("SV",    3.0, "right"),
    ("IP",    4.5, "right"),
    ("H",     3.5, "right"),
    ("ER",    3.5, "right"),
    ("HR",    3.0, "right"),
    ("BB",    3.5, "right"),
    ("SO",    3.5, "right"),
    ("WHIP",  4.5, "right"),
    ("Awards",7.0, "left"),
]


def fmt_val(col, val, is_pitching=False):
    """Format a value for display."""
    if col in ("BA", "OBP", "SLG", "OPS", "ERA", "WHIP"):
        if val == 0:
            return ".000" if col != "ERA" else "0.00"
        if col in ("ERA", "WHIP"):
            return f"{val:.2f}"
        return f"{val:.3f}".lstrip("0")
    if col == "IP":
        # Display innings as XXX.1 or XXX.2 format
        whole = int(val)
        frac = val - whole
        if frac < 0.15:
            return str(whole)
        elif frac < 0.5:
            return f"{whole}.1"
        else:
            return f"{whole}.2"
    if col == "Year":
        return str(int(val))
    if col in ("Age",):
        return str(int(val)) if val != "" else ""
    if col == "Awards":
        return str(val) if val else ""
    if col == "Pos":
        return str(val) if val else ""
    if col in ("Tm", "Lg"):
        return str(val)
    return str(int(val))


def render_stats_image_batting(seasons, output_path, show_name=None):
    """Render year-by-year batting stats as a Baseball Reference-style PNG."""
    totals = compute_totals_batting(seasons)
    num_rows = len(seasons) + 1

    col_widths = [c[1] for c in COLUMNS_BATTING]
    total_width_chars = sum(col_widths)
    
    char_width = 0.115
    fig_width = total_width_chars * char_width + 0.8
    row_height = 0.22
    header_height = 0.55
    title_height = 0.45 if show_name else 0.35
    section_header_height = 0.30
    fig_height = title_height + section_header_height + header_height + (num_rows * row_height) + 0.3

    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height), dpi=150)
    ax.set_xlim(0, fig_width)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_facecolor("#f5f3ed")

    y_cursor = fig_height

    # Title
    y_cursor -= title_height
    if show_name:
        ax.text(0.3, y_cursor + 0.15, show_name,
                fontsize=16, fontweight="bold", color=BR_LINK,
                fontfamily="serif", va="bottom")
    else:
        ax.text(0.3, y_cursor + 0.15, "??? ???",
                fontsize=16, fontweight="bold", color="#999999",
                fontfamily="serif", va="bottom")

    # Section header
    y_cursor -= section_header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, section_header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)
    ax.text(0.3, y_cursor + section_header_height / 2, "Standard Batting",
            fontsize=9, fontweight="bold", color=BR_TEXT,
            fontfamily="sans-serif", va="center")

    # Column headers
    y_cursor -= header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)
    ax.plot([0, fig_width], [y_cursor, y_cursor], color=BR_RED, linewidth=1.5)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS_BATTING:
        if col_align == "left":
            tx = x + 0.1
            ha = "left"
        elif col_align == "center":
            tx = x + col_w * char_width / 2
            ha = "center"
        else:
            tx = x + col_w * char_width - 0.05
            ha = "right"

        ax.text(tx, y_cursor + header_height / 2, col_name,
                fontsize=7, fontweight="bold", color="#333",
                fontfamily="monospace", va="center", ha=ha)
        x += col_w * char_width

    # Data rows
    for row_idx, season in enumerate(seasons):
        y_cursor -= row_height
        bg = BR_BG if row_idx % 2 == 0 else BR_BG_ALT
        rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                              facecolor=bg, edgecolor="none")
        ax.add_patch(rect)
        ax.plot([0, fig_width], [y_cursor, y_cursor], color="#e0ddd5", linewidth=0.3)

        x = 0.3
        for col_name, col_w, col_align in COLUMNS_BATTING:
            val = season.get(col_name, "")
            text = fmt_val(col_name, val)

            if col_align == "left":
                tx = x + 0.1
                ha = "left"
            elif col_align == "center":
                tx = x + col_w * char_width / 2
                ha = "center"
            else:
                tx = x + col_w * char_width - 0.05
                ha = "right"

            color = BR_TEXT
            weight = "normal"
            fsize = 7

            if col_name in ("Year", "Tm", "Lg"):
                color = BR_LINK
                weight = "bold" if col_name == "Year" else "normal"
            elif col_name in ("BA", "OBP", "SLG", "OPS"):
                weight = "bold"
                if col_name == "OPS" and isinstance(val, (int, float)) and val >= 0.900:
                    color = BR_HIGHLIGHT
                    weight = "bold"
            elif col_name == "HR" and isinstance(val, (int, float)) and val >= 30:
                color = BR_HIGHLIGHT
                weight = "bold"
            elif col_name == "SB" and isinstance(val, (int, float)) and val >= 30:
                color = BR_HIGHLIGHT
                weight = "bold"
            elif col_name == "Awards":
                color = BR_AWARD
                fsize = 6
            elif col_name == "Pos":
                color = BR_TEXT
                fsize = 6.5

            ax.text(tx, y_cursor + row_height / 2, text,
                    fontsize=fsize, fontweight=weight, color=color,
                    fontfamily="monospace", va="center", ha=ha)
            x += col_w * char_width

    # Totals row
    y_cursor -= row_height
    ax.plot([0, fig_width], [y_cursor + row_height, y_cursor + row_height], color=BR_RED, linewidth=1.5)
    rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                          facecolor="#e8e5d8", edgecolor="none")
    ax.add_patch(rect)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS_BATTING:
        if col_name == "Year":
            val = totals["label"]
            text = val
        elif col_name in ("Age", "Tm", "Lg", "Pos", "Awards"):
            text = ""
        else:
            val = totals.get(col_name, "")
            text = fmt_val(col_name, val)

        if col_align == "left":
            tx = x + 0.1
            ha = "left"
        elif col_align == "center":
            tx = x + col_w * char_width / 2
            ha = "center"
        else:
            tx = x + col_w * char_width - 0.05
            ha = "right"

        ax.text(tx, y_cursor + row_height / 2, text,
                fontsize=7, fontweight="bold", color=BR_TEXT,
                fontfamily="monospace", va="center", ha=ha)
        x += col_w * char_width

    plt.tight_layout(pad=0.1)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


def render_stats_image_pitching(seasons, output_path, show_name=None):
    """Render year-by-year pitching stats as a Baseball Reference-style PNG."""
    totals = compute_totals_pitching(seasons)
    num_rows = len(seasons) + 1

    col_widths = [c[1] for c in COLUMNS_PITCHING]
    total_width_chars = sum(col_widths)
    
    char_width = 0.115
    fig_width = total_width_chars * char_width + 0.8
    row_height = 0.22
    header_height = 0.55
    title_height = 0.45 if show_name else 0.35
    section_header_height = 0.30
    fig_height = title_height + section_header_height + header_height + (num_rows * row_height) + 0.3

    fig, ax = plt.subplots(1, 1, figsize=(fig_width, fig_height), dpi=150)
    ax.set_xlim(0, fig_width)
    ax.set_ylim(0, fig_height)
    ax.axis("off")
    fig.patch.set_facecolor("#f5f3ed")

    y_cursor = fig_height

    # Title
    y_cursor -= title_height
    if show_name:
        ax.text(0.3, y_cursor + 0.15, show_name,
                fontsize=16, fontweight="bold", color=BR_LINK,
                fontfamily="serif", va="bottom")
    else:
        ax.text(0.3, y_cursor + 0.15, "??? ???",
                fontsize=16, fontweight="bold", color="#999999",
                fontfamily="serif", va="bottom")

    # Section header
    y_cursor -= section_header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, section_header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)
    ax.text(0.3, y_cursor + section_header_height / 2, "Standard Pitching",
            fontsize=9, fontweight="bold", color=BR_TEXT,
            fontfamily="sans-serif", va="center")

    # Column headers
    y_cursor -= header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)
    ax.plot([0, fig_width], [y_cursor, y_cursor], color=BR_RED, linewidth=1.5)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS_PITCHING:
        if col_align == "left":
            tx = x + 0.1
            ha = "left"
        elif col_align == "center":
            tx = x + col_w * char_width / 2
            ha = "center"
        else:
            tx = x + col_w * char_width - 0.05
            ha = "right"

        ax.text(tx, y_cursor + header_height / 2, col_name,
                fontsize=7, fontweight="bold", color="#333",
                fontfamily="monospace", va="center", ha=ha)
        x += col_w * char_width

    # Data rows
    for row_idx, season in enumerate(seasons):
        y_cursor -= row_height
        bg = BR_BG if row_idx % 2 == 0 else BR_BG_ALT
        rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                              facecolor=bg, edgecolor="none")
        ax.add_patch(rect)
        ax.plot([0, fig_width], [y_cursor, y_cursor], color="#e0ddd5", linewidth=0.3)

        x = 0.3
        for col_name, col_w, col_align in COLUMNS_PITCHING:
            val = season.get(col_name, "")
            text = fmt_val(col_name, val, is_pitching=True)

            if col_align == "left":
                tx = x + 0.1
                ha = "left"
            elif col_align == "center":
                tx = x + col_w * char_width / 2
                ha = "center"
            else:
                tx = x + col_w * char_width - 0.05
                ha = "right"

            color = BR_TEXT
            weight = "normal"
            fsize = 7

            if col_name in ("Year", "Tm", "Lg"):
                color = BR_LINK
                weight = "bold" if col_name == "Year" else "normal"
            elif col_name in ("ERA", "WHIP"):
                weight = "bold"
                if col_name == "ERA" and isinstance(val, (int, float)) and val <= 3.00:
                    color = BR_HIGHLIGHT
                    weight = "bold"
            elif col_name == "W" and isinstance(val, (int, float)) and val >= 20:
                color = BR_HIGHLIGHT
                weight = "bold"
            elif col_name == "SO" and isinstance(val, (int, float)) and val >= 200:
                color = BR_HIGHLIGHT
                weight = "bold"
            elif col_name == "Awards":
                color = BR_AWARD
                fsize = 6

            ax.text(tx, y_cursor + row_height / 2, text,
                    fontsize=fsize, fontweight=weight, color=color,
                    fontfamily="monospace", va="center", ha=ha)
            x += col_w * char_width

    # Totals row
    y_cursor -= row_height
    ax.plot([0, fig_width], [y_cursor + row_height, y_cursor + row_height], color=BR_RED, linewidth=1.5)
    rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                          facecolor="#e8e5d8", edgecolor="none")
    ax.add_patch(rect)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS_PITCHING:
        if col_name == "Year":
            val = totals["label"]
            text = val
        elif col_name in ("Age", "Tm", "Lg", "Awards"):
            text = ""
        else:
            val = totals.get(col_name, "")
            text = fmt_val(col_name, val, is_pitching=True)

        if col_align == "left":
            tx = x + 0.1
            ha = "left"
        elif col_align == "center":
            tx = x + col_w * char_width / 2
            ha = "center"
        else:
            tx = x + col_w * char_width - 0.05
            ha = "right"

        ax.text(tx, y_cursor + row_height / 2, text,
                fontsize=7, fontweight="bold", color=BR_TEXT,
                fontfamily="monospace", va="center", ha=ha)
        x += col_w * char_width

    plt.tight_layout(pad=0.1)
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor=fig.get_facecolor(), edgecolor="none")
    plt.close(fig)


# ─── Game Logic ──────────────────────────────────────────────────────────────

def play_game(data_dir, mode="batting", min_years=None, era=None, 
              min_pa=1000, min_ip=1000, output_dir=None):
    """Main game loop."""
    print("\n" + "=" * 60)
    print("  ⚾  NAME THAT BALLPLAYER  ⚾")
    print("=" * 60)
    print("Loading Lahman database...")

    batting, pitching, people, awards_df, allstar_df, appearances_df, awards_share_df = load_data(data_dir)

    pool = get_player_pool(batting, pitching, people, mode=mode,
                          min_years=min_years, era=era, min_pa=min_pa, min_ip=min_ip)

    if len(pool) == 0:
        print("No players match your filters. Try relaxing constraints.")
        sys.exit(1)

    print(f"Player pool: {len(pool)} eligible players (mode: {mode})")

    if output_dir is None:
        output_dir = os.path.join(os.path.dirname(__file__), "output")
    os.makedirs(output_dir, exist_ok=True)

    player_ids = pool["playerID"].tolist()
    random.shuffle(player_ids)

    score_correct = 0
    score_total = 0
    streak = 0
    best_streak = 0

    for round_num, pid in enumerate(player_ids, 1):
        # Determine if this player is primarily a batter or pitcher
        is_batter = False
        is_pitcher = False
        
        if mode == "batting":
            is_batter = True
        elif mode == "pitching":
            is_pitcher = True
        else:  # mode == "both"
            # Check which stats are more prominent
            batter_ab = batting[batting["playerID"] == pid]["AB"].sum() if batting is not None else 0
            pitcher_ip = pitching[pitching["playerID"] == pid]["IPouts"].sum() / 3.0 if pitching is not None else 0
            
            if batter_ab >= min_pa and pitcher_ip >= min_ip:
                # Two-way player - choose randomly
                is_batter = random.choice([True, False])
                is_pitcher = not is_batter
            elif batter_ab >= min_pa:
                is_batter = True
            else:
                is_pitcher = True

        if is_batter:
            name, seasons = get_player_seasons_batting(batting, people, awards_df, allstar_df, pid, appearances_df, awards_share_df)
            seasons = [s for s in seasons if s["AB"] > 0]
            if len(seasons) == 0:
                continue
            img_path = os.path.join(output_dir, "current_player.png")
            render_stats_image_batting(seasons, img_path, show_name=None)
        else:
            name, seasons = get_player_seasons_pitching(pitching, people, awards_df, allstar_df, pid, awards_share_df)
            seasons = [s for s in seasons if s["IP"] > 0]
            if len(seasons) == 0:
                continue
            img_path = os.path.join(output_dir, "current_player.png")
            render_stats_image_pitching(seasons, img_path, show_name=None)

        print(f"\n{'─' * 60}")
        print(f"  Round {round_num}  |  Score: {score_correct}/{score_total}  |  Streak: {streak}  |  Best: {best_streak}")
        print(f"{'─' * 60}")
        print(f"  Stats image saved to: {img_path}")
        print(f"  Open it and study the stats!")
        print()

        hints_given = 0
        name_parts = name.split()

        while True:
            user_input = input("  Your guess (or 'hint' / 'give up' / 'quit'): ").strip()

            if user_input.lower() == "quit":
                print(f"\n  Final score: {score_correct}/{score_total}")
                print(f"  Best streak: {best_streak}")
                return

            if user_input.lower() == "give up":
                print(f"\n  ❌ The answer was: {name}")
                reveal_path = os.path.join(output_dir, "revealed_player.png")
                if is_batter:
                    render_stats_image_batting(seasons, reveal_path, show_name=name)
                else:
                    render_stats_image_pitching(seasons, reveal_path, show_name=name)
                print(f"  Revealed image: {reveal_path}")
                score_total += 1
                streak = 0
                break

            if user_input.lower() == "hint":
                hints_given += 1
                if hints_given == 1:
                    initials = " ".join(p[0] + "." for p in name_parts)
                    print(f"  💡 Initials: {initials}")
                elif hints_given == 2:
                    print(f"  💡 First name: {name_parts[0]}")
                elif hints_given == 3:
                    partial = name_parts[0] + " " + " ".join(
                        p[:max(2, len(p)//2)] + "…" for p in name_parts[1:]
                    )
                    print(f"  💡 Partial: {partial}")
                else:
                    print(f"  💡 No more hints!")
                continue

            def normalize(s):
                return "".join(c for c in s.lower() if c.isalpha())

            if normalize(user_input) == normalize(name):
                print(f"\n  ✅ Correct! It's {name}!")
                reveal_path = os.path.join(output_dir, "revealed_player.png")
                if is_batter:
                    render_stats_image_batting(seasons, reveal_path, show_name=name)
                else:
                    render_stats_image_pitching(seasons, reveal_path, show_name=name)
                score_correct += 1
                score_total += 1
                streak += 1
                best_streak = max(best_streak, streak)
                break
            else:
                print(f"  ❌ Not {user_input}. Try again!")

    print(f"\n  You've gone through all {len(player_ids)} players!")
    print(f"  Final score: {score_correct}/{score_total}")


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Name That Ballplayer — guess MLB players from their stats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              python game.py --data-dir ./core --mode batting
              python game.py --data-dir ./core --mode pitching --min-ip 1500
              python game.py --data-dir ./core --mode both --era 1990-2020
        """),
    )
    parser.add_argument("--data-dir", required=True,
                        help="Path to folder containing Lahman CSVs")
    parser.add_argument("--mode", choices=["batting", "pitching", "both"], default="batting",
                        help="Game mode: batting, pitching, or both (default: batting)")
    parser.add_argument("--min-years", type=int, default=5,
                        help="Minimum career seasons (default: 5)")
    parser.add_argument("--min-pa", type=int, default=1500,
                        help="Minimum career AB for batters (default: 1500)")
    parser.add_argument("--min-ip", type=int, default=1000,
                        help="Minimum career IP for pitchers (default: 1000)")
    parser.add_argument("--era", type=str, default=None,
                        help="Debut year range, e.g. '1980-2010'")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Directory for generated images (default: ./output)")

    args = parser.parse_args()

    era = None
    if args.era:
        parts = args.era.split("-")
        era = (int(parts[0]), int(parts[1]))

    play_game(
        data_dir=args.data_dir,
        mode=args.mode,
        min_years=args.min_years,
        era=era,
        min_pa=args.min_pa,
        min_ip=args.min_ip,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
