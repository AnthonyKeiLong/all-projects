"""
Folder scanning and file-pair matching.

Supported extensions: .docx (python-docx) and .doc (Word COM / pywin32).
"""
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Word file extensions that are supported for comparison
_WORD_EXTENSIONS = {".docx", ".doc"}


def scan_folder(folder: str, recursive: bool = True) -> Dict[str, Path]:
    """
    Discover all ``.docx`` and ``.doc`` files under *folder*.

    Returns a dict mapping ``relative/posix/path.docx`` → absolute ``Path``.
    Temporary Word lock files (``~$*``) are silently skipped.

    Raises:
        NotADirectoryError: if *folder* does not exist or is not a directory.
    """
    root = Path(folder).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder}")

    result: Dict[str, Path] = {}

    # Collect both extension types in a single pass with a wildcard, then filter.
    pattern = "**/*" if recursive else "*"
    for fp in root.glob(pattern):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in _WORD_EXTENSIONS:
            continue
        if fp.name.startswith("~$"):   # skip Word temporary lock files
            continue
        rel = fp.relative_to(root)
        result[rel.as_posix()] = fp    # forward-slash keys, portable

    return result


def match_files(
    folder_a: str,
    folder_b: str,
    recursive: bool = True,
    match_by: str = "filename",
) -> List[Tuple[str, Optional[Path], Optional[Path]]]:
    """
    Pair up ``.docx`` files between two folders.

    Args:
        folder_a:  Path to Folder A.
        folder_b:  Path to Folder B.
        recursive: Scan sub-directories when ``True``.
        match_by:
            ``"filename"``     – match on bare filename only (ignores location).
            ``"relative_path"``– match on path relative to each folder root.

    Returns:
        Sorted list of ``(key, path_a, path_b)`` tuples.
        *path_a* or *path_b* is ``None`` when the file exists on only one side.
    """
    files_a = scan_folder(folder_a, recursive)
    files_b = scan_folder(folder_b, recursive)

    pairs: List[Tuple[str, Optional[Path], Optional[Path]]] = []

    if match_by == "filename":
        # Index both sides by bare filename.  If duplicate names exist, the
        # last entry wins (alphabetically by relative path after sorting).
        idx_a: Dict[str, Path] = {}
        for rel in sorted(files_a):
            idx_a[Path(rel).name] = files_a[rel]

        idx_b: Dict[str, Path] = {}
        for rel in sorted(files_b):
            idx_b[Path(rel).name] = files_b[rel]

        for name in sorted(set(idx_a) | set(idx_b)):
            pairs.append((name, idx_a.get(name), idx_b.get(name)))
    else:
        # match_by == "relative_path"
        for key in sorted(set(files_a) | set(files_b)):
            pairs.append((key, files_a.get(key), files_b.get(key)))

    return pairs
