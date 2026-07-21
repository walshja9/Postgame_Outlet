# PGO Team Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shadow-only Postgame Outlet team-level NFL rating model whose historical game-margin backtest must pass before its ratings can be considered for product integration.

**Architecture:** Add one standard-library Python script that reads completed regular-season team results from a pinned nflverse schedule snapshot, trains a transparent online margin rating, and evaluates it chronologically against a separately tuned home-field-only baseline. Keep the model independent from Sean McCabe's QB/offense/defense inputs and from market lines; write only versioned research receipts under `research/pgo/` and stop before any site, Shopify, or prediction-surface integration.

**Tech Stack:** Python 3 standard library (`argparse`, `csv`, `dataclasses`, `hashlib`, `json`, `urllib`), `unittest`, pinned nflverse `games.csv` data.

## Global Constraints

- Work only on `codex/pgo-team-model` in the isolated worktree `C:\Users\Alex\Postgame_Outlet-pgo-model`.
- The PGO model is team-level only. It must not read, reproduce, or replace Sean McCabe's `qb_value`, `off_value`, or `def_value` structure.
- The model may consume only completed regular-season game identity, date, teams, scores, and neutral-site status.
- Market and odds fields, including nflverse `spread_line`, remain deferred and unused.
- The held-out backtest is a hard gate: no ratings receipt is written unless the model beats the home-field-only baseline in aggregate and in every evaluation season from 2018 through 2025.
- Hyperparameters are selected only on 2002-2017 games after a 1999-2001 warm-up; 2018-2025 remains untouched holdout evidence.
- Require at least 2,000 held-out games and all 32 current franchises before the gate can pass.
- Keep outputs shadow-only under `research/pgo/`. Do not modify or import them into `data/ratings.csv`, `generate_site.py`, `docs/index.html`, Shopify, GitHub Pages, redirects, analytics, or production content.
- Do not add a dependency, notebook, framework, database, service, scheduled workflow, market comparison, or public UI.
- Do not push, publish, deploy, or change any live service.

---

## File Map

- Create `pgo_model.py`: source validation, team alias normalization, online team-margin rating, pre-2018 parameter selection, held-out evaluation, gate, and deterministic research-output CLI.
- Create `tests/test_pgo_model.py`: focused regression tests for market-free parsing, no-lookahead updates, offseason regression, holdout isolation, and fail-closed output.
- Create `research/pgo/backtest.json`: deterministic gate receipt tied to the pinned source commit and SHA-256.
- Create `research/pgo/ratings_2026_preseason.csv`: shadow ratings written only after the gate passes.
- Modify `README.md`: document the independent shadow command and its hard boundaries.
- Preserve unchanged: `data/**`, `generate_site.py`, `release_ratings.py`, `snapshot.py`, `spreads.py`, `docs/index.html`, `shopify-theme/**`, and `.github/workflows/**`.

## Fixed Research Contract

- Source: `https://raw.githubusercontent.com/nflverse/nfldata/29102e4f32febb597750c71a27f22fb2898e3cfc/data/games.csv`
- Source commit: `29102e4f32febb597750c71a27f22fb2898e3cfc`
- Expected source SHA-256: `cfb9c79a28ac1187a44be0bcfa0d8ff2f5a7ca201c5183a1dbf1e6d227d72f39`
- Franchise aliases: `OAK -> LV`, `SD -> LAC`, `STL -> LAR`, `LA -> LAR`.
- Prediction: `home_rating - away_rating + home_field`, with home field set to zero at neutral sites.
- Update after prediction: clip the margin residual, then move the two team ratings equally in opposite directions.
- Parameter candidates:
  - learning rate: `0.10, 0.15, 0.20, 0.25, 0.30`
  - offseason retention: `0.50, 0.60, 0.70, 0.80, 0.90`
  - home field: `1.5, 2.0, 2.5, 3.0`
  - residual cap: `20, 28, 35, 1000`
- Gate baseline: the best home-field-only predictor selected on 2002-2017 from the same home-field candidates.
- Expected pinned-data result: 2,127 holdout games; model MAE `10.2662`; independently tuned baseline MAE `11.0790`; model better in all eight holdout seasons.

