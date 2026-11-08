# King Walk Chess

Chess where one side may only move its king and pawns (or another restricted set of pieces);
its other pieces are frozen but still block and guard. You play normally against the engine,
which plays the restricted side, or the engine suggests the best restricted move on a live screen. Python 3.15 + python-chess. Mac only for the
screen tools (screencapture, Apple Vision).

Setup: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
Tests: `.venv/bin/python -m pytest -q` (40 tests, about 20 s)

## Use it
- Play in the browser: `.venv/bin/python play.py`, then open http://localhost:8766. Click or drag to move.
  New game panel: your color (or random), starting position (presets or any FEN), who moves first,
  piece odds, engine rule and seconds. Undo, flip, resign; keys U, F, N.
  Every game is saved to `games/<id>.pgn` (gitignored) with the settings, result and the engine's
  eval and depth on each of its moves.
- Play in the terminal: `.venv/bin/python kingwalk.py --color white --time 3 [--odds q,r] [--rule NAME]`
- Best move for a position: `.venv/bin/python kingwalk.py --suggest "FEN" --time 5`
- Any UCI GUI or lichess-bot: point it at `kingwalk_uci.py` (option `Rule`)
- Live screen assistant (overlay at http://localhost:8765):
  1. Show the start position, run `.venv/bin/python screenread.py calibrate`
  2. Optional: `.venv/bin/python screenread.py calibrate-text` (move list, clocks)
  3. `.venv/bin/python watch.py [--rule NAME] [--time 3]`
  Engine help is for games your friend knows about; live chess.com and Lichess games forbid it.

Rules (`--rule`, default king+pawns): king+pawns, king, knights, bishops, no-queen, forward,
captures, none. Add one as a line in `RULES` in `kingwalk.py`. If a rule leaves no legal move
(for example the king is boxed in under `king`), the engine may only play a move that frees one
for its next turn; if no move does that, any move is allowed (no deadlock).

## Measure it
`match.py` plays the engine against Stockfish limited by Elo (`brew install stockfish`).
Use `--kw-depth` and `--sf-nodes` for load-independent comparisons; `--kw-time` results move
with machine load. `tune.py` random-searches the eval weights; results go to `results/`.

## Patched Stockfish (optional)
`patches/stockfish-kingwalk.patch` adds a `KingWalkColor` UCI option to official Stockfish
(base commit ff7cee4). Build: clone Stockfish into `vendor/Stockfish`, `git apply` the patch,
`make -j build ARCH=apple-silicon`. The patch is GPL; share the source if you share a binary.
Current state and evidence: see STATUS.md.

## License
GPL-3.0 (see LICENSE), matching the Stockfish patch.
