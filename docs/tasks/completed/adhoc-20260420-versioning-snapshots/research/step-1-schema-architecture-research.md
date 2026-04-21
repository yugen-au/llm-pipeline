# Step 1 — Schema Architecture: Versioning + Run Snapshots

Scope: schema + indexes only. Write-path invariants handled in step 3.
All decisions in the task prompt are locked; this doc translates them into concrete SQLModel / SQL.

---

## 1. Prompt schema changes

File: `llm_pipeline/db/prompt.py`

### Column adds
```python
is_latest: bool = Field(default=True, index=False)
# existing: version: str = Field(default="1.0", max_length=20)   <- keep
# existing: is_active: bool = Field(default=True)                <- keep
```
No new `deleted_at` column needed — `is_active=False` is the soft-delete flag (per locked decision #3 and #9). Timestamp of deletion is captured by `updated_at`.

### Constraint drops
- Drop existing `UniqueConstraint('prompt_key', 'prompt_type', name='uq_prompts_key_type')`. Multiple version rows per `(prompt_key, prompt_type)` are now legal.

### Final `__table_args__`
```python
__table_args__ = (
    # Partial unique: only one "live + latest" row per (key, type)
    Index(
        "uq_prompts_active_latest",
        "prompt_key", "prompt_type",
        unique=True,
        sqlite_where=text("is_active = 1 AND is_latest = 1"),
        postgresql_where=text("is_active = true AND is_latest = true"),
    ),
    # Hot path: runtime lookup of the active/latest row
    Index(
        "ix_prompts_key_type_live",
        "prompt_key", "prompt_type", "is_active", "is_latest",
    ),
    # Retained
    Index("ix_prompts_category_step", "category", "step_name"),
    Index("ix_prompts_active", "is_active"),
    # History listing (UI)
    Index("ix_prompts_key_type_version", "prompt_key", "prompt_type", "version"),
)
```

Imports needed: `from sqlalchemy import Index, text`. `UniqueConstraint` import can be removed from this file.

Note: `Index(..., unique=True, sqlite_where=...)` is the SQLModel/SQLAlchemy idiom for a partial unique index. Verification in §4.

---

## 2. EvaluationCase schema changes

File: `llm_pipeline/evals/models.py`

### Column adds
```python
version: str = Field(default="1.0", max_length=20)
is_active: bool = Field(default=True)
is_latest: bool = Field(default=True)
```
`name` (existing) becomes the identity key scoped to `dataset_id`. No new `deleted_at`.

### Final `__table_args__`
```python
__table_args__ = (
    # Partial unique: only one "live + latest" row per (dataset_id, name)
    Index(
        "uq_eval_cases_active_latest",
        "dataset_id", "name",
        unique=True,
        sqlite_where=text("is_active = 1 AND is_latest = 1"),
        postgresql_where=text("is_active = true AND is_latest = true"),
    ),
    # Retained dataset scan
    Index("ix_eval_cases_dataset", "dataset_id"),
    # Hot path: runner fetches current live case rows
    Index(
        "ix_eval_cases_dataset_live",
        "dataset_id", "is_active", "is_latest",
    ),
    # History listing for a specific case
    Index("ix_eval_cases_dataset_name_version", "dataset_id", "name", "version"),
)
```

Rationale: matches Prompt shape exactly for consistency. Runner query becomes
`WHERE dataset_id=? AND is_active=1 AND is_latest=1` which is fully index-covered.

---

## 3. EvaluationRun snapshot columns

File: `llm_pipeline/evals/models.py`

### Column adds (all nullable, default NULL)
```python
case_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
prompt_versions: Optional[dict] = Field(default=None, sa_column=Column(JSON))
model_snapshot: Optional[str] = Field(default=None, max_length=100)
instructions_schema_snapshot: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

### Proposed shapes

**`case_versions`** — flat map, string keys (JSON requirement):
```json
{"42": "1.0", "43": "1.2", "44": "1.1"}
```
Keys are `str(case.id)` of the row actually used (which may be a non-latest version row — see §5). Compact and enough to reconstruct; no need to store `name` here because `EvaluationCaseResult.case_id` already points at the specific row.

**`prompt_versions`** — nested by `prompt_key`, inner keyed by `prompt_type`:
```json
{
  "rate_card_parse": {"system": "1.2", "user": "1.0"},
  "rate_card_dedupe": {"system": "2.1"}
}
```

Justification for nested over flat `"rate_card_parse.system"`:
- Matches the natural pair shape (a prompt is a `(key, system?, user?)` bundle).
- Matches YAML file structure (one file per `prompt_key`, `system:` and `user:` sections) so diffing UI can render side-by-side per key.
- No delimiter collision risk (dots allowed in `prompt_key`? unclear — safer to avoid fabricated compound keys).
- Trivial to flatten at read-time for the compare-view badge.

**`model_snapshot`** — plain resolved model name (e.g. `"openai:gpt-4o-2024-08-06"`). `max_length=100` matches `StepModelConfig.model` field width (check before merge; bump if shorter).

**`instructions_schema_snapshot`** — the output of `instructions_cls.model_json_schema()`. Pydantic emits a dict; store as JSON. Legacy rows = NULL and the compare view treats NULL as "unknown / pre-versioning".

---

## 4. Partial unique index syntax — verification

SQLAlchemy supports partial indexes via dialect kwargs on `Index`:

```python
Index(
    "uq_prompts_active_latest",
    "prompt_key", "prompt_type",
    unique=True,
    sqlite_where=text("is_active = 1 AND is_latest = 1"),
    postgresql_where=text("is_active = true AND is_latest = true"),
)
```

- SQLite: supported since 3.8.0 (2014). Project uses SQLite default engine; any modern Python 3.11+ ships with SQLite >= 3.40. Safe.
- Postgres: partial indexes fully supported. `postgresql_where` kwarg is the dialect-native form.
- SQLModel: `__table_args__` is a raw SQLAlchemy tuple, so `Index(...)` works unchanged.
- `text(...)` is required because bare string expressions for `sqlite_where` are deprecated in recent SQLAlchemy 2.x.

**Fallback (if `sqlite_where` ever breaks):** emit the partial unique index via raw DDL inside the migration function using `CREATE UNIQUE INDEX IF NOT EXISTS ... WHERE ...` — same approach as `add_missing_indexes()` in `llm_pipeline/db/__init__.py`. This also sidesteps any `create_all` quirks for partial indexes on pre-existing tables.

Recommendation: declare in `__table_args__` (keeps model truthful) AND emit raw DDL in the migration (guarantees the index actually exists on already-created DBs — `create_all` is a no-op on existing tables and will not create new indexes). Both paths idempotent via `IF NOT EXISTS`.

---

## 5. FK preservation note

`EvaluationCaseResult.case_id` FK -> `eval_cases.id` stays unchanged.

When a run uses case row `id=42, version="1.0"` and a later version `id=87, version="1.1"` is created, the old row `id=42` remains in the table (just with `is_latest=False`). Historical results continue to resolve via FK to the exact row used. This is the only correct behaviour for run reproducibility — row deletion is never performed by the versioning flow. Soft-delete sets `is_active=False` on whichever row is current but does not delete any row.

Implication: `eval_cases` is append-mostly. No cascade-delete changes needed.

---

## 6. Migration script

Project convention (inspected in `llm_pipeline/db/__init__.py`): a single `_migrate_add_columns` function appends `(table, col, type)` tuples to `_MIGRATIONS`, iterates per-table, uses PRAGMA for SQLite introspection and `information_schema` for Postgres, idempotent via presence check. Index additions live in `add_missing_indexes` using `CREATE INDEX IF NOT EXISTS`.

### Changes to `_MIGRATIONS` list

Append these rows:
```python
("prompts", "is_latest", "INTEGER DEFAULT 1"),
("eval_cases", "version", "VARCHAR(20) DEFAULT '1.0'"),
("eval_cases", "is_active", "INTEGER DEFAULT 1"),
("eval_cases", "is_latest", "INTEGER DEFAULT 1"),
("eval_runs", "case_versions", "TEXT"),
("eval_runs", "prompt_versions", "TEXT"),
("eval_runs", "model_snapshot", "VARCHAR(100)"),
("eval_runs", "instructions_schema_snapshot", "TEXT"),
```

Notes:
- SQLite booleans stored as INTEGER. `DEFAULT 1` backfills existing rows to `is_active=True`, `is_latest=True` — correct because prior to versioning every existing row is the one and only live+latest.
- Postgres branch of `_migrate_add_columns` emits `ADD COLUMN IF NOT EXISTS`; types `INTEGER` / `VARCHAR(20)` / `TEXT` are compatible. Postgres will use INT for booleans here (matches existing pattern; SQLAlchemy BOOLEAN maps to INT on SQLite and BOOLEAN on PG — but the existing migration pattern uses INTEGER everywhere and it works fine because SQLModel coerces at query time).
- JSON columns use `TEXT` column type to match existing precedent (see `pipeline_reviews.input_data`, `eval_runs.delta_snapshot`).

### New dedicated migration step: drop old unique + add partial uniques

Add a new function `_migrate_versioning_indexes(engine)` invoked from `init_pipeline_db` after `_migrate_add_columns`. Kept separate from the column list because index DDL is different.

```python
def _migrate_versioning_indexes(engine: Engine) -> None:
    """One-off: retire legacy unique constraints and install partial uniques
    for prompt/eval_case versioning. Idempotent."""
    is_sqlite = engine.url.drivername.startswith("sqlite")

    # ----- prompts: drop legacy unique ---------------------------------
    # SQLite: the old constraint was created as an auto-index named
    # 'uq_prompts_key_type' (matches the name=... passed to UniqueConstraint).
    # It cannot be dropped via ALTER TABLE in SQLite; DROP INDEX works for
    # named unique indexes.
    drops = [
        "DROP INDEX IF EXISTS uq_prompts_key_type",
    ]

    # ----- eval_cases: dedupe before adding partial unique -------------
    # Strategy (locked): keep newest row per (dataset_id, name) by created_at.
    # For any older duplicates, set is_latest=0 so they no longer collide
    # with the partial unique. is_active is left as-is (True) so historical
    # rows remain queryable; the partial unique only fires on is_latest=1.
    # This is safer than deletion and matches the "append-mostly" model.
    dedupe_sql = [
        # Mark all eval_cases rows as is_latest=1 only if they're the newest
        # in their (dataset_id, name) group. All others -> is_latest=0.
        """
        UPDATE eval_cases
           SET is_latest = 0
         WHERE id NOT IN (
               SELECT id FROM (
                   SELECT id,
                          ROW_NUMBER() OVER (
                              PARTITION BY dataset_id, name
                              ORDER BY created_at DESC, id DESC
                          ) AS rn
                     FROM eval_cases
               ) t
               WHERE rn = 1
         )
        """,
    ]

    # ----- partial unique indexes --------------------------------------
    # Raw DDL: create_all won't emit indexes for tables that already exist
    # (reliably), and we want a single, idempotent path for both fresh
    # and upgrading DBs.
    if is_sqlite:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = 1 AND is_latest = 1",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]
    else:
        creates = [
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_prompts_active_latest "
            "ON prompts (prompt_key, prompt_type) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_cases_active_latest "
            "ON eval_cases (dataset_id, name) "
            "WHERE is_active = true AND is_latest = true",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_live "
            "ON prompts (prompt_key, prompt_type, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_prompts_key_type_version "
            "ON prompts (prompt_key, prompt_type, version)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_live "
            "ON eval_cases (dataset_id, is_active, is_latest)",
            "CREATE INDEX IF NOT EXISTS ix_eval_cases_dataset_name_version "
            "ON eval_cases (dataset_id, name, version)",
        ]

    with engine.connect() as conn:
        for stmt in drops:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        for stmt in dedupe_sql:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass  # eval_cases may not exist yet on fresh DB
        for stmt in creates:
            try:
                conn.execute(text(stmt))
            except OperationalError:
                pass
        conn.commit()
```

Wire into `init_pipeline_db` after `_migrate_add_columns(engine)`:
```python
_migrate_add_columns(engine)
_migrate_versioning_indexes(engine)
add_missing_indexes(engine)
```

### Fresh-DB path
`SQLModel.metadata.create_all(engine, tables=[...])` will emit the `Index(..., unique=True, sqlite_where=...)` declared in `__table_args__`. The raw DDL in `_migrate_versioning_indexes` is a no-op second pass (idempotent). Belt-and-braces.

### Dedupe strategy confirmation
Before shipping, a one-shot check should be run (can be a pytest assertion in the migration test):
```sql
SELECT dataset_id, name, COUNT(*) AS n
FROM eval_cases
GROUP BY dataset_id, name
HAVING n > 1;
```
If zero rows: dedupe is a no-op. If non-zero: the `UPDATE ... ROW_NUMBER()` above marks older rows `is_latest=0`, preserving them for history. The result row's FK to `eval_cases.id` is unaffected. "Keep newest by created_at, tiebreak by id DESC" is the locked strategy.

Legacy `EvaluationRun` rows: all four snapshot columns are nullable and default NULL. No backfill needed — the compare view must handle NULL snapshot as "pre-versioning run" gracefully.

---

## 7. Supporting indexes (hot runtime paths)

Already included in §1 and §2 above. Summarised:

| Path | Query | Index used |
|---|---|---|
| Prompt lookup for step execution | `WHERE prompt_key=? AND prompt_type=? AND is_active AND is_latest` | `uq_prompts_active_latest` (partial unique) + `ix_prompts_key_type_live` |
| Prompt version history (UI) | `WHERE prompt_key=? AND prompt_type=? ORDER BY version` | `ix_prompts_key_type_version` |
| Eval case list for runner | `WHERE dataset_id=? AND is_active AND is_latest` | `ix_eval_cases_dataset_live` |
| Eval case history | `WHERE dataset_id=? AND name=? ORDER BY version` | `ix_eval_cases_dataset_name_version` |
| Eval result -> case row | FK `case_id -> eval_cases.id` | PK |

No additional indexes on `eval_runs` snapshot columns — they are per-row payloads, not query predicates. If future UI filters on `model_snapshot`, add then.

---

## 8. Sandbox note

Sandbox uses the same schema (locked decision #8) — no branching, no alternate tables. Sandbox DB gets the same migration path via the same `init_pipeline_db` entrypoint.

---

## 9. Risks / gotchas

1. **SQLite partial-index support.** Requires SQLite >= 3.8.0. Python 3.11 ships with SQLite 3.37+. Verified safe. Prod Postgres path uses `postgresql_where`, also supported.

2. **`create_all` does not add indexes to existing tables.** This is why `add_missing_indexes` exists in the codebase. Our new indexes must be created via raw DDL in `_migrate_versioning_indexes` for upgrading DBs. The `__table_args__` declarations only fire on fresh `create_all` (i.e. new DBs).

3. **Legacy `UniqueConstraint('prompt_key', 'prompt_type')` removal on existing DBs.** SQLite cannot `ALTER TABLE DROP CONSTRAINT`. The constraint was created as a unique index named `uq_prompts_key_type`, droppable via `DROP INDEX IF EXISTS`. The partial unique index then enforces the new invariant. Tested approach. On Postgres, `DROP INDEX IF EXISTS` works identically (the UniqueConstraint is implemented as a unique index there too; constraint name == index name by convention).

4. **SQLModel boolean storage on SQLite.** SQLModel maps `bool` -> INTEGER (0/1). The partial index `WHERE is_active = 1 AND is_latest = 1` uses the integer literal. Matches. If an app writer writes `True` via SQLAlchemy it will coerce to `1` on the SQLite dialect. No mismatch.

5. **Default values via ALTER TABLE in SQLite.** SQLite supports `ADD COLUMN ... DEFAULT <const>` which also backfills. `DEFAULT 1` correctly backfills all existing rows. `DEFAULT '1.0'` on `eval_cases.version` is a string literal — also fine.

6. **Dedupe window.** The dedupe `UPDATE` runs on every startup. On an already-deduped DB the `id NOT IN (SELECT ...)` returns empty and the UPDATE is a no-op. No repeated work cost concern at project scale. For large DBs consider gating behind `PRAGMA user_version`, but not necessary now.

7. **JSON column type on Postgres.** Existing code uses `Column(JSON)` which resolves to `JSON` on PG and `TEXT` (JSON-encoded) on SQLite. New snapshot columns follow the same pattern. In the migration, we add `TEXT` on SQLite / `TEXT` on PG — PG will happily hold JSON in TEXT; queries on the snapshot are read-mostly and parsed app-side, so JSON typing isn't required. If future querying inside `prompt_versions` is needed on PG, the column can be altered to `JSONB` in a later migration.

8. **`is_latest` desync risk.** Two rows with `is_active=1 AND is_latest=1` must never coexist for the same key — the partial unique index guards this at DB level. Any app-level bug that tries to insert a second "latest" row will raise an `IntegrityError` on commit, which is the correct safety net for the write-path helper designed in step 3.

9. **Reset-on-recreate (decision #9).** When a soft-deleted key is recreated via YAML with `version="1.0"` and a `is_active=False, version="1.3"` row exists in history, the new `is_active=1, is_latest=1, version="1.0"` row does not collide (the old row has `is_active=0` so it's outside the partial index predicate). Verified.

10. **`EvaluationCase.metadata_` trailing underscore.** Unrelated to this task but noted: existing column already uses trailing underscore to avoid SQLAlchemy `metadata` attribute collision. New `version`/`is_active`/`is_latest` have no such collision.
