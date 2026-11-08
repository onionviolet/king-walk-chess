import json
import random
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import chess
import pytest

import kingwalk as k
import play


def test_engine_reply_obeys_king_rule_through_a_game():
    random.seed(3)
    req = {"color": "white", "rule": "king", "odds": "", "time": 0.2, "moves": []}
    for _ in range(12):
        st = play.handle(req)
        if st["over"]:
            break
        req["moves"] = st["moves"] + [random.choice(st["legal"])]
        before = chess.Board()
        for u in req["moves"]:
            before.push_uci(u)
        st = play.handle({**req, "think": True})
        if before.is_game_over():
            break
        reply = chess.Move.from_uci(st["moves"][-1])
        king_moves = k.side_moves(before, chess.BLACK)
        assert reply in king_moves  # side_moves holds the rule and its fallback
        if any(before.piece_type_at(m.from_square) == chess.KING for m in before.legal_moves):
            assert before.piece_type_at(reply.from_square) == chess.KING
        req["moves"] = st["moves"]


def test_black_with_odds_engine_moves_first():
    st = play.handle({"color": "black", "odds": "q,r", "moves": [], "think": True, "time": 0.2})
    assert len(st["moves"]) == 1 and st["turn"] == "black" and st["legal"]
    assert st["fen"].split()[0].count("q") == 0  # black's queen removed


def test_illegal_move_rejected():
    with pytest.raises(ValueError):
        play.handle({"moves": ["e2e5"]})


def test_http_endpoint():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), play.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        body = json.dumps({"moves": ["e2e4"], "think": True, "time": 0.2}).encode()
        r = urllib.request.urlopen(urllib.request.Request(url + "/api/play", body,
                                                          {"Content-Type": "application/json"}))
        st = json.loads(r.read())
        assert len(st["moves"]) == 2 and st["engine"]["san"]
        assert b"King Walk Chess" in urllib.request.urlopen(url + "/").read()
    finally:
        srv.shutdown()


def test_finds_forced_mate_cheaply():
    # 1.e4 e5 2.Nf3 Nc6, white to move under the king rule: Ke2 is forced and loses by force.
    # The pre-2026-11-07 search needed about 51k nodes to see it; ordering + check extension ~13k.
    b = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3")
    s = k.Searcher()
    _, score, _ = s.search(b, max_depth=6, seconds=None)
    assert score < -k.MATE + 1000 and s.nodes < 25000


def test_start_position_and_first_move():
    fen = play.PRESETS["Kings and pawns"]
    st = play.handle({"start": fen, "first": "black", "color": "black", "moves": []})
    assert st["start_turn"] == "black" and st["turn"] == "black" and st["legal"]
    st = play.handle({"start": fen, "first": "black", "color": "white", "moves": [], "think": True, "time": 0.2})
    assert len(st["moves"]) == 1 and st["turn"] == "white"


def test_bad_fen_rejected_with_reason():
    with pytest.raises(ValueError, match="no white king"):
        play.handle({"start": "8/8/8/8/8/8/8/k7 w - - 0 1"})


def test_captures_reported():
    st = play.handle({"moves": ["e2e4", "d7d5", "e4d5"]})
    assert st["captured"] == {"white": [], "black": ["p"]}


def test_game_log_written_with_engine_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(play, "GAMES", tmp_path)
    req = {"moves": ["e2e4"], "think": True, "time": 0.2, "game_id": "t1", "rule": "king+pawns"}
    st = play.handle(req)
    play.handle({**req, "moves": st["moves"], "think": False, "resigned": True})
    pgn = (tmp_path / "t1.pgn").read_text()
    assert '[Rule "king+pawns"]' in pgn and '[Result "0-1"]' in pgn and "{ eval" in pgn
