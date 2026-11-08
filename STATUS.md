# King Walk Chess: status

*Type: CURRENT-STATE. Reconciled and committed 2026-11-04. Replace stale lines; do not append history here.*

## Verification state per feature
States kept separate: source (edited), focused test, fixture journey, real screen/site, committed.

| Feature | Source | Focused tests | Fixture journey | Real screen/site | Committed |
|---|---|---|---|---|---|
| King-only engine, rules table, fallback | yes | yes (9) | via match harness | n/a | yes |
| UCI wrapper with Rule option | yes | yes (2) | no GUI tried | no | yes |
| Screen reader (learn/read) | yes | yes (5, drawn boards) | yes (watch journey) | NOT RUN | yes |
| Game tracker | yes | yes (5) | yes | NOT RUN | yes |
| Watcher loop and overlay | yes | yes | yes (3, drawn boards) | NOT RUN | yes |
| OCR (move list, clock) | yes | yes (4, drawn text) | move-list sync path only, OCR stubbed | NOT RUN | yes |
| Patched Stockfish `KingWalkColor` | yes (patch file) | yes (2, needs build) | used in matches | n/a | yes |
| Match and tune harness | yes | smoke only (16-game depth run) | n/a | n/a | yes |

Test run on the current tree: `.venv/bin/python -m pytest -q` gave 27 passed (2026-11-04).

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
- One fixed-depth smoke run (depth 4 vs 20000 nodes, queen+rook odds, 16 games): 0.44. Single sample.

## Unmapped residue / not done
- Real chess.com or Lichess screen: board reader, OCR and calibration are untested on real sprites.
- Plan layer (target + safe path), opponent-error modeling, learned eval, opening book: not built.
- Fair-handicap table per rating and per rule: not measured.
- Turn after a mid-game resync is assumed to be ours unless the move list syncs.
- Patched Stockfish wired only into match.py, not into watch.py, the game or the UCI wrapper.
- Not pushed anywhere (local repo only). History-dependent rules (for example "alternate pieces") are unsupported
  because the transposition table keys on position only.