### Task 1: Add the market-free team model core

**Files:**
- Create: `tests/test_pgo_model.py`
- Create: `pgo_model.py`

**Interfaces:**
- Produces: `Game`, `Parameters`, and `Prediction` immutable dataclasses.
- Produces: `parse_games(text, first_season=1999, last_season=2025) -> list[Game]`.
- Produces: `walk_forward(games, parameters) -> tuple[list[Prediction], dict[str, float]]`.
- Consumes only the nine fields listed in `REQUIRED_COLUMNS`; all odds and player/unit fields are ignored.

- [ ] **Step 1: Write failing parser and no-lookahead tests**

Create `tests/test_pgo_model.py` with a CSV helper and these tests:

```python
import csv
import io
import tempfile
import unittest
from pathlib import Path

import pgo_model


FIELDS = [
    "game_id", "season", "game_type", "gameday", "away_team",
    "away_score", "home_team", "home_score", "location", "spread_line",
]


def games_csv(rows):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def row(game_id, season, away, away_score, home, home_score, **overrides):
    value = {
        "game_id": game_id,
        "season": season,
        "game_type": "REG",
        "gameday": f"{season}-09-01",
        "away_team": away,
        "away_score": away_score,
        "home_team": home,
        "home_score": home_score,
        "location": "Home",
        "spread_line": "-99.5",
    }
    value.update(overrides)
    return value


class ParsingTests(unittest.TestCase):
    def test_uses_only_completed_regular_season_team_results(self):
        text = games_csv([
            row("one", 2025, "OAK", 10, "SD", 20),
            row("two", 2025, "A", 10, "B", 20, game_type="POST"),
            row("three", 2025, "A", "", "B", ""),
        ])

        games = pgo_model.parse_games(text)

        self.assertEqual(len(games), 1)
        self.assertEqual((games[0].away, games[0].home), ("LV", "LAC"))
        self.assertEqual(games[0].margin, 10.0)

    def test_market_line_does_not_change_parsed_game(self):
        first = row("one", 2025, "A", 10, "B", 20, spread_line="-2.5")
        second = {**first, "spread_line": "+12.5"}
        self.assertEqual(
            pgo_model.parse_games(games_csv([first])),
            pgo_model.parse_games(games_csv([second])),
        )


class WalkForwardTests(unittest.TestCase):
    def test_prediction_is_recorded_before_result_update(self):
        games = [
            pgo_model.Game("one", 2020, "2020-09-01", "B", "A", 12.0, False),
            pgo_model.Game("two", 2020, "2020-09-08", "B", "A", 0.0, False),
        ]
        params = pgo_model.Parameters(0.2, 0.5, 2.0, 20.0)

        predictions, _ = pgo_model.walk_forward(games, params)

        self.assertEqual(predictions[0].predicted, 2.0)
        self.assertEqual(predictions[1].predicted, 4.0)

    def test_new_season_regresses_existing_ratings(self):
        games = [
            pgo_model.Game("one", 2020, "2020-09-01", "B", "A", 12.0, False),
            pgo_model.Game("two", 2021, "2021-09-01", "B", "A", 0.0, False),
        ]
        params = pgo_model.Parameters(0.2, 0.5, 2.0, 20.0)

        predictions, _ = pgo_model.walk_forward(games, params)

        self.assertEqual(predictions[1].predicted, 3.0)
```

- [ ] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_model -v
```

Expected: import error because `pgo_model.py` does not exist.

- [ ] **Step 3: Implement the smallest team-only core**

Create `pgo_model.py` with:

```python
#!/usr/bin/env python3
"""Shadow-only Postgame Outlet team-margin model and backtest gate."""

import argparse
import csv
import hashlib
import io
import itertools
import json
import sys
import urllib.request
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from release_ratings import atomic_write_text


