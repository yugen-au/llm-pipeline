"""NFR-004/005: Database query response benchmarks.

Measures query performance at 10k+ row scale:
- NFR-004: list_runs paginated queries <200ms (unfiltered and status-filtered)
- NFR-005: step detail lookup <100ms

Uses standard benchmark() (not pedantic) for 100-200ms targets.
Seeded with 10,000 PipelineRun + 30,000 PipelineStepState rows.
"""

import hashlib
import json
import random
import string
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, text
from sqlmodel import Session, select

from llm_pipeline.state import PipelineRun, PipelineStepState

# -- Constants ----------------------------------------------------------------

NUM_RUNS = 10_000
STEPS_PER_RUN_AVG = 3  # 30k total step rows
STATUS_DISTRIBUTION = {
    "completed": 0.70,
    "failed": 0.20,
    "running": 0.10,
}
SPREAD_DAYS = 30
NFR_004_LIMIT_MS = 200
NFR_005_LIMIT_MS = 100


# -- Helpers ------------------------------------------------------------------


def _random_json_blob(min_kb: int = 1, max_kb: int = 5) -> dict:
    """Generate a dict that serializes to ~min_kb-max_kb of JSON."""
    target_bytes = random.randint(min_kb * 1024, max_kb * 1024)
    # Build a dict with random string values until target size reached
    blob: dict = {}
    current_size = 2  # '{}'
    idx = 0
    while current_size < target_bytes:
        key = f"field_{idx}"
        val = "".join(random.choices(string.ascii_lowercase, k=80))
        entry_size = len(key) + len(val) + 6  # quotes, colon, comma
        blob[key] = val
        current_size += entry_size
        idx += 1
    return blob


def _pick_status() -> str:
    """Weighted random status per distribution."""
    r = random.random()
    cumulative = 0.0
    for status, weight in STATUS_DISTRIBUTION.items():
        cumulative += weight
        if r <= cumulative:
            return status
    return "completed"


# -- Fixture ------------------------------------------------------------------


@pytest.fixture(scope="module")
def large_db_session(benchmark_engine):
    """Module-scoped session seeded with 10k runs + 30k step states.

    Uses benchmark_engine from conftest.py (in-memory SQLite, StaticPool,
    PRAGMA optimizations). Bulk inserts via add_all(), runs ANALYZE after.
    """
    base_time = datetime.now(timezone.utc) - timedelta(days=SPREAD_DAYS)
    random.seed(42)  # reproducible distribution

    runs = []
    steps = []

    for i in range(NUM_RUNS):
        run_id = str(uuid.uuid4())
        status = _pick_status()
        started_at = base_time + timedelta(
            seconds=random.randint(0, SPREAD_DAYS * 86400)
        )
        completed_at = (
            started_at + timedelta(seconds=random.randint(1, 300))
            if status != "running"
            else None
        )
        total_time_ms = (
            int((completed_at - started_at).total_seconds() * 1000)
            if completed_at
            else None
        )

        # Vary step count: 1-5 steps per run, avg ~3
        num_steps = random.randint(1, 5)

        runs.append(
            PipelineRun(
                run_id=run_id,
                pipeline_name="benchmark_pipeline",
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                step_count=num_steps,
                total_time_ms=total_time_ms,
            )
        )

        for step_num in range(1, num_steps + 1):
            steps.append(
                PipelineStepState(
                    pipeline_name="benchmark_pipeline",
                    run_id=run_id,
                    step_name=f"step_{step_num}",
                    step_number=step_num,
                    input_hash=hashlib.sha256(
                        f"{run_id}_{step_num}".encode()
                    ).hexdigest(),
                    result_data=_random_json_blob(1, 5),
                    context_snapshot=_random_json_blob(1, 3),
                    created_at=started_at + timedelta(seconds=step_num * 10),
                    execution_time_ms=random.randint(50, 5000),
                )
            )

    # Bulk insert in batches to avoid excessive memory
    with Session(benchmark_engine) as session:
        # Insert runs in chunks
        batch_size = 2000
        for start in range(0, len(runs), batch_size):
            session.add_all(runs[start : start + batch_size])
        session.commit()

        # Insert steps in chunks
        for start in range(0, len(steps), batch_size):
            session.add_all(steps[start : start + batch_size])
        session.commit()

        # Update SQLite query planner statistics
        session.execute(text("ANALYZE"))
        session.commit()

    # Yield a fresh session for queries
    with Session(benchmark_engine) as session:
        yield session


