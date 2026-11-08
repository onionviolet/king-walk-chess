import chess
from watch import Tracker


def test_tracks_one_and_two_plies_and_resyncs():
    t = Tracker(chess.BLACK)
    assert t.update(chess.STARTING_BOARD_FEN) == "resync" and t.board.turn == chess.WHITE
    b = chess.Board(); b.push_san("e4")
    assert t.update(b.board_fen()) == "moved" and t.board.turn == chess.BLACK
    b.push_san("e5"); b.push_san("Nf3")          # two plies at once (missed one read)
    assert t.update(b.board_fen()) == "moved" and t.board.turn == chess.BLACK
    assert t.update(b.board_fen()) == "same"
    other = chess.Board("4k3/8/8/8/8/8/4P3/4K3 w - - 0 1")
    assert t.update(other.board_fen()) == "resync" and t.board.turn == chess.BLACK


def test_castling_guess_and_invalid():
    t = Tracker(chess.WHITE)
    assert t.update("r3k2r/8/8/8/8/8/8/R3K2R") == "resync"
    assert t.board.has_castling_rights(chess.WHITE) and t.board.has_castling_rights(chess.BLACK)
    t2 = Tracker(chess.WHITE)
    assert t2.update("8/8/8/8/8/8/8/8") == "invalid"


def test_budget_seconds():
    from watch import budget_seconds
    assert budget_seconds(None, 3.0) == 3.0
    assert budget_seconds(600, 3.0) == 3.0          # plenty of time: use the cap
    assert abs(budget_seconds(40, 3.0) - 1.0) < 1e-9
    assert budget_seconds(2, 3.0) == 0.3            # low on time: floor


def test_sync_from_movelist_adopts_only_matching_history():
    from watch import sync_from_movelist
    t = Tracker(chess.WHITE)
    placement = chess.Board()
    for san in ("e4", "e5", "Nf3", "Nc6"):
        placement.push_san(san)
    assert sync_from_movelist(t, ["e4", "e5", "Nf3", "Nc6"], placement.board_fen())
    assert len(t.board.move_stack) == 4 and t.board.turn == chess.WHITE
    t2 = Tracker(chess.WHITE)
    assert not sync_from_movelist(t2, ["e4", "e5"], placement.board_fen())      # does not match screen
    assert not sync_from_movelist(t2, ["e4", "zzzz"], placement.board_fen())    # unreadable
    assert t2.board is None