SOURCE_COMMIT = "29102e4f32febb597750c71a27f22fb2898e3cfc"
SOURCE_URL = (
    "https://raw.githubusercontent.com/nflverse/nfldata/"
    f"{SOURCE_COMMIT}/data/games.csv"
)
EXPECTED_SOURCE_SHA256 = (
    "cfb9c79a28ac1187a44be0bcfa0d8ff2f5a7ca201c5183a1dbf1e6d227d72f39"
)
ALIASES = {"OAK": "LV", "SD": "LAC", "STL": "LAR", "LA": "LAR"}
REQUIRED_COLUMNS = {
    "game_id", "season", "game_type", "gameday", "away_team",
    "away_score", "home_team", "home_score", "location",
}


@dataclass(frozen=True)
class Game:
    game_id: str
    season: int
    gameday: str
    away: str
    home: str
    margin: float
    neutral: bool


@dataclass(frozen=True, order=True)
class Parameters:
    learning_rate: float
    offseason_retention: float
    home_field: float
    margin_cap: float


@dataclass(frozen=True)
class Prediction:
    game_id: str
    season: int
    actual: float
    predicted: float


def parse_games(text, first_season=1999, last_season=2025):
    reader = csv.DictReader(io.StringIO(text))
    missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
    if missing:
        raise ValueError("Missing game columns: " + ", ".join(sorted(missing)))
    games, seen = [], set()
    for row in reader:
        if row["game_type"] != "REG" or not row["home_score"] or not row["away_score"]:
            continue
        season = int(row["season"])
        if not first_season <= season <= last_season:
            continue
        game_id = row["game_id"]
        if game_id in seen:
            raise ValueError(f"Duplicate completed game: {game_id}")
        seen.add(game_id)
        home = ALIASES.get(row["home_team"], row["home_team"])
        away = ALIASES.get(row["away_team"], row["away_team"])
        if not home or not away or home == away:
            raise ValueError(f"Invalid teams for {game_id}")
        games.append(Game(
            game_id,
            season,
            row["gameday"],
            away,
            home,
            float(row["home_score"]) - float(row["away_score"]),
            row["location"].strip().lower() == "neutral",
        ))
    if not games:
        raise ValueError("No completed regular-season games found")
    return sorted(games, key=lambda game: (game.gameday, game.game_id))


def walk_forward(games, parameters):
    ratings = defaultdict(float)
    predictions = []
    current_season = None
    for game in games:
        if current_season is not None and game.season != current_season:
            seasons = game.season - current_season
            for team in ratings:
                ratings[team] *= parameters.offseason_retention ** seasons
        current_season = game.season
        home_field = 0.0 if game.neutral else parameters.home_field
        predicted = ratings[game.home] - ratings[game.away] + home_field
        predictions.append(Prediction(
            game.game_id, game.season, game.margin, predicted,
        ))
        residual = max(
            -parameters.margin_cap,
            min(parameters.margin_cap, game.margin - predicted),
        )
        change = parameters.learning_rate * residual / 2
        ratings[game.home] += change
        ratings[game.away] -= change
    return predictions, dict(ratings)
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_pgo_model -v
```

Expected: four tests pass.

- [ ] **Step 5: Commit the team-model core**

```powershell
git add pgo_model.py tests/test_pgo_model.py
git commit -m "Add shadow PGO team model core"
```

### Task 2: Add the chronological backtest gate

**Files:**
- Modify: `pgo_model.py`
- Modify: `tests/test_pgo_model.py`

**Interfaces:**
- Produces: `select_parameters(games) -> Parameters`, trained only through 2017.
- Produces: `build_analysis(games) -> tuple[dict, list[dict]]`.
- Produces: `gate_checks(aggregate, seasons, team_count) -> dict[str, bool]`.
- The ratings list is the 2026 preseason shadow state after one additional offseason regression.

- [ ] **Step 1: Add failing holdout-isolation and fail-closed gate tests**

Append:

```python
class GateTests(unittest.TestCase):
    def test_parameter_search_ignores_holdout_results(self):
        before = [
            pgo_model.Game("train", 2017, "2017-09-01", "B", "A", 10.0, False),
        ]
        good_holdout = pgo_model.Game(
            "holdout", 2018, "2018-09-01", "B", "A", 50.0, False,
        )
        bad_holdout = pgo_model.Game(
            "holdout", 2018, "2018-09-01", "B", "A", -50.0, False,
        )
        self.assertEqual(
            pgo_model.select_parameters(before + [good_holdout]),
            pgo_model.select_parameters(before + [bad_holdout]),
        )

    def test_gate_requires_aggregate_and_every_season_to_win(self):
        aggregate = {"games": 2127, "model_mae": 10.0, "baseline_mae": 11.0}
        seasons = [
            {"season": 2018, "model_mae": 10.0, "baseline_mae": 11.0},
            {"season": 2019, "model_mae": 11.1, "baseline_mae": 11.0},
        ]
        checks = pgo_model.gate_checks(aggregate, seasons, 32)
        self.assertTrue(checks["aggregate_beats_baseline"])
        self.assertFalse(checks["every_season_beats_baseline"])
        self.assertFalse(all(checks.values()))
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m unittest tests.test_pgo_model.GateTests -v
```

Expected: errors for missing `select_parameters` and `gate_checks`.

- [ ] **Step 3: Implement training-only selection, metrics, and gate**

Add constants and functions to `pgo_model.py`:

```python
TRAIN_START, TRAIN_END = 2002, 2017
EVAL_START, EVAL_END = 2018, 2025
CURRENT_TEAMS = tuple(sorted(
    "ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR "
    "LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split()
))
LEARNING_RATES = (0.10, 0.15, 0.20, 0.25, 0.30)
OFFSEASON_RETENTIONS = (0.50, 0.60, 0.70, 0.80, 0.90)
HOME_FIELDS = (1.5, 2.0, 2.5, 3.0)
MARGIN_CAPS = (20.0, 28.0, 35.0, 1000.0)


