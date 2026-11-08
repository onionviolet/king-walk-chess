"""The patched Stockfish (vendor/, see patches/stockfish-kingwalk.patch) must enforce the rule."""
import os

import chess
import chess.engine
import pytest

BIN = os.path.join(os.path.dirname(__file__), "vendor/Stockfish/src/stockfish")
pytestmark = pytest.mark.skipif(not os.path.exists(BIN), reason="patched Stockfish not built")


@pytest.fixture()
def engine():
    e = chess.engine.SimpleEngine.popen_uci(BIN)
    yield e
    e.quit()


def test_restricted_side_plays_only_king_moves(engine):
    engine.configure({"KingWalkColor": 1})   # Black may only move its king
    b = chess.Board("r1bq1b1r/ppppkppp/2n2n2/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQ - 5 4")
    assert any(b.piece_type_at(m.from_square) == chess.KING for m in b.legal_moves)
    move = engine.play(chess.Board(b.fen()), chess.engine.Limit(depth=8)).move
    assert b.piece_type_at(move.from_square) == chess.KING


def test_rule_is_off_by_default(engine):
    b = chess.Board()
    move = engine.play(b, chess.engine.Limit(depth=6)).move
    assert b.piece_type_at(move.from_square) != chess.KING   # white has no king move at the start
