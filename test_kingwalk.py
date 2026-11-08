import random
import time

import chess

import kingwalk as k


def test_engine_only_moves_king_when_it_can():
    random.seed(1)
    b = chess.Board()
    t = time.time()
    for _ in range(30):
        if b.is_game_over():
            break
        b.push(random.choice(list(b.legal_moves)))
        if b.is_game_over():
            break
        m, _ = k.pick_move(b, 3)
        king_available = any(b.piece_type_at(x.from_square) == chess.KING for x in b.legal_moves)
        assert (b.piece_type_at(m.from_square) == chess.KING) or not king_available
        b.push(m)
    assert time.time() - t < 60


def test_takes_hanging_piece():
    b = chess.Board("8/8/8/4k3/4N3/8/P7/4K3 b - - 0 1")
    m, _ = k.pick_move(b, 3)
    assert b.san(m) == "Kxe4"


def test_does_not_take_defended_piece():
    b = chess.Board("8/8/8/4k3/4N3/3B4/P7/4K3 b - - 0 1")
    m, _ = k.pick_move(b, 3)
    assert b.san(m) != "Kxe4"


def test_falls_back_when_king_has_no_moves():
    b = chess.Board("k7/8/1QK5/8/8/8/8/r7 b - - 0 1")
    # black king boxed in, rook on a1 still has moves
    assert not [m for m in b.legal_moves if b.piece_type_at(m.from_square) == chess.KING]
    m, _ = k.pick_move(b, 2)
    assert m in b.legal_moves


def test_time_limited_search_returns_legal_move():
    b = chess.Board("rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 2")
    t = time.time()
    m, _, d = k.Searcher().search(b, seconds=1.0)
    assert m in b.legal_moves and d >= 1 and time.time() - t < 3


def test_uci_roundtrip():
    import subprocess, sys
    p = subprocess.run([sys.executable, "kingwalk_uci.py"], text=True, timeout=30,
                       input="uci\nisready\nposition startpos moves e2e4 e7e5\ngo movetime 500\nquit\n",
                       capture_output=True)
    assert "uciok" in p.stdout and "readyok" in p.stdout and "bestmove " in p.stdout


def _mid():
    b = chess.Board()
    for san in ("e4", "e5", "Nf3", "Nc6", "Bc4", "Bc5", "c3", "Nf6", "d4", "exd4", "cxd4", "Bb4+"):
        b.push_san(san)
    return b


def test_every_rule_is_obeyed():
    for name, rule in k.RULES.items():
        b = _mid()                       # white to move, in check from Bb4
        for _ in range(4):
            m, _, _ = k.Searcher(rule).search(b, max_depth=3, seconds=None)
            allowed = [x for x in b.legal_moves if rule(b, x)]
            assert (m in allowed) or not allowed, (name, b.san(m))
            b.push(m)
            if b.is_game_over():
                break
            b.push(random_reply(b))


def random_reply(b):
    return sorted(b.legal_moves, key=lambda x: x.uci())[0]


def test_forward_never_retreats():
    rule = k.RULES["forward"]
    b = chess.Board("4k3/8/8/3p4/8/8/3P4/4K3 w - - 0 1")
    for m in b.legal_moves:
        if rule(b, m):
            assert chess.square_rank(m.to_square) >= chess.square_rank(m.from_square)
    # a king on e1 may step sideways or forward but not back (rank 1 is already the edge)
    assert not rule(chess.Board("4k3/8/8/8/8/8/4K3/8 w - - 0 1"), chess.Move.from_uci("e2e1"))


def test_uci_rule_option_survives_newgame():
    import subprocess, sys
    p = subprocess.run([sys.executable, "kingwalk_uci.py"], text=True, timeout=30,
                       input="uci\nsetoption name Rule value forward\nucinewgame\nposition startpos\ngo movetime 200\nquit\n",
                       capture_output=True)
    assert "option name Rule" in p.stdout and "bestmove " in p.stdout
