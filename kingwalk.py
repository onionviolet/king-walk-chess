#!/usr/bin/env python3
"""King Walk Chess: the engine side may only move its king.

The engine side's other pieces are frozen (they still count as material, block
and guard, but never move). If the engine's king is stuck (no legal move), it
may only play a move that frees the king, meaning the king has a legal move on
its next turn if the opponent passes. Only if no move frees it is any legal move
allowed, so the game cannot deadlock. That is how it opens: one pawn move that
opens a square next to the king, then the king walks.

Play in the terminal:
  .venv/bin/python kingwalk.py [--color white|black] [--time 3] [--odds q,r]
Suggest a move for any position (you are the king-walker):
  .venv/bin/python kingwalk.py --suggest "FEN" [--time 5]
Use from any UCI chess GUI: point it at kingwalk_uci.py (see README.md).
Which moves the engine may play is set by --rule (see RULES below).
"""
import argparse
import math
import sys
import time

import chess

VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330,
          chess.ROOK: 500, chess.QUEEN: 900, chess.KING: 0}
MATE = 100000
EXACT, LOWER, UPPER = 0, 1, 2
MAX_EXT = 4  # check extensions allowed per line
TT_MAX = 2_000_000

# Evaluation weights (tuned by tune.py against a limited Stockfish)
DEFAULT_W = {"hunt": 1.0, "loose": 12.0, "check": 80.0, "escape": 7.0, "boxed": 60.0,
             "advance": 0.0, "passed": 0.0}  # pawn terms (rules that move pawns); off: 6/20 scored
                                             # 0.67 vs 0.74 without in a 48-game check, 2026-11-07


class TimeUp(Exception):
    pass


# Rules decide which moves the restricted side may play. Add your own here.
RULES = {
    "king": lambda b, m: b.piece_type_at(m.from_square) == chess.KING,
    "king+pawns": lambda b, m: b.piece_type_at(m.from_square) in (chess.KING, chess.PAWN),
    "knights": lambda b, m: b.piece_type_at(m.from_square) in (chess.KNIGHT, chess.KING),
    "bishops": lambda b, m: b.piece_type_at(m.from_square) in (chess.BISHOP, chess.KING),
    "no-queen": lambda b, m: b.piece_type_at(m.from_square) != chess.QUEEN,
    # never retreat: white may not lower its rank, black may not raise it
    "forward": lambda b, m: (chess.square_rank(m.to_square) >= chess.square_rank(m.from_square))
    if b.turn == chess.WHITE else (chess.square_rank(m.to_square) <= chess.square_rank(m.from_square)),
    "captures": lambda b, m: b.is_capture(m) or b.gives_check(m),
    "none": lambda b, m: True,  # unrestricted (full-strength mode)
}


def _rule_moves(board, color, rule):
    """Moves the rule allows for `color` (to move), with no fallback."""
    if rule is RULES["king"]:  # fast paths: only generate the pieces that may move
        k = board.king(color)
        return list(board.generate_legal_moves(from_mask=chess.BB_SQUARES[k])) if k is not None else []
    if rule is RULES["king+pawns"]:
        return list(board.generate_legal_moves(from_mask=board.kings & board.occupied_co[color]
                                               | board.pawns & board.occupied_co[color]))
    return [m for m in board.legal_moves if rule(board, m)]


def freeing_moves(board, rule=RULES["king"]):
    """Legal moves after which the rule allows a move again on our next turn
    (tested by letting the opponent pass). For the king rule: moves that unstick the king."""
    color, out = board.turn, []
    for m in board.legal_moves:
        board.push(m)
        board.push(chess.Move.null())
        if _rule_moves(board, color, rule):
            out.append(m)
        board.pop()
        board.pop()
    return out


def _moves_pawns(rule):
    b = chess.Board()
    return any(rule(b, m) for m in b.legal_moves if b.piece_type_at(m.from_square) == chess.PAWN)


