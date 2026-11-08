#!/usr/bin/env python3
"""Live king-walk assistant: watches your screen, tracks the game, and shows the
suggested king move with an arrow and eval bar at http://localhost:8765

  .venv/bin/python watch.py [--profile default] [--time 3] [--port 8765]
                            [--color white|black] [--interval 0.6]

Run `screenread.py calibrate` first. Engine help is for games your friend knows about;
live chess.com games forbid it.
"""
import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import chess

import screenread as sr
from kingwalk import RULES, Searcher

HERE = Path(__file__).parent


class Tracker:
    """Follow the game from a stream of piece placements (1 or 2 plies per update)."""

    def __init__(self, ours):
        self.ours = ours
        self.board = None

    @staticmethod
    def guess_castling(board):
        rights = 0
        for color, home in ((chess.WHITE, 0), (chess.BLACK, 7)):
            if board.piece_at(chess.square(4, home)) == chess.Piece(chess.KING, color):
                for file, flag in ((0, chess.BB_FILES[0]), (7, chess.BB_FILES[7])):
                    sq = chess.square(file, home)
                    if board.piece_at(sq) == chess.Piece(chess.ROOK, color):
                        rights |= chess.BB_SQUARES[sq]
        return rights

    def resync(self, placement):
        b = chess.Board(None)
        b.set_board_fen(placement)
        b.turn = self.ours
        b.castling_rights = self.guess_castling(b)
        if not b.is_valid():
            return False
        self.board = b
        return True

    def update(self, placement):
        """Returns 'same', 'moved', 'resync', or 'invalid'."""
        if self.board is None:
            if placement == chess.STARTING_BOARD_FEN:
                self.board = chess.Board()
                return "resync"
            return "resync" if self.resync(placement) else "invalid"
        b = self.board
        if placement == b.board_fen():
            return "same"
        for m1 in list(b.legal_moves):
            b.push(m1)
            if b.board_fen() == placement:
                return "moved"
            for m2 in list(b.legal_moves):
                b.push(m2)
                if b.board_fen() == placement:
                    return "moved"
                b.pop()
            b.pop()
        return "resync" if self.resync(placement) else "invalid"


def budget_seconds(clock_s, cap, floor=0.3):
    """Thinking time: the cap, or 1/40 of the remaining clock when that is smaller."""
    if clock_s is None:
        return cap
    return max(floor, min(cap, clock_s / 40.0))


def sync_from_movelist(tracker, tokens, placement):
    """Adopt the replayed move list as the game history, but only if replaying it
    reproduces exactly what the board shows. Returns True when adopted."""
    import ocr
    board, played, bad = ocr.replay_san(tokens)
    if bad or not played or board.board_fen() != placement:
        return False
    tracker.board = board
    return True


def read_text_boxes(text_boxes):
    """OCR the optional move-list and clock boxes. Returns (move tokens or None, my clock seconds or None)."""
    import ocr
    tokens, mine = None, None
    if "movelist" in text_boxes:
        lines = ocr.ocr_lines(sr.capture(text_boxes["movelist"]))
        tokens = ocr.move_tokens(" ".join(t for t, _ in lines if ":" not in t))
    if "clock_me" in text_boxes:
        for t, _ in ocr.ocr_lines(sr.capture(text_boxes["clock_me"])):
            mine = ocr.clock_seconds(t)
            if mine is not None:
                break
    return tokens, mine


class State:
    def __init__(self):
        self.lock = threading.Lock()
        self.data = {"status": "starting"}

    def set(self, **kw):
        with self.lock:
            self.data = kw

    def json(self):
        with self.lock:
            return json.dumps(self.data)


def serve(state, port):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/state.json"):
                body, ctype = state.json().encode(), "application/json"
            else:
                body, ctype = (HERE / "overlay.html").read_bytes(), "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()


def publish(state, board, ours, white_bottom, status, move=None, score=None, depth=None):
    state.set(status=status, fen=board.fen() if board else None,
              ours="white" if ours == chess.WHITE else "black", white_bottom=white_bottom,
              turn=("white" if board.turn == chess.WHITE else "black") if board else None,
              move=move.uci() if move else None,
              san=board.san(move) if (move and board) else None,
              # engine eval is from the mover's side; the bar is always from White's side
              cp_white=(score if board.turn == chess.WHITE else -score) if score is not None else None,
              depth=depth)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="default")
    ap.add_argument("--time", type=float, default=3.0)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--interval", type=float, default=0.6)
    ap.add_argument("--rule", choices=list(RULES), default="king")
    ap.add_argument("--color", choices=["white", "black"], default=None,
                    help="override the side detected at calibration")
    a = ap.parse_args()

    box, cal = sr.load(a.profile)
    text_boxes = sr.load_text(a.profile)
    white_bottom = cal["white_bottom"]
    ours = (chess.WHITE if a.color == "white" else chess.BLACK) if a.color else \
           (chess.WHITE if white_bottom else chess.BLACK)
    tracker, state, searcher = Tracker(ours), State(), Searcher(RULES[a.rule])
    serve(state, a.port)
    print(f"Overlay: http://localhost:{a.port}   (you are {'White' if ours else 'Black'})")

    prev, accepted, suggested = None, None, None
    while True:
        try:
            placement, conf = sr.read(sr.capture(box), cal)
        except Exception as e:  # capture hiccup
            print("capture error:", e)
            time.sleep(1)
            continue
        if placement != prev:       # need two identical reads (skips animation frames)
            prev = placement
            time.sleep(a.interval)
            continue
        if placement != accepted:
            accepted = placement
            status = tracker.update(placement)
            if status == "invalid":
                publish(state, None, ours, white_bottom, "board not recognized")
                accepted = None
            elif status == "resync":
                print("(re)synced from screen; assuming the turn is yours" if placement != chess.STARTING_BOARD_FEN
                      else "new game")
            if text_boxes.get("movelist") and status in ("moved", "resync"):
                try:
                    tokens, _ = read_text_boxes({"movelist": text_boxes["movelist"]})
                    if tokens and sync_from_movelist(tracker, tokens, placement):
                        print(f"history synced from move list ({len(tokens)} plies)")
                except Exception as e:
                    print("move-list OCR skipped:", e)
        b = tracker.board
        if b is not None and not b.is_game_over() and b.turn == ours and suggested != b.fen():
            publish(state, b, ours, white_bottom, "thinking")
            secs = a.time
            if text_boxes.get("clock_me"):
                try:
                    _, mine = read_text_boxes({"clock_me": text_boxes["clock_me"]})
                    secs = budget_seconds(mine, a.time)
                except Exception as e:
                    print("clock OCR skipped:", e)
            move, score, depth = searcher.search(b, seconds=secs)
            suggested = b.fen()
            publish(state, b, ours, white_bottom, "your move", move, score, depth)
            print(f"{b.san(move)} ({move.uci()})  eval {score:+}  depth {depth}")
        elif b is not None and suggested != b.fen():
            publish(state, b, ours, white_bottom,
                    "game over" if b.is_game_over() else "waiting for your friend")
        time.sleep(a.interval)


if __name__ == "__main__":
    main()
