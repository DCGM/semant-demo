"""Levenshtein distance (unit insertions, deletions and substitutions) of a chunk to the
best-matching part of the serialized text, with Myers' bit-parallel algorithm (Myers 1999,
in Hyyrö's formulation). Python integers serve as bit vectors of any length, so a chunk of
1,000 characters against a window of similar length takes milliseconds."""


def _scores(pattern: str, text: str, anchored: bool) -> list[int]:
    """For each ``j``, the distance of ``pattern`` to the best substring of ``text`` ending at
    ``j`` (exclusive ``j + 1``); with ``anchored`` the substring starts at ``text[0]``."""
    m = len(pattern)
    peq: dict[str, int] = {}
    for i, c in enumerate(pattern):
        peq[c] = peq.get(c, 0) | (1 << i)
    mask, high = (1 << m) - 1, 1 << (m - 1)
    pv, mv, score = mask, 0, m
    scores = []
    for c in text:
        eq = peq.get(c, 0)
        xv = eq | mv
        xh = (((eq & pv) + pv) ^ pv) | eq
        ph = (mv | ~(xh | pv)) & mask
        mh = pv & xh
        if ph & high:
            score += 1
        elif mh & high:
            score -= 1
        ph = (ph << 1) | (1 if anchored else 0)
        mh <<= 1
        pv = (mh | ~(xv | ph)) & mask
        mv = ph & xv
        scores.append(score)
    return scores


def best_match(pattern: str, text: str, near: int | None = None) -> tuple[int, int, int]:
    """``(distance, start, end)`` of the substring ``text[start:end]`` with the least edit
    distance to ``pattern``; among equal ones the end closest to ``near`` (default: the first),
    then the start giving the length closest to the pattern's."""
    if not pattern:
        return 0, 0, 0
    if not text:
        return len(pattern), 0, 0
    scores = _scores(pattern, text, anchored=False)
    distance = min(scores)
    ends = [j + 1 for j, s in enumerate(scores) if s == distance]
    end = min(ends, key=lambda e: abs(e - near)) if near is not None else ends[0]
    # the start: the same distance aligning the reversed pattern from the end backwards
    back = _scores(pattern[::-1], text[:end][::-1], anchored=True)
    lengths = [j + 1 for j, s in enumerate(back) if s == distance]
    length = min(lengths, key=lambda n: abs(n - len(pattern))) if lengths else 0
    return distance, end - length, end


def levenshtein(a: str, b: str) -> int:
    """The plain edit distance (for tests and small strings)."""
    if not a or not b:
        return len(a) + len(b)
    scores = _scores(a, b, anchored=True)
    return scores[-1]