def mean_absolute_error(predictions, first_season, last_season):
    errors = [
        abs(value.actual - value.predicted)
        for value in predictions
        if first_season <= value.season <= last_season
    ]
    if not errors:
        raise ValueError("No predictions in requested evaluation window")
    return sum(errors) / len(errors), len(errors)


def select_parameters(games):
    training_games = [game for game in games if game.season <= TRAIN_END]
    candidates = []
    for values in itertools.product(
        LEARNING_RATES, OFFSEASON_RETENTIONS, HOME_FIELDS, MARGIN_CAPS,
    ):
        parameters = Parameters(*values)
        predictions, _ = walk_forward(training_games, parameters)
        score, _ = mean_absolute_error(predictions, TRAIN_START, TRAIN_END)
        candidates.append((score, parameters))
    return min(candidates)[1]


def select_baseline_home_field(games):
    training = [game for game in games if TRAIN_START <= game.season <= TRAIN_END]
    return min(
        (
            sum(abs(game.margin - (0.0 if game.neutral else value)) for game in training)
            / len(training),
            value,
        )
        for value in HOME_FIELDS
    )[1]


def baseline_predictions(games, home_field):
    return [
        Prediction(
            game.game_id,
            game.season,
            game.margin,
            0.0 if game.neutral else home_field,
        )
        for game in games
    ]


def evaluation_metrics(model, baseline):
    aggregate_model, count = mean_absolute_error(model, EVAL_START, EVAL_END)
    aggregate_baseline, _ = mean_absolute_error(baseline, EVAL_START, EVAL_END)
    seasons = []
    for season in range(EVAL_START, EVAL_END + 1):
        model_mae, games = mean_absolute_error(model, season, season)
        baseline_mae, _ = mean_absolute_error(baseline, season, season)
        seasons.append({
            "season": season,
            "games": games,
            "model_mae": round(model_mae, 4),
            "baseline_mae": round(baseline_mae, 4),
            "improvement": round(baseline_mae - model_mae, 4),
        })
    aggregate = {
        "games": count,
        "model_mae": round(aggregate_model, 4),
        "baseline_mae": round(aggregate_baseline, 4),
        "improvement": round(aggregate_baseline - aggregate_model, 4),
    }
    return aggregate, seasons


def gate_checks(aggregate, seasons, team_count):
    return {
        "at_least_2000_holdout_games": aggregate["games"] >= 2000,
        "all_32_current_teams": team_count == 32,
        "aggregate_beats_baseline": (
            aggregate["model_mae"] < aggregate["baseline_mae"]
        ),
        "every_season_beats_baseline": all(
            season["model_mae"] < season["baseline_mae"]
            for season in seasons
        ),
    }


