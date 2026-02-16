# ⚾ Name That Ballplayer

A baseball stats guessing game that generates Baseball Reference–style stat images from the full Lahman Database. Study the year-by-year stats, teams, and awards – then guess the player!

**NEW:** Now supports both **batting** and **pitching** stats!

## Setup (5 minutes)

### 1. Clone/download this project

### 2. Get the Lahman Database

```bash
git clone https://github.com/chadwickbureau/baseballdatabank.git
```

Or download directly from: https://www.seanlahman.com/baseball-archive/statistics/

This gives you CSVs including:
- `Batting.csv` – all batting stats
- `Pitching.csv` – all pitching stats
- `People.csv` – player names, birth years
- `AwardsPlayers.csv` – MVP, GG, SS, ROY, CY awards
- `AllstarFull.csv` – All-Star appearances

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Play!

**Option A: Web version (recommended)**

```bash
python web_game.py --data-dir ./baseballdatabank/core
```

Then open **http://localhost:5050** in your browser.

**Option B: Terminal version**

```bash
python game.py --data-dir ./baseballdatabank/core --mode batting
```

The terminal version saves PNG images to `./output/` that you open manually.

## Game Modes

### Batting Mode (default)
Shows year-by-year batting stats: AB, H, HR, RBI, BA, OBP, SLG, OPS, etc.

```bash
python web_game.py --data-dir ./baseballdatabank/core
```

### Pitching Mode
Shows year-by-year pitching stats: W, L, ERA, IP, SO, WHIP, etc.

```bash
python game.py --data-dir ./baseballdatabank/core --mode pitching
```

### Both Mode
Randomly shows either batting or pitching stats for eligible two-way players and specialists.

```bash
python game.py --data-dir ./baseballdatabank/core --mode both
```

## Options & Filters

Both versions support these flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--data-dir` | (required) | Path to Lahman `core/` folder |
| `--mode` | batting | Game mode: `batting`, `pitching`, or `both` |
| `--min-years` | 5 | Minimum career seasons |
| `--min-pa` | 1500 | Minimum career plate appearances (batters) |
| `--min-ip` | 1000 | Minimum career innings pitched (pitchers) |
| `--era` | all | Debut year range, e.g. `1980-2010` |
| `--output-dir` | `./output` | Where to save generated PNGs |
| `--port` | 5050 | Web version port (web_game.py only) |

### Examples

```bash
# Batters only from 1990-2020
python web_game.py --data-dir ./baseballdatabank/core --mode batting --era 1990-2020

# Pitchers only with 1500+ IP
python web_game.py --data-dir ./baseballdatabank/core --mode pitching --min-ip 1500

# Both batters and pitchers
python web_game.py --data-dir ./baseballdatabank/core --mode both

# Classic era pitchers
python game.py --data-dir ./baseballdatabank/core --mode pitching --era 1950-1980

# Long-career batters (10+ years, 3000+ AB)
python web_game.py --data-dir ./baseballdatabank/core --mode batting --min-years 10 --min-pa 3000
```

## How to Play

1. A Baseball Reference–style stat table image is shown (player name hidden)
2. Study the year-by-year stats: teams, awards, career arc, counting stats, rate stats
3. Type your guess
4. Use **Hint** for progressive clues (initials → first name → partial last name)
5. **Give Up** reveals the answer
6. Track your score and streak!

## Web Version Features

The web version includes:
- 🎨 Beautiful, modern UI with gradient backgrounds and smooth animations
- 🎮 In-browser filters for mode, seasons, AB/IP minimums, and era ranges
- 📊 Real-time score tracking with streak indicators
- 🔄 Easy mode switching between batting and pitching
- 📱 Fully responsive design

## Project Structure

```
name-that-ballplayer/
├── game.py           # Core engine: data loading, image rendering, CLI game
├── web_game.py       # Flask web UI (imports from game.py)
├── requirements.txt
├── README.md
└── output/           # Generated images (created automatically)
```

## How the Images Work

The rendering functions use matplotlib to draw pixel-perfect tables that mimic the Baseball Reference layout:

### Batting Stats
- Columns: Year, Age, Tm, Lg, G, AB, R, H, 2B, 3B, HR, RBI, SB, CS, BB, SO, BA, OBP, SLG, OPS, Pos, Awards
- Highlighted: 30+ HR, 30+ SB, .900+ OPS

### Pitching Stats
- Columns: Year, Age, Tm, Lg, W, L, ERA, G, GS, CG, SHO, SV, IP, H, ER, HR, BB, SO, WHIP, Awards
- Highlighted: 20+ W, 200+ SO, ERA ≤ 3.00

### Common Features
- Alternating row backgrounds (#f7f7f0 / #ffffff)
- Red header/totals borders
- Blue link-colored Year/Team/League columns
- Bold rate stats
- Career totals row at bottom
- Awards column (AS, MVP, CY, GG, SS, ROY with vote rankings)

## What's New in This Version

✨ **Pitching Support**: Full pitching stats with ERA, WHIP, IP, strikeouts, and more
🎯 **Three Game Modes**: Play with batters, pitchers, or both
🎨 **Enhanced UI**: Modern gradient design with smooth animations
📈 **Better Filtering**: Separate controls for batting (min AB) and pitching (min IP)
🏆 **Cy Young Awards**: Now displays Cy Young award winners and vote rankings
⚡ **Smart Player Detection**: Automatically determines if a player is primarily a batter or pitcher

## Tips for Playing

- **Look at team changes**: Trades and free agency moves can identify specific eras
- **Check awards**: MVP, Cy Young, All-Star selections narrow it down significantly
- **Watch for career arcs**: Breakout years, decline phases, and peak performance windows
- **For pitchers**: Look for signature seasons (no-hitters show up as low ERA/WHIP combos)
- **Use the era filter**: Narrow to decades you know best

## Requirements

- Python 3.7+
- pandas
- matplotlib
- Pillow
- flask (for web version)

## License

Open source - feel free to modify and share!
