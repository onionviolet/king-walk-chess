#!/usr/bin/env python3
"""Read a chess position from the screen, with no trained model.

You calibrate once per site/theme: show the START position, point at the board's
two corners, and the reader learns what each piece looks like on YOUR screen.
After that it turns any screenshot of the board into a piece placement.

  .venv/bin/python screenread.py calibrate [--profile NAME]
  .venv/bin/python screenread.py calibrate-text [--profile NAME]   # optional: move list + clocks
  .venv/bin/python screenread.py read [--profile NAME]
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import chess
import numpy as np
from PIL import Image

CAL_DIR = Path(__file__).parent / "calibration"
N = 32            # each square is resized to N x N
INSET = 0.10      # crop this fraction off each side (drops coordinate labels)
MASK_DIST = 40.0  # RGB distance from the square background that counts as "piece"


# ---------- reading squares ----------

def square_arrays(img):
    img = img.convert("RGB")
    W, H = img.size
    out = []
    for i in range(8):
        row = []
        for j in range(8):
            x0, x1 = W * j / 8, W * (j + 1) / 8
            y0, y1 = H * i / 8, H * (i + 1) / 8
            dx, dy = (x1 - x0) * INSET, (y1 - y0) * INSET
            crop = img.crop((round(x0 + dx), round(y0 + dy), round(x1 - dx), round(y1 - dy)))
            row.append(np.asarray(crop.resize((N, N), Image.BILINEAR), dtype=np.float32))
        out.append(row)
    return out


def piece_feature(arr):
    """Return (feature, mask fraction, mask). Background is replaced by neutral gray so a
    template learned on a light square also matches the same piece on a dark one."""
    ring = np.concatenate([arr[:2].reshape(-1, 3), arr[-2:].reshape(-1, 3),
                           arr[:, :2].reshape(-1, 3), arr[:, -2:].reshape(-1, 3)])
    bg = np.median(ring, axis=0)
    mask = np.linalg.norm(arr - bg, axis=2) > MASK_DIST
    feat = np.where(mask[..., None], arr, 128.0) / 255.0
    return feat, float(mask.mean()), mask


def key(symbol):
    return ("w" if symbol.isupper() else "b") + symbol.lower()


# ---------- learning from the start position ----------

def learn(img):
    """Learn templates from an image of the start position. Returns a dict."""
    sq = square_arrays(img)
    feats = [[piece_feature(sq[i][j]) for j in range(8)] for i in range(8)]

    def lum(rows):
        vals = []
        for i in rows:
            for j in range(8):
                _, _, mask = feats[i][j]
                if mask.any():
                    vals.append(sq[i][j][mask].mean())
        return float(np.mean(vals))

    white_bottom = lum((6, 7)) > lum((0, 1))
    start = chess.Board()
    groups, empty_fracs, piece_fracs = {}, [], []
    for i in range(8):
        for j in range(8):
            f, frac, _ = feats[i][j]
            rank, file = (7 - i, j) if white_bottom else (i, 7 - j)
            piece = start.piece_at(chess.square(file, rank))
            if piece is None:
                empty_fracs.append(frac)
            else:
                piece_fracs.append(frac)
                groups.setdefault(key(piece.symbol()), []).append(f)
    if max(empty_fracs) >= min(piece_fracs):
        raise ValueError("That does not look like the start position (or the box is off). "
                         "Show all 32 pieces unmoved, with no highlights or arrows.")
    return {
        "white_bottom": white_bottom,
        "occ_thresh": (max(empty_fracs) + min(piece_fracs)) / 2,
        "templates": {k: np.mean(v, axis=0) for k, v in groups.items()},
    }


def read(img, cal):
    """Return (piece placement FEN, confidence). Confidence is the worst ratio of
    runner-up to best template distance over occupied squares (1.0 = a coin flip)."""
    sq = square_arrays(img)
    board = chess.Board(None)
    names = list(cal["templates"])
    worst = float("inf")
    for i in range(8):
        for j in range(8):
            f, frac, _ = piece_feature(sq[i][j])
            if frac < cal["occ_thresh"]:
                continue
            d = np.array([np.mean((f - cal["templates"][n]) ** 2) for n in names])
            order = np.argsort(d)
            worst = min(worst, (d[order[1]] + 1e-9) / (d[order[0]] + 1e-9))
            name = names[order[0]]
            rank, file = (7 - i, j) if cal["white_bottom"] else (i, 7 - j)
            board.set_piece_at(chess.square(file, rank),
                               chess.Piece.from_symbol(name[1].upper() if name[0] == "w" else name[1]))
    return board.board_fen(), (worst if worst != float("inf") else 99.0)


# ---------- saving / loading ----------

def save(profile, box, cal):
    CAL_DIR.mkdir(exist_ok=True)
    np.savez_compressed(CAL_DIR / f"{profile}.npz", **cal["templates"])
    (CAL_DIR / f"{profile}.json").write_text(json.dumps(
        {"box": box, "white_bottom": cal["white_bottom"], "occ_thresh": cal["occ_thresh"]}))


def load(profile):
    meta = json.loads((CAL_DIR / f"{profile}.json").read_text())
    z = np.load(CAL_DIR / f"{profile}.npz")
    return meta["box"], {"white_bottom": meta["white_bottom"], "occ_thresh": meta["occ_thresh"],
                         "templates": {k: z[k] for k in z.files}}


# ---------- macOS capture and mouse ----------

def capture(box):
    """Capture a screen region. box = (x, y, w, h) in points. Needs Screen Recording
    permission for the app that runs this script."""
    x, y, w, h = box
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", path], check=True)
        return Image.open(path).convert("RGB")
    finally:
        os.unlink(path)


def mouse_point():
    js = ('ObjC.import("AppKit"); var f=$.NSScreen.screens.objectAtIndex(0).frame; '
          'var m=$.NSEvent.mouseLocation; JSON.stringify({h:f.size.height,x:m.x,y:m.y})')
    out = subprocess.run(["osascript", "-l", "JavaScript", "-e", js],
                         capture_output=True, text=True, check=True).stdout
    p = json.loads(out)
    return p["x"], p["h"] - p["y"]


def calibrate(profile):
    print("Open the board in the START position: all pieces unmoved, no highlights, no arrows.")
    input("Hover the mouse over the TOP-LEFT corner of the board, then press Enter... ")
    x0, y0 = mouse_point()
    input("Hover over the BOTTOM-RIGHT corner of the board, then press Enter... ")
    x1, y1 = mouse_point()
    size = round((abs(x1 - x0) + abs(y1 - y0)) / 2)
    box = [round(min(x0, x1)), round(min(y0, y1)), size, size]
    img = capture(box)
    cal = learn(img)
    fen, conf = read(img, cal)
    if fen != chess.Board().board_fen():
        raise SystemExit(f"Self-check failed (read {fen}). Re-run and aim at the exact corners.")
    save(profile, box, cal)
    side = "White" if cal["white_bottom"] else "Black"
    print(f"Saved profile '{profile}'. You are {side} (that side is at the bottom). "
          f"Board box {box}, confidence {conf:.1f}.")


def pick_box(name):
    input(f"Hover over the TOP-LEFT corner of the {name}, then press Enter... ")
    x0, y0 = mouse_point()
    input(f"Hover over the BOTTOM-RIGHT corner of the {name}, then press Enter... ")
    x1, y1 = mouse_point()
    return [round(min(x0, x1)), round(min(y0, y1)), round(abs(x1 - x0)), round(abs(y1 - y0))]


TEXT_BOXES = (("movelist", "move list panel"), ("clock_me", "YOUR clock"), ("clock_opp", "your OPPONENT's clock"))


def calibrate_text(profile):
    """Optional: boxes for the move list and clocks. Type s to skip any of them."""
    path = CAL_DIR / f"{profile}.json"
    meta = json.loads(path.read_text())
    text = meta.get("text", {})
    for key_, name in TEXT_BOXES:
        if input(f"Set the {name}? Press Enter to place it, or type s to skip: ").strip().lower() == "s":
            continue
        text[key_] = pick_box(name)
    meta["text"] = text
    path.write_text(json.dumps(meta))
    print("Saved text boxes:", ", ".join(text) or "none")


def load_text(profile):
    """Return the optional text boxes saved by calibrate-text ({} if none)."""
    return json.loads((CAL_DIR / f"{profile}.json").read_text()).get("text", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["calibrate", "calibrate-text", "read"])
    ap.add_argument("--profile", default="default")
    a = ap.parse_args()
    if a.cmd == "calibrate":
        calibrate(a.profile)
    elif a.cmd == "calibrate-text":
        calibrate_text(a.profile)
    else:
        box, cal = load(a.profile)
        fen, conf = read(capture(box), cal)
        print(fen, f"(confidence {conf:.1f})")


if __name__ == "__main__":
    sys.exit(main())