def side_moves(board, engine_color, rule=RULES["king"]):
    """Legal moves for the side to move; rule-restricted on the engine's turn.
    If the rule leaves no move, only moves that free it are allowed; if none
    do, any legal move is allowed (no deadlock)."""
    if board.turn != engine_color:
        return list(board.legal_moves)
    return _rule_moves(board, engine_color, rule) or freeing_moves(board, rule) or list(board.legal_moves)


def order_key(board, m, tt_move):
    if m == tt_move:
        return -10**7
    score = 0
    if board.is_capture(m):
        victim = board.piece_type_at(m.to_square) or chess.PAWN
        score += 10 * VALUES[victim] - VALUES[board.piece_type_at(m.from_square)] // 10
    if board.gives_check(m):
        score += 50
    return -score


def pawn_score(board, color, w):
    """Advance and passed-pawn bonus for `color`'s pawns (both grow toward promotion)."""
    score = 0
    enemy_pawns = board.pawns & board.occupied_co[not color]
    for sq in board.pieces(chess.PAWN, color):
        f, r = chess.square_file(sq), chess.square_rank(sq)
        steps = r - 1 if color == chess.WHITE else 6 - r  # 0 on the start rank, 5 one step from queening
        score += w["advance"] * steps
        ahead = 0
        for ff in (f - 1, f, f + 1):
            if 0 <= ff < 8:
                ahead |= chess.BB_FILES[ff]
        if color == chess.WHITE:
            ahead &= ~((1 << (8 * (r + 1))) - 1)   # ranks above r
        else:
            ahead &= (1 << (8 * r)) - 1             # ranks below r
        if not enemy_pawns & ahead:
            score += w["passed"] * (1 + steps * steps / 5)
    return score


def evaluate(board, engine_color, w=DEFAULT_W, pawns=False):
    """Static score from the engine's point of view. `pawns`: add pawn terms
    (when the rule lets the engine move its pawns)."""
    enemy = not engine_color
    score = 0
    ek = board.king(engine_color)
    enemy_pieces = []
    for sq, piece in board.piece_map().items():
        v = VALUES[piece.piece_type]
        if piece.color == engine_color:
            score += v
        else:
            score -= v
            if piece.piece_type != chess.KING:
                enemy_pieces.append((sq, piece))
    if ek is None:
        return score
    if pawns:
        score += pawn_score(board, engine_color, w) - pawn_score(board, enemy, w)

    # The hunt: be near enemy pieces, especially loose (undefended) ones.
    for sq, piece in enemy_pieces:
        v = VALUES[piece.piece_type] // 100 + 1
        d = chess.square_distance(ek, sq)
        score += w["hunt"] * (7 - d) * v
        if d <= 2 and not board.is_attacked_by(enemy, sq):
            score += w["loose"] * v  # loose piece within reach

    # Safety: escape squares and not standing in the open.
    if board.is_attacked_by(enemy, ek):
        score -= w["check"]
    escapes = 0
    own = board.occupied_co[engine_color]
    for t in chess.SquareSet(chess.BB_KING_ATTACKS[ek] & ~own):
        if not board.is_attacked_by(enemy, t):
            escapes += 1
    score += w["escape"] * escapes
    if escapes == 0:
        score -= w["boxed"]  # about to be boxed in (and with frozen pieces, mated)
    return score