def build_analysis(games):
    parameters = select_parameters(games)
    baseline_home_field = select_baseline_home_field(games)
    model_predictions, ratings = walk_forward(games, parameters)
    baseline = baseline_predictions(games, baseline_home_field)
    aggregate, seasons = evaluation_metrics(model_predictions, baseline)
    shadow = [
        {
            "team": team,
            "rating": round(
                ratings.get(team, 0.0) * parameters.offseason_retention,
                3,
            ),
        }
        for team in CURRENT_TEAMS
        if team in ratings
    ]
    shadow.sort(key=lambda row: (-row["rating"], row["team"]))
    checks = gate_checks(aggregate, seasons, len(shadow))
    report = {
        "format_version": 1,
        "model": "PGO team margin v0",
        "status": "PASS" if all(checks.values()) else "HOLD",
        "scope": {
            "included": "completed regular-season team results",
            "excluded": [
                "Sean McCabe QB/offense/defense ratings",
                "player and unit inputs",
                "market spreads and odds",
            ],
        },
        "windows": {
            "warmup": "1999-2001",
            "training": "2002-2017",
            "evaluation": "2018-2025",
            "ratings": "2026 preseason",
        },
        "parameters": asdict(parameters),
        "baseline": {"home_field": baseline_home_field},
        "aggregate": aggregate,
        "seasons": seasons,
        "checks": checks,
    }
    return report, shadow
```

- [ ] **Step 4: Run the focused and full tests**

```powershell
python -m unittest tests.test_pgo_model -v
python -m unittest discover -s tests -v
```

Expected: all new tests and the existing 24 tests pass.

- [ ] **Step 5: Commit the backtest gate**

```powershell
git add pgo_model.py tests/test_pgo_model.py
git commit -m "Gate PGO ratings on held-out backtest"
```

### Task 3: Write deterministic shadow receipts only after PASS

**Files:**
- Modify: `pgo_model.py`
- Modify: `tests/test_pgo_model.py`
- Create: `research/pgo/backtest.json`
- Create: `research/pgo/ratings_2026_preseason.csv`

**Interfaces:**
- Produces: `read_source(location) -> tuple[bytes, str]`.
- Produces: `write_outputs(output_dir, report, ratings) -> bool`.
- CLI: `python pgo_model.py [--source URL_OR_PATH] [--output-dir PATH]`.
- Exit 0 means the gate passed and both receipts were written; exit 1 means HOLD and no ratings receipt was written.

- [ ] **Step 1: Add a failing fail-closed artifact test**

Append to `GateTests`:

```python
    def test_hold_writes_report_but_not_ratings(self):
        report = {"status": "HOLD"}
        with tempfile.TemporaryDirectory() as temp:
            written = pgo_model.write_outputs(Path(temp), report, [])
            self.assertFalse(written)
            self.assertTrue(Path(temp, "backtest.json").exists())
            self.assertFalse(Path(temp, "ratings_2026_preseason.csv").exists())
