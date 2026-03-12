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


def search(query: str = "", types: str = "all") -> dict:
    """Global search across tracks, artists, albums, and playlists.

    Args:
        query: Search query string
        types: Filter by type - "all", "tracks", "playlists" (comma-separated for multiple)

    Returns:
        Dictionary with search results grouped by type
    """
    results = {"tracks": [], "playlists": [], "albums": [], "artists": []}
    if not query:
        return results

    q = f"%{query}%"
    type_list = [t.strip() for t in types.split(",")] if types != "all" else ["tracks", "playlists", "albums", "artists"]

    with get_conn() as conn:
        # Search tracks (by name, path, and metadata: title, artist, album)
        if "tracks" in type_list:
            track_rows = conn.execute("""
                SELECT t.id, t.source, t.name, t.path, t.rel_path, t.size_bytes,
                       COALESCE(m.title, t.name) as display_title,
                       COALESCE(m.artist, '') as artist,
                       COALESCE(m.album, '') as album
                FROM tracks t
                LEFT JOIN track_metadata m ON t.id = m.track_id
                WHERE t.name LIKE ? OR t.rel_path LIKE ? OR m.title LIKE ? OR m.artist LIKE ? OR m.album LIKE ?
                ORDER BY t.name COLLATE NOCASE
                LIMIT 50
            """, (q, q, q, q, q)).fetchall()
            results["tracks"] = [
                {
                    "id": r["id"],
                    "source": r["source"],
                    "name": r["display_title"],
                    "original_name": r["name"],
                    "path": r["path"],
                    "rel_path": r["rel_path"],
                    "size_bytes": r["size_bytes"],
                    "artist": r["artist"],
                    "album": r["album"],
                }
                for r in track_rows
            ]

        # Search playlists (by name)
        if "playlists" in type_list:
            playlist_rows = conn.execute("""
                SELECT id, name, created_at
                FROM playlists
                WHERE name LIKE ?
                ORDER BY name COLLATE NOCASE
                LIMIT 20
            """, (q,)).fetchall()
            results["playlists"] = [dict(r) for r in playlist_rows]

        # Search albums (from track_metadata)
        if "albums" in type_list:
            album_rows = conn.execute("""
                SELECT DISTINCT album as name, COUNT(*) as track_count
                FROM track_metadata
                WHERE album LIKE ? AND album IS NOT NULL AND album != ''
                GROUP BY album
                ORDER BY album COLLATE NOCASE
                LIMIT 20
            """, (q,)).fetchall()
            results["albums"] = [{"name": r["name"], "track_count": r["track_count"]} for r in album_rows]

        # Search artists (from track_metadata)
        if "artists" in type_list:
            artist_rows = conn.execute("""
                SELECT DISTINCT artist as name, COUNT(*) as track_count
                FROM track_metadata
                WHERE artist LIKE ? AND artist IS NOT NULL AND artist != ''
                GROUP BY artist
                ORDER BY artist COLLATE NOCASE
                LIMIT 20
            """, (q,)).fetchall()
            results["artists"] = [{"name": r["name"], "track_count": r["track_count"]} for r in artist_rows]

    return results


def search_suggestions(query: str = "", limit: int = 10) -> list[dict]:
    """Get search suggestions based on query.

    Returns suggestions for tracks, artists, albums, and playlists.
    """
    if not query or len(query) < 1:
        return []

    suggestions = []
    q = f"{query}%"

    with get_conn() as conn:
        # Track name suggestions
        track_rows = conn.execute("""
            SELECT DISTINCT COALESCE(m.title, t.name) as name, 'track' as type, t.id as ref_id
            FROM tracks t
            LEFT JOIN track_metadata m ON t.id = m.track_id
            WHERE t.name LIKE ? OR m.title LIKE ?
            ORDER BY t.name COLLATE NOCASE
            LIMIT ?
        """, (q, q, limit)).fetchall()
        suggestions.extend([{"name": r["name"], "type": r["type"], "ref_id": r["ref_id"]} for r in track_rows])

        # Artist suggestions
        artist_rows = conn.execute("""
            SELECT DISTINCT artist as name, 'artist' as type
            FROM track_metadata
            WHERE artist LIKE ? AND artist IS NOT NULL AND artist != ''
            ORDER BY artist COLLATE NOCASE
            LIMIT ?
        """, (q, limit)).fetchall()
        suggestions.extend([{"name": r["name"], "type": r["type"]} for r in artist_rows])

        # Album suggestions
        album_rows = conn.execute("""
            SELECT DISTINCT album as name, 'album' as type
            FROM track_metadata
            WHERE album LIKE ? AND album IS NOT NULL AND album != ''
            ORDER BY album COLLATE NOCASE
            LIMIT ?
        """, (q, limit)).fetchall()
        suggestions.extend([{"name": r["name"], "type": r["type"]} for r in album_rows])

        # Playlist suggestions
        playlist_rows = conn.execute("""
            SELECT name, 'playlist' as type, id as ref_id
            FROM playlists
            WHERE name LIKE ?
            ORDER BY name COLLATE NOCASE
            LIMIT ?
        """, (q, limit)).fetchall()
        suggestions.extend([{"name": r["name"], "type": r["type"], "ref_id": r["ref_id"]} for r in playlist_rows])

    # Remove duplicates and limit
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        key = (s["name"].lower(), s["type"])
        if key not in seen:
            seen.add(key)
            unique_suggestions.append(s)

    return unique_suggestions[:limit]


def track_by_id(track_id: str) -> Track | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, source, name, path, rel_path, size_bytes FROM tracks WHERE id = ?",
            (track_id,),
        ).fetchone()
    if not row:
        return None
    return Track(**dict(row))
