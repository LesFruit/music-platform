from __future__ import annotations

from app.db import get_conn
from app.models import Track


def load_library(*, query: str = "", source: str = "") -> list[Track]:
    """Fetch tracks from the indexed DB. Fast — no filesystem scan."""
    clauses = []
    params: list[str] = []
    if source:
        clauses.append("source = ?")
        params.append(source)
    if query:
        clauses.append("(name LIKE ? OR rel_path LIKE ?)")
        q = f"%{query}%"
        params.extend([q, q])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT id, source, name, path, rel_path, size_bytes FROM tracks {where} ORDER BY name COLLATE NOCASE"

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [Track(**dict(r)) for r in rows]


def track_by_id(track_id: str) -> Track | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, source, name, path, rel_path, size_bytes FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
    if not row:
        return None
    return Track(**dict(row))