```

- [ ] **Step 2: Run the test and verify RED**

```powershell
python -m unittest tests.test_pgo_model.GateTests.test_hold_writes_report_but_not_ratings -v
```

Expected: error for missing `write_outputs`.

- [ ] **Step 3: Add pinned-source loading, atomic receipts, and CLI**

Append to `pgo_model.py`:

```python
def read_source(location):
    if location.startswith(("http://", "https://")):
        request = urllib.request.Request(
            location,
            headers={"User-Agent": "PostgameOutlet-PGO/0"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read(), location
    path = Path(location)
    return path.read_bytes(), str(path.resolve())


def ratings_csv(ratings):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=("rank", "team", "rating"))
    writer.writeheader()
    for rank, row in enumerate(ratings, 1):
        writer.writerow({"rank": rank, **row})
    return output.getvalue()


def write_outputs(output_dir, report, ratings):
    output_dir = Path(output_dir)
    atomic_write_text(
        output_dir / "backtest.json",
        json.dumps(report, indent=2, sort_keys=True) + "\n",
    )
    if report["status"] != "PASS":
        return False
    atomic_write_text(
        output_dir / "ratings_2026_preseason.csv",
        ratings_csv(ratings),
    )
    return True


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE_URL)
    parser.add_argument("--output-dir", default="research/pgo")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    raw, source = read_source(args.source)
    source_hash = hashlib.sha256(raw).hexdigest()
    if args.source == SOURCE_URL and source_hash != EXPECTED_SOURCE_SHA256:
        raise ValueError("Pinned nflverse source hash does not match")
    games = parse_games(raw.decode("utf-8-sig"))
    report, ratings = build_analysis(games)
    report["source"] = {
        "location": source,
        "commit": SOURCE_COMMIT if args.source == SOURCE_URL else "",
        "sha256": source_hash,
    }
    written = write_outputs(args.output_dir, report, ratings)
    aggregate = report["aggregate"]
    print(
        f"{report['status']}: PGO MAE {aggregate['model_mae']:.4f}; "
        f"baseline {aggregate['baseline_mae']:.4f}; "
        f"{aggregate['games']} holdout games"
    )
    return 0 if written else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
```

- [ ] **Step 4: Run the focused test and verify GREEN**

```powershell
python -m unittest tests.test_pgo_model.GateTests.test_hold_writes_report_but_not_ratings -v
```

Expected: pass.

- [ ] **Step 5: Run the pinned backtest and inspect receipts**

```powershell
python pgo_model.py
Get-Content -Raw research/pgo/backtest.json
Get-Content research/pgo/ratings_2026_preseason.csv -TotalCount 10
```

Expected: exit 0 and `PASS`; source hash matches the fixed contract; aggregate and all eight season checks pass; ratings contain 32 teams.

- [ ] **Step 6: Commit the reproducible receipts**

```powershell
git add pgo_model.py tests/test_pgo_model.py research/pgo/backtest.json research/pgo/ratings_2026_preseason.csv
git commit -m "Record PGO model backtest receipt"
```

### Task 4: Document the shadow boundary and verify production isolation

**Files:**
- Modify: `README.md`
- Verify unchanged: `data/**`, `generate_site.py`, `spreads.py`, `docs/index.html`, `.github/workflows/**`

**Interfaces:**
- Produces: one operator command and explicit language that PASS authorizes review only, not publication.

- [ ] **Step 1: Add the minimal README section**

Append before `## Notes & caveats`:

```markdown
## PGO team model (shadow only)

`python pgo_model.py` runs a pinned, chronological backtest of Postgame's
independent team-results model and writes its receipt under `research/pgo/`.
It does not read Sean McCabe's QB/offense/defense inputs or any market line.
A `PASS` makes the shadow ratings eligible for human review only; it does not
publish them or add them to the ratings site.
```

- [ ] **Step 2: Run all deterministic verification**

```powershell
python -m unittest discover -s tests -v
python -m py_compile pgo_model.py release_ratings.py generate_site.py snapshot.py spreads.py
python pgo_model.py
git diff --exit-code main -- data generate_site.py spreads.py docs/index.html .github/workflows
```

Expected: all tests pass; compilation succeeds; the pinned backtest prints `PASS`; the production-isolation diff exits 0.

- [ ] **Step 3: Verify the exact branch scope**

```powershell
git status --short
git diff --stat main
git diff --name-only main
```

Expected changed paths only:

```text
README.md
docs/superpowers/plans/2026-07-21-pgo-team-model.md
pgo_model.py
research/pgo/backtest.json
research/pgo/ratings_2026_preseason.csv
tests/test_pgo_model.py
```

- [ ] **Step 4: Commit documentation if needed**

```powershell
git add README.md docs/superpowers/plans/2026-07-21-pgo-team-model.md
git commit -m "Document shadow PGO model workflow"
```

- [ ] **Step 5: Stop at review**

Return the branch name, local commits, exact backtest metrics, receipt paths, test output, and production-isolation proof. Do not push, merge, publish, deploy, change workflows, or integrate PGO ratings into any public surface without a new explicit approval.
