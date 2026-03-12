# Metadata Ingest and Curation Rules

This document specifies how metadata enters the catalog during ingest, what fields are required versus optional, how missing values are handled, and how metadata can be corrected or enriched after publication.

## Overview

The music platform maintains a two-tier metadata system:
- **Core track record** (`tracks` table): Physical file identity and storage location
- **Extended metadata** (`track_metadata` table): Descriptive and discoverability attributes

## Metadata Schema

### Core Track Fields (Required)

These fields are populated automatically during ingest and cannot be null:

| Field | Type | Source | Description |
|-------|------|--------|-------------|
| `id` | TEXT (PK) | Generated | SHA1 hash of `source:rel_path` (first 16 chars) |
| `source` | TEXT | Ingest | Origin system: `suno`, `ace-step`, `diffrhythm`, `heartmula`, `stable-audio`, `cover-piano`, `cover-orchestra` |
| `name` | TEXT | File | Original filename |
| `path` | TEXT | System | Absolute filesystem path to canonical storage |
| `rel_path` | TEXT | System | Path relative to source root (used for ID generation) |
| `size_bytes` | INTEGER | File | File size in bytes |
| `mtime_ns` | INTEGER | File | Last modification time (nanoseconds since epoch) |
| `duration_sec` | REAL | Manifest/FFprobe | Audio duration in seconds (nullable) |
| `indexed_at` | TEXT | System | ISO 8601 timestamp of catalog registration |

### Extended Metadata Fields (Optional)

These fields enrich discoverability and are populated from manifest files or manual curation:

| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `title` | TEXT | No | Max 200 chars | Display title for the track |
| `artist` | TEXT | No | Max 200 chars | Primary artist or creator name |
| `album` | TEXT | No | Max 200 chars | Album or collection name |
| `genre` | TEXT | No | Max 100 chars | Primary genre classification |
| `bpm` | REAL | No | > 0 | Beats per minute (tempo) |
| `key` | TEXT | No | Max 10 chars | Musical key (e.g., "C Major", "F# Minor") |
| `mood` | TEXT | No | Max 50 chars | Descriptive mood tag |
| `energy` | REAL | No | 0.0 - 1.0 | Energy level score |
| `tags` | TEXT | No | Max 500 chars | Comma-separated searchable tags |
| `description` | TEXT | No | Max 2000 chars | Free-form description |
| `updated_at` | TEXT | Auto | ISO 8601 | Last metadata modification timestamp |

## Ingest Rules

### Source Attribution

Every track must have a `source` value indicating its origin:

- **`suno`**: Tracks from Suno AI generation
- **`ace-step`**: Tracks from ACE-Step generation
- **`diffrhythm`**: Tracks from DiffRhythm generation
- **`heartmula`**: Tracks from Heartmula generation
- **`stable-audio`**: Tracks from Stable Audio generation
- **`cover-piano`**: AI-generated piano covers (music-gen pipeline)
- **`cover-orchestra`**: AI-generated orchestral covers (music-gen pipeline)

### File Path Linkage to Canonical Storage

1. **Source Detection**: Ingest scans source-specific directories for `manifest.json` files
2. **Canonical Location**: Files are copied to `/host/d/Music/covers/{source_type}/` (or equivalent configured path)
3. **Stable Naming**: Destination filename uses `job_id` from manifest to ensure stability
4. **Path Persistence**: The absolute canonical path is stored in `tracks.path`
5. **Relative Path**: Used for ID generation and cross-reference: `{source_type}/{job_id}.{ext}`

### Manifest-Based Metadata Extraction

During ingest, the following metadata is extracted from `manifest.json`:

```json
{
  "job_id": "uuid-or-string",
  "input": {"path": "source-file-reference"},
  "artifacts": {"cover_piano_wav": "path/to/file.wav"},
  "metrics": {"duration_s": 180.5}
}
```