# -- NFR-004: Run listing benchmarks -----------------------------------------


@pytest.mark.benchmark_group("NFR-004")
def test_list_runs_unfiltered(benchmark, large_db_session):
    """Paginated run listing without filters.

    Mirrors list_runs route: ORDER BY started_at DESC, OFFSET 0, LIMIT 20
    plus a COUNT(*) query. Target: <200ms combined.
    """
    session = large_db_session

    def query():
        # Data query
        data_stmt = (
            select(PipelineRun)
            .order_by(PipelineRun.started_at.desc())
            .offset(0)
            .limit(20)
        )
        rows = session.exec(data_stmt).all()

        # Count query
        count_stmt = select(func.count()).select_from(PipelineRun)
        total = session.scalar(count_stmt)

        return rows, total

    result = benchmark(query)
    rows, total = result

    # Sanity checks
    assert len(rows) == 20
    assert total == NUM_RUNS

    # NFR-004: mean < 200ms
    mean_s = benchmark.stats.stats.mean
    assert mean_s < NFR_004_LIMIT_MS / 1000, (
        f"NFR-004 FAILED: mean {mean_s * 1000:.1f}ms > {NFR_004_LIMIT_MS}ms"
    )


@pytest.mark.benchmark_group("NFR-004")
def test_list_runs_status_filtered(benchmark, large_db_session):
    """Paginated run listing filtered by status='completed'.

    Uses composite index ix_pipeline_runs_status_started(status, started_at).
    Target: <200ms combined.
    """
    session = large_db_session

    def query():
        # Data query
        data_stmt = (
            select(PipelineRun)
            .where(PipelineRun.status == "completed")
            .order_by(PipelineRun.started_at.desc())
            .offset(0)
            .limit(20)
        )
        rows = session.exec(data_stmt).all()

        # Count query
        count_stmt = (
            select(func.count())
            .select_from(PipelineRun)
            .where(PipelineRun.status == "completed")
        )
        total = session.scalar(count_stmt)

        return rows, total

    result = benchmark(query)
    rows, total = result

    # Sanity checks
    assert len(rows) == 20
    # ~70% of 10k = ~7000
    assert total > 6000

    # NFR-004: mean < 200ms
    mean_s = benchmark.stats.stats.mean
    assert mean_s < NFR_004_LIMIT_MS / 1000, (
        f"NFR-004 FAILED: mean {mean_s * 1000:.1f}ms > {NFR_004_LIMIT_MS}ms"
    )


# -- NFR-005: Step detail benchmark ------------------------------------------


@pytest.mark.benchmark_group("NFR-005")
def test_step_detail(benchmark, large_db_session):
    """Single step lookup by run_id + step_number.

    Uses index ix_pipeline_step_states_run(run_id, step_number).
    Target: <100ms.
    """
    session = large_db_session

    # Pick a known run_id from the middle of the dataset
    sample_stmt = select(PipelineRun.run_id).offset(NUM_RUNS // 2).limit(1)
    target_run_id = session.scalar(sample_stmt)
    assert target_run_id is not None, "No run_id found for step_detail benchmark"

    def query():
        stmt = (
            select(PipelineStepState)
            .where(
                PipelineStepState.run_id == target_run_id,
                PipelineStepState.step_number == 1,
            )
        )
        return session.exec(stmt).first()

    result = benchmark(query)

    # Sanity checks
    assert result is not None
    assert result.run_id == target_run_id
    assert result.step_number == 1

    # NFR-005: mean < 100ms
    mean_s = benchmark.stats.stats.mean
    assert mean_s < NFR_005_LIMIT_MS / 1000, (
        f"NFR-005 FAILED: mean {mean_s * 1000:.1f}ms > {NFR_005_LIMIT_MS}ms"
    )
