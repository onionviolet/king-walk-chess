#!/usr/bin/env python3
"""Minimal UCI wrapper so any UCI GUI or bot framework can run King Walk Chess.

The side to move at each `go` is treated as the king-walker.
"""
import sys

import chess

from kingwalk import RULES, Searcher


def main():
    board = chess.Board()
    rule = RULES["king"]
    searcher = Searcher(rule)

    def out(s):
        print(s, flush=True)

    for line in sys.stdin:
        parts = line.split()
        if not parts:
            continue
        cmd = parts[0]
        if cmd == "uci":
            out("id name KingWalk 0.2")
            out("id author weibao")
            out("option name Rule type combo default king " + " ".join("var " + r for r in RULES))
            out("uciok")
        elif cmd == "isready":
            out("readyok")
        elif cmd == "setoption" and "Rule" in parts and parts[-1] in RULES:
            rule = RULES[parts[-1]]
            searcher = Searcher(rule)
        elif cmd == "ucinewgame":
            board = chess.Board()
            searcher = Searcher(rule)
        elif cmd == "position":
            if parts[1] == "startpos":
                board = chess.Board()
                rest = parts[2:]
            else:
                i = parts.index("moves") if "moves" in parts else len(parts)
                board = chess.Board(" ".join(parts[2:i]))
                rest = parts[i:]
            if rest[:1] == ["moves"]:
                for mv in rest[1:]:
                    board.push_uci(mv)
        elif cmd == "go":
            args = dict(zip(parts[1::2], parts[2::2]))
            if "movetime" in args:
                secs = int(args["movetime"]) / 1000
            else:
                mine = args.get("wtime" if board.turn == chess.WHITE else "btime")
                secs = min(int(mine) / 1000 / 30, 10) if mine else 3.0
            depth = int(args["depth"]) if "depth" in args else 64

            def info(d, score, nodes, move):
                out(f"info depth {d} score cp {int(score)} nodes {nodes} pv {move.uci()}")

            move, _, _ = searcher.search(board, max_depth=depth, seconds=max(secs, 0.05), info=info)
            out(f"bestmove {move.uci()}")
        elif cmd == "quit":
            break


if __name__ == "__main__":
    main()