class Searcher:
    def __init__(self, rule=RULES["king"], weights=None):
        self.rule = rule
        self.w = {**DEFAULT_W, **(weights or {})}
        self.pawns = rule is not RULES["king"] and _moves_pawns(rule)
        self.tt = {}
        self.killers = {}
        self.history = {}
        self.nodes = 0
        self.deadline = None
        self.engine = None

    def _check_time(self):
        self.nodes += 1
        if self.deadline is not None and self.nodes & 511 == 0 and time.time() > self.deadline:
            raise TimeUp

    def _order(self, board, moves, tt_move, ply):
        killers = self.killers.get(ply, ())
        hist = self.history

        def key(m):
            if m == tt_move:
                return -10**8
            if board.is_capture(m):
                victim = board.piece_type_at(m.to_square) or chess.PAWN
                return -(10**6 + 10 * VALUES[victim] - VALUES[board.piece_type_at(m.from_square)] // 10)
            if m in killers:
                return -(5 * 10**5) + killers.index(m)
            score = hist.get((board.turn, m.from_square, m.to_square), 0)
            if board.gives_check(m):
                score += 10**4
            return -score
        return sorted(moves, key=key)

    def qsearch(self, board, alpha, beta, ply, qdepth=6):
        self._check_time()
        in_check = board.is_check()
        if in_check:
            # no stand-pat while in check: look at every evasion (mates are how a frozen side loses)
            moves = side_moves(board, self.engine, self.rule)
            if not moves:
                return -MATE + ply
            if qdepth == 0:
                e = evaluate(board, self.engine, self.w, self.pawns)
                return e if board.turn == self.engine else -e
            best = -math.inf
            for m in self._order(board, moves, None, ply):
                board.push(m)
                s = -self.qsearch(board, -beta, -alpha, ply + 1, qdepth - 1)
                board.pop()
                best = max(best, s)
                alpha = max(alpha, s)
                if alpha >= beta:
                    break
            return best
        e = evaluate(board, self.engine, self.w, self.pawns)
        stand = e if board.turn == self.engine else -e
        if qdepth == 0 or stand >= beta:
            return stand
        alpha = max(alpha, stand)
        moves = [m for m in side_moves(board, self.engine, self.rule) if board.is_capture(m)]
        for m in sorted(moves, key=lambda m: order_key(board, m, None)):
            board.push(m)
            s = -self.qsearch(board, -beta, -alpha, ply + 1, qdepth - 1)
            board.pop()
            if s >= beta:
                return s
            alpha = max(alpha, s)
        return alpha

    def negamax(self, board, depth, alpha, beta, ply, ext=0):
        self._check_time()
        if board.is_checkmate():
            return -MATE + ply
        if board.is_stalemate() or board.is_insufficient_material() or board.is_repetition(2):
            return 0
        if board.is_check() and ext < MAX_EXT:
            depth += 1  # check extension: see the mating net through
            ext += 1
        if depth <= 0:
            return self.qsearch(board, alpha, beta, ply)

        key = board._transposition_key()
        a0 = alpha
        tt_move = None
        hit = self.tt.get(key)
        if hit:
            hd, flag, val, tt_move = hit
            if hd >= depth:
                if flag == EXACT:
                    return val
                if flag == LOWER:
                    alpha = max(alpha, val)
                elif flag == UPPER:
                    beta = min(beta, val)
                if alpha >= beta:
                    return val

        best, best_move = -math.inf, None
        for m in self._order(board, side_moves(board, self.engine, self.rule), tt_move, ply):
            board.push(m)
            s = -self.negamax(board, depth - 1, -beta, -alpha, ply + 1, ext)
            board.pop()
            if s > best:
                best, best_move = s, m
            alpha = max(alpha, s)
            if alpha >= beta:
                if not board.is_capture(m):
                    ks = self.killers.setdefault(ply, [])
                    if m not in ks:
                        ks.insert(0, m)
                        del ks[2:]
                    hk = (board.turn, m.from_square, m.to_square)
                    self.history[hk] = self.history.get(hk, 0) + depth * depth
                break
        flag = UPPER if best <= a0 else LOWER if best >= beta else EXACT
        self.tt[key] = (depth, flag, best, best_move)
        return best

    def search(self, board, max_depth=64, seconds=3.0, info=None):
        """Iterative deepening. Returns (move, score_cp_for_side_to_move, depth)."""
        self.engine = board.turn
        self.nodes = 0
        self.killers = {}
        self.history = {k: v // 4 for k, v in self.history.items()}  # age old history
        if len(self.tt) > TT_MAX:
            self.tt.clear()
        self.deadline = time.time() + seconds if seconds else None
        root_moves = side_moves(board, self.engine, self.rule)
        best_move, best_score, done = root_moves[0], 0, 0
        base = len(board.move_stack)
        try:
            for depth in range(1, max_depth + 1):
                alpha, cur_best, cur_score = -math.inf, None, -math.inf
                ordered = sorted(root_moves, key=lambda m: order_key(board, m, best_move))
                for m in ordered:
                    board.push(m)
                    s = -self.negamax(board, depth - 1, -math.inf, -alpha, 1)
                    board.pop()
                    if s > cur_score:
                        cur_best, cur_score = m, s
                    alpha = max(alpha, s)
                best_move, best_score, done = cur_best, cur_score, depth
                if info:
                    info(depth, best_score, self.nodes, best_move)
                if abs(best_score) > MATE - 1000:
                    break
        except TimeUp:
            while len(board.move_stack) > base:  # unwind moves left pushed by the abort
                board.pop()
        return best_move, best_score, done


def pick_move(board, depth=4):
    """Fixed-depth helper (used by tests)."""
    s = Searcher()
    m, score, _ = s.search(board, max_depth=depth, seconds=None)
    return m, score


def apply_odds(board, human_color, odds):
    names = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP,
             "n": chess.KNIGHT, "p": chess.PAWN}
    for letter in odds:
        squares = list(board.pieces(names[letter], human_color))
        if squares:
            board.remove_piece_at(squares[-1])
    board.castling_rights = board.clean_castling_rights()
    board.clear_stack()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--color", choices=["white", "black"], default="white", help="your color")
    ap.add_argument("--time", type=float, default=3.0, help="engine seconds per move")
    ap.add_argument("--rule", choices=list(RULES), default="king+pawns", help="which moves the engine may play")
    ap.add_argument("--odds", default="", help="your pieces to remove, e.g. q,r")
    ap.add_argument("--fen", default=None)
    ap.add_argument("--suggest", default=None, metavar="FEN",
                    help="print the best king-walk move for the side to move and exit")
    args = ap.parse_args()

    if args.suggest:
        board = chess.Board(args.suggest)
        move, score, depth = Searcher(RULES[args.rule]).search(board, seconds=args.time)
        print(f"{board.san(move)}  ({move.uci()})  eval {score:+} cp  depth {depth}")
        return

    human = chess.WHITE if args.color == "white" else chess.BLACK
    engine = not human
    board = chess.Board(args.fen) if args.fen else chess.Board()
    odds = [x.strip().lower() for x in args.odds.split(",") if x.strip()]
    if odds:
        apply_odds(board, human, odds)

    searcher = Searcher(RULES[args.rule])
    print(f"King Walk Chess: engine rule = {args.rule}.")
    while not board.is_game_over():
        print("\n" + board.unicode(borders=True, orientation=human))
        if board.turn == engine:
            t = time.time()
            move, score, depth = searcher.search(board, seconds=args.time)
            san = board.san(move)
            board.push(move)
            print(f"Engine plays {san}  (eval {score:+}, depth {depth}, {time.time() - t:.1f}s)")
            continue
        raw = input("Your move: ").strip()
        if raw in ("quit", "q", "exit"):
            return
        if raw == "undo":
            for _ in range(2):
                if board.move_stack:
                    board.pop()
            continue
        try:
            try:
                move = board.parse_san(raw)
            except ValueError:
                move = board.parse_uci(raw)
            if move not in board.legal_moves:
                raise ValueError
        except ValueError:
            print("Illegal or unreadable move.")
            continue
        board.push(move)

    print("\n" + board.unicode(borders=True, orientation=human))
    print("Game over:", board.result(), board.outcome().termination.name)


if __name__ == "__main__":
    sys.exit(main())
