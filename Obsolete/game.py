#!/usr/bin/env python3
"""
Name That Ballplayer — A baseball stats guessing game.

Reads the Lahman Baseball Database CSVs, picks a random player,
renders their year-by-year batting stats as a Baseball Reference–style
PNG image, and lets you guess who it is.

Setup:
  1. Download the Lahman database from https://github.com/chadwickbureau/baseballdatabank
     (or https://www.seanlahman.com/baseball-archive/statistics/)
  2. Place (or symlink) the CSV folder so that this script can find:
       <data_dir>/Batting.csv
       <data_dir>/People.csv
       <data_dir>/AwardsPlayers.csv
       <data_dir>/AllstarFull.csv
       <data_dir>/Appearances.csv
  3. pip install matplotlib pandas Pillow
  4. python game.py --data-dir /path/to/baseballdatabank/core

Usage:
  python game.py --data-dir ./core
  python game.py --data-dir ./core --min-war 30   # only great players
  python game.py --data-dir ./core --min-years 10  # 10+ year careers
  python game.py --data-dir ./core --era 1990-2020 # debut in range
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
    """Load and merge Lahman CSVs into a usable player+batting dataframe."""
    batting_path     = os.path.join(data_dir, "Batting.csv")
    people_path      = os.path.join(data_dir, "People.csv")
    awards_path      = os.path.join(data_dir, "AwardsPlayers.csv")
    allstar_path     = os.path.join(data_dir, "AllstarFull.csv")
    appearances_path = os.path.join(data_dir, "Appearances.csv")

    for p in [batting_path, people_path]:
        if not os.path.exists(p):
            print(f"ERROR: Required file not found: {p}")
            print(f"Make sure --data-dir points to the folder containing Batting.csv, People.csv, etc.")
            sys.exit(1)

    batting = pd.read_csv(batting_path)
    people  = pd.read_csv(people_path)

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
        # Rank by pointsWon descending within each award+year+league group
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

    return batting, people, awards_df, allstar_df, appearances_df, awards_share_df


def get_player_pool(batting, people, min_war=None, min_years=None, era=None, min_pa=1000, played_in=None):
    """Filter to a pool of eligible players.
    
    Args:
        played_in: tuple (start, end) — require player to have played at least one season 
                   where yearID falls within [start, end].
    """
    # Calculate basic career stats per player
    career = batting.groupby("playerID").agg(
        total_G=("G", "sum"),
        total_AB=("AB", "sum"),
        total_H=("H", "sum"),
        total_HR=("HR", "sum"),
        num_seasons=("yearID", "nunique"),
        first_year=("yearID", "min"),
        last_year=("yearID", "max"),
    ).reset_index()

    # Rough PA filter (AB is close enough for filtering)
    career = career[career["total_AB"] >= min_pa]

    if min_years:
        career = career[career["num_seasons"] >= min_years]

    if era:
        start, end = era
        career = career[(career["first_year"] >= start) & (career["first_year"] <= end)]

    if played_in:
        start, end = played_in
        # Player's career must overlap with the range: last_year >= start AND first_year <= end
        career = career[(career["last_year"] >= start) & (career["first_year"] <= end)]

    # Merge with people to get names
    career = career.merge(people[["playerID", "nameFirst", "nameLast", "debut"]], on="playerID", how="left")
    career["full_name"] = career["nameFirst"].fillna("") + " " + career["nameLast"].fillna("")

    # Filter out players with missing names
    career = career.dropna(subset=["nameFirst", "nameLast"])

    return career


def _derive_position_string(appearances_df, player_id, year, team_id):
    """
    Derive a Baseball Reference-style position string from Appearances.csv.
    
    Format examples: *8/DH, 9/7H, *6, DH, 1/DH
    The primary position gets a * prefix. Positions are listed by most games played.
    
    Appearances.csv columns for positions:
      G_p (pitcher), G_c (catcher), G_1b, G_2b, G_3b, G_ss,
      G_lf, G_cf, G_rf, G_dh, G_ph, G_pr, G_of (outfield generic)
    """
    if appearances_df is None:
        return ""

    # Position column mapping: column name -> display code
    # Using Baseball Reference numeric codes: 1=P, 2=C, 3=1B, 4=2B, 5=3B, 6=SS, 7=LF, 8=CF, 9=RF, D=DH, H=PH, R=PR
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
        ("G_of", "O"),    # Outfield (generic, used when specific OF not available)
    ]
    
    # Find this player/year/team row(s)
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
    
    # Sum games across all matching rows (in case of multiple entries)
    pos_games = {}
    for col, code in POS_MAP:
        if col in rows.columns:
            total = rows[col].fillna(0).sum()
            if total > 0:
                pos_games[code] = int(total)
    
    if not pos_games:
        return ""
    
    # If we have generic "O" (outfield) but not specific OF positions, use it
    # If we have specific OF positions, drop generic "O"
    has_specific_of = any(pos_games.get(c, 0) > 0 for c in ("7", "8", "9"))
    if has_specific_of and "O" in pos_games:
        del pos_games["O"]
    
    # Sort by games played descending
    sorted_pos = sorted(pos_games.items(), key=lambda x: -x[1])
    
    # Build the string: primary position gets *, then /separated others
    # Only include positions with meaningful playing time (skip PH/PR which aren't in our map)
    # Skip positions with very few games relative to primary
    primary_code = sorted_pos[0][0]
    primary_games = sorted_pos[0][1]
    
    parts = []
    for code, games in sorted_pos:
        # Skip positions with < 5% of total games (unless it's the primary)
        if len(parts) > 0 and games < 3:
            continue
        # Cap at 4 positions to keep it readable
        if len(parts) >= 4:
            break
        parts.append(code)
    
    if not parts:
        return ""
    
    # Primary position gets * prefix (Baseball Reference convention)
    result = "*" + parts[0]
    if len(parts) > 1:
        result += "/" + "/".join(parts[1:])
    
    # Replace "O" with "OF" for display if it's still there
    result = result.replace("O", "OF")
    # Replace "D" with "DH" for display
    result = result.replace("D", "DH")
    
    return result


def get_player_seasons(batting, people, awards_df, allstar_df, player_id, appearances_df=None, awards_share_df=None):
    """Get year-by-year batting stats for a player, with awards and positions."""
    pdf = batting[batting["playerID"] == player_id].copy()
    pdf = pdf.sort_values("yearID")

    person = people[people["playerID"] == player_id].iloc[0]
    name = f"{person['nameFirst']} {person['nameLast']}"

    # Calculate age (approximate from birthYear)
    birth_year = person.get("birthYear", None)

    # Build season rows
    seasons = []
    for _, row in pdf.iterrows():
        def safe_int(val):
            """Convert to int, treating NaN/None as 0."""
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return 0
            return int(val)

        year = int(row["yearID"])
        team = row.get("teamID", "???")
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
        SH   = safe_int(row.get("SH", 0))

        # Compute rate stats
        BA  = H / AB if AB > 0 else 0
        # OBP = (H+BB+HBP) / (AB+BB+HBP+SF)
        obp_denom = AB + BB + HBP + SF
        OBP = (H + BB + HBP) / obp_denom if obp_denom > 0 else 0
        TB  = H + _2B + 2 * _3B + 3 * HR
        SLG = TB / AB if AB > 0 else 0
        OPS = OBP + SLG

        age = year - birth_year if birth_year and not pd.isna(birth_year) else ""

        # Awards for this player+year
        awards_list = []
        if allstar_df is not None:
            if ((allstar_df["playerID"] == player_id) & (allstar_df["yearID"] == year)).any():
                awards_list.append("AS")

        # MVP and Cy Young vote rankings from AwardsSharePlayers
        # This gives us "MVP-3" style labels instead of just "MVP" for winners only
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

        # Add MVP with ranking
        if mvp_rank is not None:
            if mvp_rank == 1:
                awards_list.append("MVP")
            else:
                awards_list.append(f"MVP-{mvp_rank}")
        
        # Add Cy Young with ranking
        if cy_rank is not None:
            if cy_rank == 1:
                awards_list.append("CY")
            else:
                awards_list.append(f"CY-{cy_rank}")

        # Gold Glove, Silver Slugger, ROY from AwardsPlayers (winners only, no ranking)
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

        # Position string from Appearances
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


def compute_totals(seasons):
    """Compute career totals row from list of season dicts."""
    keys_sum = ["G","AB","R","H","2B","3B","HR","RBI","SB","CS","BB","SO"]
    totals = {k: sum(s[k] for s in seasons) for k in keys_sum}
    AB = totals["AB"]
    H  = totals["H"]
    BB = totals["BB"]
    totals["BA"]  = H / AB if AB > 0 else 0
    PA = AB + BB  # simplified for totals
    totals["OBP"] = (H + BB) / PA if PA > 0 else 0
    TB = H + totals["2B"] + 2 * totals["3B"] + 3 * totals["HR"]
    totals["SLG"] = TB / AB if AB > 0 else 0
    totals["OPS"] = totals["OBP"] + totals["SLG"]
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

COLUMNS = [
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


def fmt_val(col, val):
    """Format a value for display."""
    if col in ("BA", "OBP", "SLG", "OPS"):
        if val == 0:
            return ".000"
        return f"{val:.3f}".lstrip("0")
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


def render_stats_image(seasons, output_path, show_name=None):
    """
    Render year-by-year stats as a Baseball Reference-style PNG.
    If show_name is provided, it appears at the top (for reveal).
    """
    totals = compute_totals(seasons)
    num_rows = len(seasons) + 1  # +1 for totals

    # Calculate dimensions
    col_widths = [c[1] for c in COLUMNS]
    total_width_chars = sum(col_widths)
    
    # Figure sizing
    char_width = 0.115  # inches per character-width unit
    fig_width = total_width_chars * char_width + 0.8  # padding
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

    # ── Title area ──
    y_cursor -= title_height
    if show_name:
        ax.text(0.3, y_cursor + 0.15, show_name,
                fontsize=16, fontweight="bold", color=BR_LINK,
                fontfamily="serif", va="bottom")
    else:
        ax.text(0.3, y_cursor + 0.15, "??? ???",
                fontsize=16, fontweight="bold", color="#999999",
                fontfamily="serif", va="bottom")

    # ── Section header bar ("Standard Batting") ──
    y_cursor -= section_header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, section_header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)
    ax.text(0.3, y_cursor + section_header_height / 2, "Standard Batting",
            fontsize=9, fontweight="bold", color=BR_TEXT,
            fontfamily="sans-serif", va="center")
    ax.text(4.5, y_cursor + section_header_height / 2, "Regular Season",
            fontsize=7, color="#666", fontfamily="sans-serif", va="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor="#f0f0f0", edgecolor="#bbb", linewidth=0.5))

    # ── Column headers ──
    y_cursor -= header_height
    rect = plt.Rectangle((0, y_cursor), fig_width, header_height,
                          facecolor=BR_HEADER_BG, edgecolor=BR_BORDER, linewidth=0.5)
    ax.add_patch(rect)

    # Red line under header
    ax.plot([0, fig_width], [y_cursor, y_cursor], color=BR_RED, linewidth=1.5)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS:
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

    # ── Data rows ──
    for row_idx, season in enumerate(seasons):
        y_cursor -= row_height
        bg = BR_BG if row_idx % 2 == 0 else BR_BG_ALT
        rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                              facecolor=bg, edgecolor="none")
        ax.add_patch(rect)
        # Bottom border
        ax.plot([0, fig_width], [y_cursor, y_cursor], color="#e0ddd5", linewidth=0.3)

        x = 0.3
        for col_name, col_w, col_align in COLUMNS:
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

            # Styling
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

    # ── Totals row ──
    y_cursor -= row_height
    # Red line on top of totals
    ax.plot([0, fig_width], [y_cursor + row_height, y_cursor + row_height], color=BR_RED, linewidth=1.5)
    rect = plt.Rectangle((0, y_cursor), fig_width, row_height,
                          facecolor="#e8e5d8", edgecolor="none")
    ax.add_patch(rect)

    x = 0.3
    for col_name, col_w, col_align in COLUMNS:
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


# ─── Game Logic ──────────────────────────────────────────────────────────────

def play_game(data_dir, min_war=None, min_years=None, era=None, min_pa=1000,
              output_dir=None):
    """Main game loop."""
    print("\n" + "=" * 60)
    print("  ⚾  NAME THAT BALLPLAYER  ⚾")
    print("=" * 60)
    print("Loading Lahman database...")

    batting, people, awards_df, allstar_df, appearances_df, awards_share_df = load_data(data_dir)

    pool = get_player_pool(batting, people, min_war=min_war,
                           min_years=min_years, era=era, min_pa=min_pa)

    if len(pool) == 0:
        print("No players match your filters. Try relaxing constraints.")
        sys.exit(1)

    print(f"Player pool: {len(pool)} eligible players")

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
        name, seasons = get_player_seasons(batting, people, awards_df, allstar_df, pid, appearances_df, awards_share_df)

        if len(seasons) == 0:
            continue

        # Filter out seasons with 0 AB (pitchers appearing briefly, etc.)
        seasons = [s for s in seasons if s["AB"] > 0]
        if len(seasons) == 0:
            continue

        # Render the mystery image
        img_path = os.path.join(output_dir, "current_player.png")
        render_stats_image(seasons, img_path, show_name=None)

        print(f"\n{'─' * 60}")
        print(f"  Round {round_num}  |  Score: {score_correct}/{score_total}  |  Streak: {streak}  |  Best: {best_streak}")
        print(f"{'─' * 60}")
        print(f"  Stats image saved to: {img_path}")
        print(f"  Open it and study the stats!")
        print()

        # Hint tracking
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
                # Save revealed image
                reveal_path = os.path.join(output_dir, "revealed_player.png")
                render_stats_image(seasons, reveal_path, show_name=name)
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
                    print(f"  💡 No more hints! (initials, first name, and partial already given)")
                continue

            # Check guess
            def normalize(s):
                return "".join(c for c in s.lower() if c.isalpha())

            if normalize(user_input) == normalize(name):
                print(f"\n  ✅ Correct! It's {name}!")
                reveal_path = os.path.join(output_dir, "revealed_player.png")
                render_stats_image(seasons, reveal_path, show_name=name)
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
              python game.py --data-dir ./baseballdatabank/core
              python game.py --data-dir ./core --min-years 10 --min-pa 3000
              python game.py --data-dir ./core --era 1980-2010
        """),
    )
    parser.add_argument("--data-dir", required=True,
                        help="Path to folder containing Lahman CSVs (Batting.csv, People.csv, etc.)")
    parser.add_argument("--min-years", type=int, default=5,
                        help="Minimum career seasons (default: 5)")
    parser.add_argument("--min-pa", type=int, default=1500,
                        help="Minimum career AB to be eligible (default: 1500)")
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
        min_years=args.min_years,
        era=era,
        min_pa=args.min_pa,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