**Default metadata assignments:**
- `title`: "Cover ({source_type})" → e.g., "Cover (Piano)"
- `artist`: "AI Cover"
- `description`: "Generated cover from {input.path}"
- `duration_sec`: From `metrics.duration_s` if present

### Missing Value Handling

| Scenario | Action |
|----------|--------|
| No manifest.json | Skip ingest, log warning |
| Manifest missing fields | Use defaults above, never fail |
| Artifact file missing | Mark ingest as failed, log error |
| Duration not in manifest | Leave `duration_sec` NULL (can be filled later) |
| Duplicate track ID | Skip (idempotent), log as "skipped" |

## Artwork Handling

### Current State
- Artwork is **not** stored in the database
- Artwork files (if present) should follow naming conventions alongside audio files
- Future enhancement: Store artwork paths or embedded metadata references

### Naming Conventions for Artwork Files

When artwork is available, use these patterns:
- `{job_id}.jpg` or `{job_id}.png` - Cover art alongside audio file
- `{job_id}_thumb.jpg` - Thumbnail variant (max 300x300)

## Post-Publication Curation

### Metadata Update API

```
GET  /api/tracks/{track_id}/metadata    # Retrieve current metadata
PUT  /api/tracks/{track_id}/metadata    # Update metadata (partial)
```

**Update rules:**
- All fields in `TrackMetadataUpdate` are optional
- Only provided fields are updated (PATCH-like behavior)
- `updated_at` is automatically set to current timestamp
- Empty strings are treated as valid values (to clear fields)

### Manual Curation Workflow

1. **Discovery**: Use `/api/library/tracks?query=` to find tracks needing curation
2. **Review**: Fetch current metadata via `/api/tracks/{id}/metadata`
3. **Edit**: Submit corrections via PUT endpoint
4. **Audit**: `updated_at` timestamp tracks when changes were made

### Bulk Operations

For bulk metadata updates, use direct database access or create a script that:
1. Queries tracks matching criteria
2. Applies transformation rules
3. Updates via API or direct SQL (with transaction)

## Data Quality Rules

### Validation Constraints

- **String fields**: Truncate silently if exceeding max length
- **BPM**: Must be positive if provided
- **Energy**: Clamped to 0.0-1.0 range
- **Tags**: Normalize to lowercase, trim whitespace around commas

### Enrichment Recommendations

Tracks should be enriched with:
- Accurate `title` and `artist` (replace defaults)
- `genre` for filtering and discovery
- `bpm` and `key` for DJ/mixing use cases
- `tags` for flexible categorization
- `mood` and `energy` for playlist generation

### Source-Specific Defaults

| Source | Default Artist | Default Title Pattern |
|--------|---------------|----------------------|
| `suno` | "Suno AI" | From Suno metadata if available |
| `ace-step` | "ACE-Step" | "Generated Track" |
| `diffrhythm` | "DiffRhythm" | "Generated Track" |
| `heartmula` | "Heartmula" | "Generated Track" |
| `stable-audio` | "Stable Audio" | "Generated Track" |
| `cover-piano` | "AI Cover" | "Cover (Piano)" |
| `cover-orchestra` | "AI Cover" | "Cover (Orchestra)" |

## Storage and Backup

### Metadata Persistence

- All metadata is stored in SQLite (`track_metadata` table)
- Foreign key constraint ensures metadata is deleted when track is deleted
- No separate backup strategy for metadata (included in database backups)

### Migration Considerations

When migrating tracks:
1. Preserve `track_id` to maintain metadata linkage
2. Update `path` to new canonical location
3. Preserve `indexed_at` for historical tracking
4. Set new `mtime_ns` if file is touched during migration

## Future Enhancements

Planned metadata improvements:
- Embedded ID3/metadata extraction from audio files
- Automatic BPM/key detection
- Artwork storage and serving
- Multi-value tags (normalized tag table)
- Metadata versioning/audit log
- Batch edit API
