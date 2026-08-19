"""Small, dependency-free search adapter for local modeling case cards."""

from __future__ import annotations

import re
from pathlib import Path

from app.schemas.decision import CaseHit


_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9+#.-]{2,}")


class LocalCaseLibrary:
    """Search Markdown case cards without requiring a vector database."""

    def __init__(self, root: str | None = None):
        candidates = []
        if root:
            candidates.append(Path(root))
        here = Path(__file__).resolve()
        candidates.extend(
            [
                here.parents[4] / "math-modeling-skill-pro" / "cases",
                here.parents[3] / "cases",
            ]
        )
        self.root = next((p for p in candidates if p.is_dir()), None)

    def search(self, query: str, limit: int = 8) -> list[CaseHit]:
        if self.root is None:
            return []

        tokens = {token.lower() for token in _TOKEN_RE.findall(query)}
        if not tokens:
            return []

        hits: list[CaseHit] = []
        for path in self.root.glob("*.md"):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            lowered = text.lower()
            matched = [token for token in tokens if token in lowered]
            if not matched:
                continue
            score = len(matched) / max(1, len(tokens))
            title = next(
                (
                    line.lstrip("# ").strip()
                    for line in text.splitlines()
                    if line.startswith("#")
                ),
                path.stem,
            )
            excerpt = " ".join(text.split())[:900]
            hits.append(
                CaseHit(
                    case_id=path.stem,
                    title=title,
                    path=str(path),
                    score=round(score, 4),
                    excerpt=excerpt,
                )
            )
        hits.sort(key=lambda hit: (-hit.score, hit.case_id))
        return hits[:limit]
