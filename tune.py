#!/usr/bin/env python3
"""Random-search tuner for the eval weights, scored by matches against a limited Stockfish.

  .venv/bin/python tune.py --iters 16 --games 32 --odds q,r --kw-depth 4 --sf-nodes 20000
Writes every trial to results/tune_log_<date>.jsonl, then re-tests the top 3 with --confirm games.
Scores are noisy (32 games is about +/-0.07), so only trust the confirmed numbers.
"""
import argparse
import json
import math
import random
import time
from pathlib import Path

from kingwalk import DEFAULT_W
from match import run


RESULTS = Path(__file__).parent / "results"
RESULTS.mkdir(exist_ok=True)
LOG = RESULTS / time.strftime("tune_log_%Y-%m-%d_%H%M.jsonl")


def score(w, a, games):
    s, res = run(games, a.elo, [x for x in a.odds.split(",") if x], a.kw_time, 0.05, 240,
                 "kw", "king", w, a.procs, kw_depth=a.kw_depth, sf_nodes=a.sf_nodes)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=int, default=16)
    ap.add_argument("--games", type=int, default=32)
    ap.add_argument("--confirm", type=int, default=96)
    ap.add_argument("--elo", type=int, default=1320)
    ap.add_argument("--odds", default="q,r")
    ap.add_argument("--kw-time", type=float, default=0.3)
    ap.add_argument("--kw-depth", type=int, default=0, help="use fixed depth (load-independent)")
    ap.add_argument("--sf-nodes", type=int, default=0, help="use fixed opponent nodes (load-independent)")
    ap.add_argument("--procs", type=int, default=16)
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()
    rng = random.Random(a.seed)

    trials = []
    best_w = dict(DEFAULT_W)

    def log(w, s, tag):
        trials.append((s, w))
        with open(LOG, "a") as f:
            f.write(json.dumps({"tag": tag, "score": s, "w": w, "t": time.time()}) + "\n")
        print(f"{tag}: {s:.3f} {w}", flush=True)

    best_s = score(best_w, a, a.games)
    log(best_w, best_s, "baseline")
    for i in range(a.iters):
        # mutate from the current best: log-normal multiplicative noise on each weight
        cand = {k: round(v * math.exp(rng.gauss(0, 0.45)), 2) for k, v in best_w.items()}
        s = score(cand, a, a.games)
        log(cand, s, f"iter{i}")
        if s > best_s:  # greedy; confirmation below guards against lucky noise
            best_w, best_s = cand, s

    print("\nConfirming top 3 plus baseline...", flush=True)
    top = sorted(trials, key=lambda t: -t[0])[:3]
    finalists = {json.dumps(DEFAULT_W): DEFAULT_W}
    for _, w in top:
        finalists[json.dumps(w, sort_keys=True)] = w
    results = []
    for w in finalists.values():
        s = score(w, a, a.confirm)
        results.append((s, w))
        log(w, s, "confirm")
    results.sort(key=lambda t: -t[0])
    print("\nBEST CONFIRMED:", results[0], flush=True)


if __name__ == "__main__":
    main()
