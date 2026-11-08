#!/usr/bin/env python3
"""OCR helpers (Apple Vision, runs locally, no download): read a move list and clocks.

The board itself is read by template matching (screenread.py), which is more reliable
than OCR for pieces. OCR is for the TEXT around the board:
  * the move list  -> exact game history (castling rights, en passant, repetition)
  * the clocks     -> time-aware search budget
Every OCR'd move is checked against the legal moves, which fixes most misreads.
"""
import difflib
import io
import re

import chess

CLOCK = re.compile(r"(?<!\d)(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:[.,](\d))?(?!\d)")


def ocr_lines(img):
    """Return [(text, (x, y, w, h))] with normalized boxes, top-to-bottom then left-to-right."""
    import Foundation
    import Vision
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    raw = buf.getvalue()
    data = Foundation.NSData.dataWithBytes_length_(raw, len(raw))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)  # move text is not English; do not "fix" it
    handler.performRequests_error_([req], None)
    out = []
    for obs in req.results() or []:
        cands = obs.topCandidates_(1)
        if not cands:
            continue
        bb = obs.boundingBox()
        out.append((str(cands[0].string()), (bb.origin.x, bb.origin.y, bb.size.width, bb.size.height)))
    out.sort(key=lambda t: (-round(t[1][1] + t[1][3] / 2, 2), t[1][0]))
    return out


def clock_seconds(text):
    """'4:32' -> 272.0, '1:02:03' -> 3723.0, '0:09.4' -> 9.4. None if no clock found."""
    m = CLOCK.search(text)
    if not m:
        return None
    h, mi, s, tenth = m.groups()
    total = int(h or 0) * 3600 + int(mi) * 60 + int(s)
    return total + (int(tenth) / 10 if tenth else 0.0)


def move_tokens(text):
    """Split OCR text into candidate SAN tokens, dropping move numbers and results."""
    toks = []
    for t in re.split(r"[\s,;]+", text):
        t = re.sub(r"^\d+\.+", "", t)  # drop '12.' and the number glued to '12.e4'
        if t and t not in ("1-0", "0-1", "1/2-1/2", "*"):
            toks.append(t)
    return toks


def _clean(tok):
    tok = tok.replace("0-0-0", "O-O-O").replace("0-0", "O-O")
    return tok.replace("l", "1").replace("I", "1") if re.search(r"[a-h][lI]", tok) else tok


def _lev(a, b):
    """Character edit distance."""
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def replay_san(tokens, board=None, max_edits=1):
    """Replay OCR'd SAN tokens from `board` (default: start position). A token that is not
    a legal move is replaced by the closest legal move (<= max_edits character edits),
    otherwise replay stops. Returns (board, moves_played, unresolved_tokens)."""
    board = board.copy() if board else chess.Board()
    played = []
    for i, tok in enumerate(tokens):
        tok = _clean(tok)
        try:
            move = board.parse_san(tok)
        except ValueError:
            legal = {board.san(m).rstrip("+#"): m for m in board.legal_moves}
            near = difflib.get_close_matches(tok.rstrip("+#!?"), legal, n=1, cutoff=0.0)
            if not near:
                return board, played, tokens[i:]
            d = _lev(tok.rstrip("+#!?"), near[0])
            if d > max_edits:
                return board, played, tokens[i:]
            move = legal[near[0]]
        played.append(move)
        board.push(move)
    return board, played, []


if __name__ == "__main__":
    import sys

    from PIL import Image
    for text, box in ocr_lines(Image.open(sys.argv[1])):
        print(f"{text!r:30} clock={clock_seconds(text)}")
