"""
Text hashing, comparison, and side-by-side diff computation.
"""
import difflib
import hashlib
from typing import List, Tuple

# Each element is (line_text, tag).
# tag ∈ {"equal", "delete", "insert", "replace", "empty"}
DiffLine  = Tuple[str, str]
DiffLines = List[DiffLine]


def text_hash(text: str) -> str:
    """SHA-256 hex digest of UTF-8 encoded *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compare_texts(text_a: str, text_b: str) -> str:
    """
    Fast equality check via hash.

    Returns ``"identical"`` or ``"different"``.
    """
    return "identical" if text_hash(text_a) == text_hash(text_b) else "different"


def compute_side_by_side_diff(text_a: str, text_b: str) -> Tuple[DiffLines, DiffLines]:
    """
    Produce parallel line lists suitable for a side-by-side diff view.

    Both returned lists have the same length; missing lines on either side are
    represented as ``("", "empty")`` padding entries.

    Tags:
        equal   – line is the same on both sides.
        delete  – line exists in A only.
        insert  – line exists in B only.
        replace – line was changed (present on both sides but different).
        empty   – padding placeholder.
    """
    seq_a = text_a.splitlines()
    seq_b = text_b.splitlines()

    out_a: DiffLines = []
    out_b: DiffLines = []

    matcher = difflib.SequenceMatcher(None, seq_a, seq_b, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in seq_a[i1:i2]:
                out_a.append((line, "equal"))
                out_b.append((line, "equal"))

        elif tag == "delete":
            for line in seq_a[i1:i2]:
                out_a.append((line, "delete"))
                out_b.append(("",   "empty"))

        elif tag == "insert":
            for line in seq_b[j1:j2]:
                out_a.append(("",   "empty"))
                out_b.append((line, "insert"))

        elif tag == "replace":
            block_a = seq_a[i1:i2]
            block_b = seq_b[j1:j2]
            pad     = max(len(block_a), len(block_b))
            for k in range(pad):
                la = block_a[k] if k < len(block_a) else ""
                lb = block_b[k] if k < len(block_b) else ""
                ta = "replace" if k < len(block_a) else "empty"
                tb = "replace" if k < len(block_b) else "empty"
                out_a.append((la, ta))
                out_b.append((lb, tb))

    assert len(out_a) == len(out_b), "Side-by-side diff length mismatch"
    return out_a, out_b


def diff_hunk_positions(lines: DiffLines) -> List[int]:
    """
    Return the 0-based indices where a diff hunk *starts* (first non-equal line
    after a run of equal lines, or the very first line if non-equal).
    """
    positions: List[int] = []
    in_hunk = False
    for i, (_, tag) in enumerate(lines):
        if tag != "equal" and not in_hunk:
            positions.append(i)
            in_hunk = True
        elif tag == "equal":
            in_hunk = False
    return positions
