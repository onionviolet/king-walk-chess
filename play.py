#!/usr/bin/env python3
"""Play King Walk Chess in the browser against the engine.

  .venv/bin/python play.py [--port 8766]
then open http://localhost:8766. You choose your color, the engine's rule, piece odds
and think time on the page. The server checks every move; the page only sends squares.
"""
import argparse
import datetime
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import chess
import chess.pgn

from kingwalk import RULES, Searcher, apply_odds

PAGE = Path(__file__).with_name("play.html")
GAMES = Path(__file__).with_name("games")  # one PGN per game played on the page (gitignored)
_lock = threading.Lock()
_searchers = {}
_engine_notes = {}  # game_id -> {ply: (uci, info)}

# Starting positions offered on the page (the page also accepts any FEN).
PRESETS = {
    "Standard": chess.STARTING_FEN,
    "King already free (1.e4 e5)": "rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2",
    "Open center (no d- or e-pawns)": "rnbqkbnr/ppp2ppp/8/8/8/8/PPP2PPP/RNBQKBNR w KQkq - 0 1",
    "Kings and pawns": "4k3/pppppppp/8/8/8/8/PPPPPPPP/4K3 w - - 0 1",
    "Minor pieces only": "1nb1kbn1/pppppppp/8/8/8/8/PPPPPPPP/1NB1KBN1 w - - 0 1",
}


def build(req):
    """Rebuild the game from the request. Raises ValueError on an illegal move."""
    human = chess.WHITE if req.get("color", "white") == "white" else chess.BLACK
    try:
        board = chess.Board(req.get("start") or chess.STARTING_FEN)
    except ValueError:
        raise ValueError("That FEN could not be read.")
    first = req.get("first", "position")
    if first in ("white", "black"):
        turn = first == "white"
        if board.turn != turn:
            board.turn = turn
            board.ep_square = None
    odds = [x.strip().lower() for x in str(req.get("odds", "")).split(",") if x.strip() in list("qrbnp")]
    if odds:
        apply_odds(board, human, odds)
    if not board.is_valid():
        st = board.status()
        why = ", ".join(f.name.replace("_", " ").lower() for f in chess.Status if f and f in st and f.name)
        raise ValueError(f"Not a playable position: {why}.")
    for u in req.get("moves", []):
        m = chess.Move.from_uci(u)
        if m not in board.legal_moves:
            raise ValueError(f"illegal move {u}")
        board.push(m)
    return board, human


def status(board, human):
    out = board.outcome(claim_draw=True)
    if out is None:
        if board.is_check():
            return "Check." if board.turn == human else "Engine is in check."
        return "Your move." if board.turn == human else "Engine to move."
    if out.winner is None:
        return f"Draw ({out.termination.name.lower().replace('_', ' ')})."
    return "You win by checkmate!" if out.winner == human else "Engine wins by checkmate."


def handle(req):
    board, human = build(req)
    rule_name = req.get("rule", "king+pawns")
    if rule_name not in RULES:
        raise ValueError("unknown rule")
    info = {}
    if req.get("think") and board.turn != human and board.outcome(claim_draw=True) is None:
        secs = min(max(float(req.get("time", 2)), 0.1), 30)
        with _lock:
            s = _searchers.setdefault(rule_name, Searcher(RULES[rule_name]))
            t = time.time()
            move, score, depth = s.search(board, seconds=secs)
        info = {"eval": int(score), "depth": depth, "secs": round(time.time() - t, 1),
                "san": board.san(move)}
        board.push(move)
        if req.get("game_id"):
            _engine_notes.setdefault(req["game_id"], {})[len(board.move_stack) - 1] = (move.uci(), info)
    if req.get("game_id"):
        save_game(req, board, human)
    replay = chess.Board(_start_fen(req))
    start_turn = "white" if replay.turn == chess.WHITE else "black"
    sans, captured = [], {"white": [], "black": []}
    for m in board.move_stack:
        sans.append(replay.san(m))
        if replay.is_capture(m):
            victim = replay.piece_at(m.to_square) or chess.Piece(chess.PAWN, not replay.turn)  # en passant
            captured["white" if victim.color == chess.WHITE else "black"].append(victim.symbol().lower())
        replay.push(m)
    legal = [m.uci() for m in board.legal_moves] if board.turn == human else []
    king_sq = board.king(board.turn)
    return {
        "fen": board.fen(),
        "moves": [m.uci() for m in board.move_stack],
        "sans": sans,
        "legal": legal,
        "turn": "white" if board.turn == chess.WHITE else "black",
        "check": chess.square_name(king_sq) if board.is_check() and king_sq is not None else None,
        "last": board.move_stack[-1].uci() if board.move_stack else None,
        "over": board.outcome(claim_draw=True) is not None,
        "status": status(board, human),
        "engine": info,
        "start_turn": start_turn,
        "start_fen": _start_fen(req),
        "captured": captured,
    }


def save_game(req, board, human):
    """Write (overwrite) games/<game_id>.pgn with settings, result and engine notes per move."""
    gid = re.sub(r"[^A-Za-z0-9_-]", "", str(req["game_id"]))[:64]
    if not gid:
        return
    start = chess.Board(_start_fen(req))
    game = chess.pgn.Game()
    game.setup(start)
    h = game.headers
    h["Event"] = "King Walk Chess (browser)"
    h["Date"] = datetime.date.today().strftime("%Y.%m.%d")
    h["White"], h["Black"] = ("You", "Engine") if human == chess.WHITE else ("Engine", "You")
    h["Rule"] = req.get("rule", "king+pawns")
    h["Odds"] = req.get("odds", "") or "none"
    h["EngineSeconds"] = str(req.get("time", 2))
    out = board.outcome(claim_draw=True)
    if req.get("resigned"):
        h["Result"] = "1-0" if human == chess.BLACK else "0-1"
        h["Termination"] = "You resigned"
    elif out:
        h["Result"] = out.result()
        h["Termination"] = out.termination.name.lower()
    else:
        h["Result"] = "*"
    notes = _engine_notes.get(req["game_id"], {})
    node = game
    for ply, m in enumerate(board.move_stack):
        node = node.add_variation(m)
        note = notes.get(ply)
        if note and note[0] == m.uci():  # skip notes for moves taken back by undo
            i = note[1]
            node.comment = f"eval {i['eval']:+} depth {i['depth']} {i['secs']}s"
    GAMES.mkdir(exist_ok=True)
    (GAMES / f"{gid}.pgn").write_text(str(game) + "\n")


def _start_fen(req):
    req = dict(req, moves=[])
    return build(req)[0].fen()


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/rules":
            self._send(200, list(RULES))
        elif self.path == "/api/config":
            self._send(200, {"rules": list(RULES), "presets": PRESETS})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/api/play":
            return self._send(404, {"error": "not found"})
        try:
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            self._send(200, handle(req))
        except (ValueError, KeyError) as e:
            self._send(400, {"error": str(e)})


def serve(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"King Walk Chess at http://localhost:{port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    serve(ap.parse_args().port)
