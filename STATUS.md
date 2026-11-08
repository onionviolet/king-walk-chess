# King Walk Chess: status

*Type: CURRENT-STATE. Reconciled 2026-11-04; engine search and browser play added 2026-11-07 (uncommitted). Replace stale lines; do not append history here.*

## Verification state per feature
States kept separate: source (edited), focused test, fixture journey, real screen/site, committed.

| Feature | Source | Focused tests | Fixture journey | Real screen/site | Committed |
|---|---|---|---|---|---|
| King-only engine, rules table, fallback | yes | yes (9) | via match harness | n/a | yes |
| Stuck-king rule: only moves that free the king (any move only if none do) | yes | yes (3) | browser pane | n/a | no |
| king+pawns as default rule (CLI, UCI, page), fast move gen, pawn eval terms (advance, passed; off by default, no measured gain) | yes | yes (fast path = rule) | browser pane | n/a | no |
| Game log: games/<id>.pgn per browser game with engine eval/depth comments | yes | yes (1) | browser pane | n/a | no |
| Search upgrade: check extension, in-check qsearch, killer/history ordering, king-only move gen | yes | yes (mate-in-net node test) | via match harness | n/a | no |
| Browser play (play.py + play.html, port 8766): start position presets/FEN, first-move override, drag and click, eval bar, captures, game-over banner | yes | yes (7: game through API, odds as black, illegal move, HTTP, start + first move, bad FEN, captures) | n/a | played in the Claude browser pane 2026-11-07: click and drag moves, undo, black + q,r odds, Kings-and-pawns start with black first, bad-FEN error | no |
| UCI wrapper with Rule option | yes | yes (2) | no GUI tried | no | yes |
| Screen reader (learn/read) | yes | yes (5, drawn boards) | yes (watch journey) | NOT RUN | yes |
| Game tracker | yes | yes (5) | yes | NOT RUN | yes |
| Watcher loop and overlay | yes | yes | yes (3, drawn boards) | NOT RUN | yes |
| OCR (move list, clock) | yes | yes (4, drawn text) | move-list sync path only, OCR stubbed | NOT RUN | yes |
| Patched Stockfish `KingWalkColor` | yes (patch file) | yes (2, needs build) | used in matches | n/a | yes |
| Match and tune harness | yes | smoke only (16-game depth run) | n/a | n/a | yes |

Test run on the current tree: `.venv/bin/python -m pytest -q` gave 40 passed (2026-11-07).

## Findings ledger (this pass)
| ID | Claim and locator | Class | Disposition |
|---|---|---|---|
| F1 | kingwalk.py docstring pointed to a README that did not exist | stale doc | README.md added, docstring fixed |
| F2 | watcher loop and OCR wiring never executed by any test | missing proof | test_journey.py runs watch.main() on drawn boards (3 tests) |
| F3 | patched Stockfish rule had only a manual check | missing proof | test_patched_stockfish.py (skips if not built) |
| F4 | time-limited matches vary with machine load (baseline 0.33, 0.19, 0.09 in separate runs) | incomplete integration | `--kw-depth` / `--sf-nodes` added to match.py and tune.py |
| F5 | tune outputs sat at repo root; tune.py wrote a fixed filename | duplicate/clutter | moved to results/, dated log per run |
| F6 | match.py built its job list twice (main and run) | duplicate | main now calls run() |
| F7 | no requirements, README or status owner | stale doc | requirements.txt, README.md, this file |

## Measured results (kept separate from claims)
- Stockfish limited to Elo 1320 (UCI_Elo; not a Chess.com rating), 32 games, clock-limited 0.3 s:
  no odds 0.00 (4 games); queen+rook odds 0.33 (Python) vs 0.12 (patched Stockfish);
  queen+2 rooks+2 bishops 0.42 vs 0.30. Noise about +/-0.07.
- Eval tuning (16 trials x 32 games, then 96-game confirm, clock-limited): no weights beat the
  defaults beyond noise; defaults unchanged. Logs: results/.
- Search upgrade (2026-11-07): the forced-mate position in test_play.py takes 12.7k nodes at depth 6 versus 51.5k before.
  Old vs new, run side by side, 64 games each vs Stockfish UCI_Elo 1320 at 20000 nodes, queen+rook odds, 0.3 s per move:
  old +1 =22 -41 (0.19), new +6 =23 -35 (0.27). Leans better; one paired run, near the noise level.
- Rules compared (2026-11-07, 48 games each, 4 matches run at once, Stockfish UCI_Elo 1320 at 20000 nodes, 0.3 s per move):
  king, queen+rook odds: +0 =11 -37 (0.11). king+pawns, queen+rook odds: +27 =17 -4 (0.74) without pawn terms,
  +21 =22 -5 (0.67) with advance 6 / passed 20. king+pawns, no odds: +0 =1 -47 (0.01).
- One fixed-depth smoke run (depth 4 vs 20000 nodes, queen+rook odds, 16 games): 0.44. Single sample.

## Unmapped residue / not done
- Real chess.com or Lichess screen: board reader, OCR and calibration are untested on real sprites.
- Plan layer (target + safe path), opponent-error modeling, learned eval, opening book: not built.
- Fair-handicap table per rating and per rule: not measured.
- Turn after a mid-game resync is assumed to be ours unless the move list syncs.
- Patched Stockfish still uses the old fallback (any move when the king is stuck), and the 2026-11-07 old-vs-new
  match predates the stuck-king rule.
- Patched Stockfish wired only into match.py, not into watch.py, the game, the browser UI or the UCI wrapper.
- Pushed to GitHub (public, GPL-3.0) on 2026-11-07: github.com/onionviolet/king-walk-chess.
- History-dependent rules (for example "alternate pieces") are unsupported
  because the transposition table keys on position only.

## Played games
- 2026-11-07: three browser losses for the king rule were not recorded (no logging yet). The fourth game,
  recovered from the open tab, is games/2026-11-07_recovered-from-tab.pgn: the king shuffled e8/e7/d6 while
  Bg5+ won its frozen queen. Logging is on from now.
