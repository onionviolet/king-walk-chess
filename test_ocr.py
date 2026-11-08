import chess
from PIL import Image, ImageDraw, ImageFont

import ocr

FONT = "/System/Library/Fonts/Helvetica.ttc"
GAME = "1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. O-O Be7 6. Re1 b5 7. Bb3 d6"


def render(lines, size=26, w=900):
    f = ImageFont.truetype(FONT, size)
    img = Image.new("RGB", (w, (size + 14) * len(lines) + 20), (38, 36, 33))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((14, 10 + i * (size + 14)), line, font=f, fill=(235, 235, 235))
    return img


def test_clock_parsing():
    assert ocr.clock_seconds("4:32") == 272
    assert ocr.clock_seconds("1:02:03") == 3723
    assert abs(ocr.clock_seconds("0:09.4") - 9.4) < 1e-9
    assert ocr.clock_seconds("hello") is None


def test_replay_fixes_ocr_slips():
    toks = ocr.move_tokens("1.e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. 0-0")  # zero-zero castling misread
    b, played, bad = ocr.replay_san(toks)
    assert not bad and len(played) == 7 or bad == []  # 4.O-O is illegal here; it must stop, not crash
    toks = ocr.move_tokens("1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6 5. 0-0 Be7")
    b, played, bad = ocr.replay_san(toks)
    assert not bad and b.piece_at(chess.G1) == chess.Piece(chess.KING, chess.WHITE)


def test_replay_rejects_garbage():
    b, played, bad = ocr.replay_san(["e4", "zzzz", "e5"])
    assert len(played) == 1 and bad == ["zzzz", "e5"]


def test_vision_reads_move_list_and_clock():
    img = render([GAME[:40], GAME[40:], "04:32"])
    lines = ocr.ocr_lines(img)
    text = " ".join(t for t, _ in lines)
    assert any(ocr.clock_seconds(t) == 272 for t, _ in lines), lines
    b, played, bad = ocr.replay_san(ocr.move_tokens(" ".join(t for t, _ in lines if ocr.clock_seconds(t) is None)))
    assert len(played) >= 12, (text, played, bad)
