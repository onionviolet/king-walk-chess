#!/usr/bin/env python3
"""Play the king-walk engine against a strength-limited Stockfish.

  .venv/bin/python match.py --games 32 --elo 1320 --odds q,r --kw-depth 5 --sf-nodes 20000
The king-walker faces Stockfish: odds remove Stockfish-side pieces.
Colors alternate. Score = (wins + draws/2) / games for the king-walker.

Fairness note: with --kw-time / --sf-time the engines think for a fixed CLOCK time, so
scores shift with machine load (the tuning run's baseline moved from 0.33 to 0.09 that way).
For comparisons use --kw-depth and --sf-nodes, which do not depend on load.
"""
import argparse
import json
import shutil
from multiprocessing import Pool
from pathlib import Path

import chess
import chess.engine

from kingwalk import RULES, Searcher, apply_odds, side_moves

PATCHED = str(Path(__file__).parent / "vendor/Stockfish/src/stockfish")


def _limit(seconds, depth=0, nodes=0):
    if nodes:
        return chess.engine.Limit(nodes=nodes)
    if depth:
        return chess.engine.Limit(depth=depth)
    return chess.engine.Limit(time=seconds)


def play(args):
    idx, elo, odds, kw_time, sf_time, max_plies, player, rule, weights, kw_depth, sf_nodes = args
    kw_color = chess.WHITE if idx % 2 == 0 else chess.BLACK
    board = chess.Board()
    if odds:
        apply_odds(board, not kw_color, odds)
    searcher = Searcher(RULES[rule], weights)
    stockfish = shutil.which("stockfish")
    helper = None
    if player in ("sfk", "sfw"):
        helper = chess.engine.SimpleEngine.popen_uci(PATCHED if player == "sfw" else stockfish)
    sf = chess.engine.SimpleEngine.popen_uci(stockfish)
    try:
        sf.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
        while not board.is_game_over(claim_draw=True) and len(board.move_stack) < max_plies:
            if board.turn == kw_color:
                lim = _limit(kw_time, kw_depth)
                if player == "sfw":  # patched Stockfish: the rule holds at every ply of its search
                    has_king = any(board.piece_type_at(x.from_square) == chess.KING for x in board.legal_moves)
                    helper.configure({"KingWalkColor": (0 if kw_color == chess.WHITE else 1) if has_king else 2})
                    # no move history: it would contain moves this rule forbids and the engine quits
                    move = helper.play(chess.Board(board.fen()), lim).move
                elif player == "sfk":  # Stockfish restricted at the root via searchmoves
                    root = side_moves(board, kw_color, RULES[rule])
                    move = helper.play(board, lim, root_moves=root).move
                elif kw_depth:
                    move, _, _ = searcher.search(board, max_depth=kw_depth, seconds=None)
                else:
                    move, _, _ = searcher.search(board, seconds=kw_time)
            else:
                move = sf.play(board, _limit(sf_time, nodes=sf_nodes)).move
            board.push(move)
    finally:
        sf.quit()
        if helper:
            helper.quit()
    out = board.outcome(claim_draw=True)
    if out is None or out.winner is None:
        return 0.5, len(board.move_stack)
    return (1.0 if out.winner == kw_color else 0.0), len(board.move_stack)


def run(games, elo, odds, kw_time, sf_time, max_plies, player, rule, weights, procs,
        kw_depth=0, sf_nodes=0):
    jobs = [(i, elo, odds, kw_time, sf_time, max_plies, player, rule, weights, kw_depth, sf_nodes)
            for i in range(games)]
    with Pool(procs) as p:
        res = p.map(play, jobs)
    return sum(r for r, _ in res) / len(res), res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=8)
    ap.add_argument("--elo", type=int, default=1320)
    ap.add_argument("--odds", default="")
    ap.add_argument("--kw-time", type=float, default=0.4)
    ap.add_argument("--sf-time", type=float, default=0.05)
    ap.add_argument("--kw-depth", type=int, default=0, help="fixed depth for the king-walker (load-independent)")
    ap.add_argument("--sf-nodes", type=int, default=0, help="fixed node count for the opponent (load-independent)")
    ap.add_argument("--max-plies", type=int, default=240)
    ap.add_argument("--player", choices=["kw", "sfk", "sfw"], default="kw")
    ap.add_argument("--rule", choices=list(RULES), default="king")
    ap.add_argument("--weights", default="{}", help="JSON overrides for eval weights")
    ap.add_argument("--procs", type=int, default=4)
    a = ap.parse_args()
    odds = [x for x in a.odds.split(",") if x]
    score, res = run(a.games, a.elo, odds, a.kw_time, a.sf_time, a.max_plies, a.player, a.rule,
                     json.loads(a.weights), a.procs, a.kw_depth, a.sf_nodes)
    w, d, l = (sum(1 for r, _ in res if r == x) for x in (1.0, 0.5, 0.0))
    mode = f"depth {a.kw_depth}/nodes {a.sf_nodes}" if a.kw_depth else f"kw-time {a.kw_time}"
    print(f"{a.player}/{a.rule} elo {a.elo} odds [{a.odds or 'none'}] {mode}: "
          f"+{w} ={d} -{l}  score {score:.2f}  avg plies {sum(n for _, n in res) / len(res):.0f}")


if __name__ == "__main__":
    main()
