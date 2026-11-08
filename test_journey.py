"""Fixture journey: run watch.main() end to end on drawn boards (no real screen).
This proves the loop wiring (capture -> read -> track -> search -> publish), not the real
site sprites, screen permission, or live OCR."""
import json
import sys
import types
import urllib.request

import chess
import pytest

import screenread as sr
import watch
from test_screenread import render


class Stop(BaseException):
    pass


def run_watch(monkeypatch, frames, argv, text_boxes=None, sleeps=14):
    start_img = render(chess.STARTING_BOARD_FEN, flipped=True)      # we play Black (bottom)
    cal = sr.learn(start_img)
    imgs = [render(f, flipped=True) for f in frames]
    calls = {"n": 0, "sleeps": 0}

    def fake_capture(box):
        i = min(calls["n"], len(imgs) - 1)
        calls["n"] += 1
        return imgs[i]

    def fake_sleep(_):
        calls["sleeps"] += 1
        if calls["sleeps"] > sleeps:
            raise Stop

    monkeypatch.setattr(sr, "capture", fake_capture)
    monkeypatch.setattr(sr, "load", lambda profile: ([0, 0, 480, 480], cal))
    monkeypatch.setattr(sr, "load_text", lambda profile: text_boxes or {})
    monkeypatch.setattr(watch, "time", types.SimpleNamespace(sleep=fake_sleep))
    monkeypatch.setattr(sys, "argv", ["watch.py"] + argv)
    with pytest.raises(Stop):
        watch.main()


def state(port):
    return json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/state.json").read())


def frames_after(*sans):
    b = chess.Board()
    out = [b.board_fen()] * 3
    for s in sans:
        b.push_san(s)
        out += [b.board_fen()] * 4
    return out


def test_black_gets_a_king_walk_suggestion_after_e4(monkeypatch):
    # Black cannot move the king at the start, so the fallback may pick any move; use a
    # position where the king can walk: 1.e4 e5 2.Ke2 -> black to move with e7 free.
    run_watch(monkeypatch, frames_after("e4", "e5", "Ke2"), ["--time", "0.3", "--port", "8797"])
    s = state(8797)
    assert s["status"] == "your move" and s["ours"] == "black"
    board = chess.Board(s["fen"])
    move = chess.Move.from_uci(s["move"])
    assert move in board.legal_moves
    assert board.piece_type_at(move.from_square) == chess.KING   # the rule held in the live path


def test_waits_while_it_is_the_friends_turn(monkeypatch):
    run_watch(monkeypatch, frames_after(), ["--time", "0.3", "--port", "8796"], sleeps=6)
    assert state(8796)["status"] == "waiting for your friend"


def test_movelist_ocr_path_syncs_history(monkeypatch, capsys):
    monkeypatch.setattr(watch, "read_text_boxes", lambda boxes: (["e4", "e5", "Ke2"], None))
    run_watch(monkeypatch, frames_after("e4", "e5", "Ke2"), ["--time", "0.3", "--port", "8795"],
              text_boxes={"movelist": [0, 0, 100, 300], "clock_me": [0, 0, 50, 20]})
    assert "history synced from move list" in capsys.readouterr().out
