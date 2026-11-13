"""Command line: python -m app.seed [--reset] [--fake-embeddings | --no-embeddings] [--force]"""

import argparse
import asyncio
import sys
from datetime import date

from app.auth.models import DEFAULT_DEMO_PASSWORD
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.neo4j import Neo4jClient
from app.documents.repository import Neo4jDocumentRepository
from app.documents.service import DocumentService
from app.llm.base import LLMProvider
from app.llm.factory import create_provider
from app.llm.fake import FakeLLM
from app.seed.runner import seed_database


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m app.seed", description="Load synthetic data.")
    parser.add_argument("--reset", action="store_true", help="delete ALL data first (dev only)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--no-embeddings", action="store_true", help="skip the playbook (no Ollama needed)"
    )
    group.add_argument(
        "--fake-embeddings",
        action="store_true",
        help="use a fake embedder (for CI; retrieval quality is poor)",
    )
    parser.add_argument(
        "--force", action="store_true", help="allow running when APP_ENV=production"
    )
    return parser.parse_args(argv)


async def main(argv: list[str]) -> int:
    args = parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level)

    if settings.app_env == "production" and not args.force:
        print("Refusing to seed: APP_ENV=production. Production is never seeded automatically.")
        print("Use --force only if you are sure.")
        return 2

    # In development the demo users get DEMO_USER_PASSWORD, or a documented default. Elsewhere
    # they are only created when a password is set explicitly.
    demo_password: str | None = settings.demo_user_password or (
        DEFAULT_DEMO_PASSWORD if settings.app_env == "development" else None
    )

    db = Neo4jClient(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password, settings.neo4j_database
    )
    llm: LLMProvider | None = None
    try:
        docs: DocumentService | None = None
        if args.fake_embeddings:
            llm = FakeLLM(dimensions=settings.embed_dimensions)
        elif not args.no_embeddings:
            llm = create_provider(settings)
        if llm is not None:
            docs = DocumentService(
                Neo4jDocumentRepository(db),
                llm,
                query_prefix=settings.query_prefix,
                document_prefix=settings.document_prefix,
                default_k=settings.retrieval_k,
                dimensions=settings.embed_dimensions,
            )
        report = await seed_database(
            db,
            docs,
            today=date.today(),
            embed_dimensions=settings.embed_dimensions,
            reset=args.reset,
            demo_password=demo_password,
        )
    finally:
        if llm is not None:
            await llm.aclose()
        await db.close()

    print("Seed finished:")
    for key, value in report.__dict__.items():
        print(f"  {key}: {value}")
    if report.users_created:
        print("Demo users were created. Sign in with a username from the login page.")
    if docs is None:
        print("Playbook was skipped, so the Copilot cannot answer process questions yet.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
