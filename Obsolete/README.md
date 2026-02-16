# ⚾ Name That Ballplayer

A baseball stats guessing game that generates Baseball Reference–style stat images from the full Lahman Database. Study the year-by-year stats, teams, and awards — then guess the player!

## Setup (5 minutes)

### 1. Clone/download this project

### 2. Get the Lahman Database

```bash
git clone https://github.com/chadwickbureau/baseballdatabank.git
```

This gives you a `baseballdatabank/core/` folder with CSVs including:
- `Batting.csv` — all batting stats
- `People.csv` — player names, birth years
- `AwardsPlayers.csv` — MVP, GG, SS, ROY awards
- `AllstarFull.csv` — All-Star appearances

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
python game.py --data-dir ./baseballdatabank/core
```

The terminal version saves PNG images to `./output/` that you open manually.

## Options & Filters

Both versions support these flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--data-dir` | (required) | Path to Lahman `core/` folder |
| `--min-years` | 5 | Minimum career seasons |
| `--min-pa` | 1500 | Minimum career at-bats |
| `--era` | all | Debut year range, e.g. `1980-2010` |
| `--output-dir` | `./output` | Where to save generated PNGs |
| `--port` | 5050 | Web version port (web_game.py only) |

### Examples

```bash
# Only players who debuted 1990-2020
python web_game.py --data-dir ./baseballdatabank/core --era 1990-2020

# Only long-career players (10+ years, 3000+ AB)
python web_game.py --data-dir ./baseballdatabank/core --min-years 10 --min-pa 3000

# Classic era players
python web_game.py --data-dir ./baseballdatabank/core --era 1950-1980
```

## How to Play

1. A Baseball Reference–style stat table image is shown (player name hidden)
2. Study the year-by-year stats: teams, awards, career arc, counting stats, rate stats
3. Type your guess
4. Use **Hint** for progressive clues (initials → first name → partial last name)
5. **Give Up** reveals the answer
6. Track your score and streak!

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

The `render_stats_image()` function in `game.py` uses matplotlib to draw a pixel-perfect table that mimics the Baseball Reference layout:

- Same column order: Year, Age, Tm, Lg, G, AB, R, H, 2B, 3B, HR, RBI, SB, CS, BB, SO, BA, OBP, SLG, OPS, Awards
- Alternating row backgrounds (#f7f7f0 / #ffffff)
- Red header/totals borders
- Blue link-colored Year/Team/League columns
- Bold rate stats, highlighted 30+ HR, 30+ SB, .900+ OPS
- Career totals row at bottom
- Awards column (AS, MVP, GG, SS, ROY)
