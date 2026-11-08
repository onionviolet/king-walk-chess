"""Synthetic tests for the screen reader. Real sprites are antialiased differently,
so also run `screenread.py calibrate` on your own screen before trusting it."""
import chess
from PIL import Image, ImageDraw, ImageFont

import screenread as sr

FONT = "/System/Library/Fonts/Apple Symbols.ttf"
GLYPH = {chess.KING: "♚", chess.QUEEN: "♛", chess.ROOK: "♜",
         chess.BISHOP: "♝", chess.KNIGHT: "♞", chess.PAWN: "♟"}
MID = "r1bq1rk1/pp2bppp/2n1pn2/2pp4/3P1B2/2PBPN2/PP1N1PPP/R2QK2R"
MID2 = "2r2rk1/1p2qppp/p2bpn2/3p4/3P4/P1N1PN1P/1P1QBPP1/R4RK1"


def render(placement, size=480, flipped=False, light=(238, 238, 210), dark=(118, 150, 86),
           highlight=(), dots=()):
    board = chess.Board(placement + " w - - 0 1")
    img = Image.new("RGB", (size, size))
    d = ImageDraw.Draw(img, "RGBA")
    s = size / 8
    font = ImageFont.truetype(FONT, int(s * 0.8))
    for r in range(8):
        for c in range(8):
            file, rank = (c, 7 - r) if not flipped else (7 - c, r)
            sq = chess.square(file, rank)
            color = light if (file + rank) % 2 else dark
            x, y = c * s, r * s
            d.rectangle([x, y, x + s, y + s], fill=color)
            if sq in highlight:
                d.rectangle([x, y, x + s, y + s], fill=(255, 235, 60, 110))
            piece = board.piece_at(sq)
            if piece:
                white = piece.color == chess.WHITE
                d.text((x + s / 2, y + s / 2), GLYPH[piece.piece_type], font=font, anchor="mm",
                       fill=(250, 250, 250) if white else (30, 30, 30),
                       stroke_width=2, stroke_fill=(20, 20, 20) if white else (230, 230, 230))
            elif sq in dots:
                d.ellipse([x + s * .38, y + s * .38, x + s * .62, y + s * .62], fill=(0, 0, 0, 40))
    return img


def test_white_bottom_roundtrip():
    cal = sr.learn(render(chess.STARTING_BOARD_FEN))
    assert cal["white_bottom"]
    for fen in (MID, MID2):
        got, conf = sr.read(render(fen), cal)
        assert got == fen and conf > 1.5, (got, conf)


def test_black_bottom_roundtrip():
    cal = sr.learn(render(chess.STARTING_BOARD_FEN, flipped=True))
    assert not cal["white_bottom"]
    got, _ = sr.read(render(MID, flipped=True), cal)
    assert got == MID


def test_highlights_and_hint_dots():
    cal = sr.learn(render(chess.STARTING_BOARD_FEN))
    hl = {chess.E4, chess.D5, chess.F3}
    dots = {chess.E5, chess.A5, chess.H4}
    got, _ = sr.read(render(MID, highlight=hl, dots=dots), cal)
    assert got == MID


def test_other_size_and_theme_after_relearn():
    cal = sr.learn(render(chess.STARTING_BOARD_FEN, size=640, light=(240, 217, 181), dark=(181, 136, 99)))
    got, _ = sr.read(render(MID2, size=333, light=(240, 217, 181), dark=(181, 136, 99)), cal)
    assert got == MID2


def test_bad_start_rejected():
    try:
        sr.learn(render(MID))
    except ValueError:
        return
    raise AssertionError("learn accepted a non-start position")
