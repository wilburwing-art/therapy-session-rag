"""CLI for the dev ingestion pipeline."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

from dev.cache import CacheManager
from dev.config import DevConfig, load_config


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stderr,
    )
    # Quiet noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


async def _get_db_session():  # noqa: ANN202
    """Create an async DB session using the app's database config."""
    from src.core.config import get_settings
    from src.core.database import get_session_factory, init_database

    settings = get_settings()
    init_database(settings)
    factory = get_session_factory()
    session = factory()
    return session


async def _run_ingest(
    source_dir: Path,
    config: DevConfig,
    from_stage: str,
    single_file: Path | None = None,
) -> None:
    from dev.pipeline import Pipeline
    from dev.stages.load import setup_dev_scaffolding

    cache = CacheManager(config.cache_dir)
    db = await _get_db_session()

    try:
        _, patient, therapist, consent = await setup_dev_scaffolding(db)

        pipeline = Pipeline(
            config=config,
            cache=cache,
            db_session=db,
            patient=patient,
            therapist=therapist,
            consent=consent,
        )

        if single_file:
            files = [single_file]
        else:
            files = pipeline.discover_audio_files(source_dir)

        if not files:
            click.echo("No audio files found.")
            return

        click.echo(f"Found {len(files)} audio file(s)")
        click.echo(f"Pipeline: from_stage={from_stage}")
        click.echo("-" * 60)

        succeeded = 0
        failed = 0

        for i, audio_path in enumerate(files, 1):
            click.echo(f"\n[{i}/{len(files)}] {audio_path.name}")
            result = await pipeline.process_file(audio_path, from_stage=from_stage)

            if result.error:
                click.echo(f"  ERROR: {result.error}")
                failed += 1
            else:
                parts = []
                if result.transcript_cached:
                    parts.append("transcript=cached")
                if result.chunks_cached:
                    parts.append("chunks=cached")
                if result.embeddings_cached:
                    parts.append("embeddings=cached")
                parts.append(f"chunks={result.chunk_count}")
                parts.append(f"session={result.session_id}")
                click.echo(f"  OK: {', '.join(parts)}")
                succeeded += 1

        click.echo(f"\n{'=' * 60}")
        click.echo(f"Done: {succeeded} succeeded, {failed} failed")

        await pipeline.close()
    finally:
        await db.close()


@click.group()
def cli() -> None:
    """Dev pipeline for bulk audio ingestion and RAG testing."""
    _setup_logging()


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--from-stage",
    type=click.Choice(["transcribe", "chunk", "embed", "load"]),
    default="transcribe",
    help="Stage to start from (earlier stages use cache)",
)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def ingest(source_dir: Path, from_stage: str, config_path: Path | None) -> None:
    """Ingest all audio files from a directory."""
    config = load_config(config_path)
    asyncio.run(_run_ingest(source_dir, config, from_stage))


@cli.command("ingest-file")
@click.argument("audio_file", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--from-stage",
    type=click.Choice(["transcribe", "chunk", "embed", "load"]),
    default="transcribe",
)
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def ingest_file(audio_file: Path, from_stage: str, config_path: Path | None) -> None:
    """Ingest a single audio file."""
    config = load_config(config_path)
    asyncio.run(
        _run_ingest(audio_file.parent, config, from_stage, single_file=audio_file)
    )


@cli.command()
def status() -> None:
    """Show pipeline status and cache stats."""
    config = load_config()
    cache = CacheManager(config.cache_dir)
    stats = cache.get_stats()

    click.echo("Cache Status:")
    click.echo("-" * 40)
    for stage, info in stats.items():
        size_mb = info["size_bytes"] / 1e6
        click.echo(f"  {stage:15s}  {info['count']:4d} files  ({size_mb:.1f} MB)")

    total_files = sum(s["count"] for s in stats.values())
    total_mb = sum(s["size_bytes"] for s in stats.values()) / 1e6
    click.echo(f"  {'total':15s}  {total_files:4d} files  ({total_mb:.1f} MB)")


@cli.command()
@click.argument("message")
@click.option("--top-k", default=5, help="Number of context chunks to retrieve")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def query(message: str, top_k: int, config_path: Path | None) -> None:
    """Run a RAG query against loaded data."""

    async def _run() -> None:
        from dev.eval.query import evaluate_query

        config = load_config(config_path)
        config.chat.top_k = top_k
        db = await _get_db_session()

        try:
            result = await evaluate_query(db, message, config.chat)

            click.echo(f"\n{result.response}")

            if result.sources:
                click.echo(f"\n--- {len(result.sources)} sources ---")
                for s in result.sources:
                    score = f"{s['relevance_score']:.2f}" if s.get("relevance_score") else "?"
                    preview = s.get("content_preview", "")[:80]
                    speaker = f" [{s['speaker']}]" if s.get("speaker") else ""
                    click.echo(f"  [{score}]{speaker} {preview}...")
        finally:
            await db.close()

    asyncio.run(_run())


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
def chat(config_path: Path | None) -> None:
    """Interactive RAG chat REPL."""

    async def _run() -> None:
        from dev.eval.query import interactive_chat

        config = load_config(config_path)
        db = await _get_db_session()

        try:
            await interactive_chat(db, config.chat)
        finally:
            await db.close()

    asyncio.run(_run())


@cli.group("cache")
def cache_group() -> None:
    """Manage the pipeline cache."""
    pass


@cache_group.command("stats")
def cache_stats() -> None:
    """Show cache statistics."""
    config = load_config()
    cache = CacheManager(config.cache_dir)
    stats = cache.get_stats()

    for stage, info in stats.items():
        size_mb = info["size_bytes"] / 1e6
        click.echo(f"{stage:15s}  {info['count']:4d} files  ({size_mb:.1f} MB)")


@cache_group.command("clear")
@click.option(
    "--stage",
    type=click.Choice(["transcripts", "chunks", "embeddings"]),
    default=None,
    help="Stage to clear (omit for all)",
)
@click.option("--all", "clear_all", is_flag=True, help="Clear all cache layers")
def cache_clear(stage: str | None, clear_all: bool) -> None:
    """Clear cached pipeline data."""
    config = load_config()
    cache = CacheManager(config.cache_dir)

    if clear_all or stage is None:
        count = cache.clear_all()
        click.echo(f"Cleared {count} cached files (all stages)")
    else:
        count = cache.clear_stage(stage)
        click.echo(f"Cleared {count} cached files ({stage})")
