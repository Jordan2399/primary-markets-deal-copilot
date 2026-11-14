"""Neo4j constraints and indexes. Every statement is idempotent (IF NOT EXISTS)."""

import structlog

from app.db.neo4j import Neo4jClient

log = structlog.get_logger()


def schema_statements(embed_dimensions: int) -> list[str]:
    """The list of Cypher statements that prepare the database (constraints and indexes)."""
    dims = int(embed_dimensions)  # int() so nothing but a number can reach the statement
    return [
        "CREATE CONSTRAINT stage_code IF NOT EXISTS FOR (n:Stage) REQUIRE n.code IS UNIQUE",
        "CREATE CONSTRAINT issuer_id IF NOT EXISTS FOR (n:Issuer) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT deal_id IF NOT EXISTS FOR (n:Deal) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT tranche_id IF NOT EXISTS FOR (n:Tranche) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT isin_unique IF NOT EXISTS FOR (n:Tranche) REQUIRE n.isin IS UNIQUE",
        "CREATE CONSTRAINT task_id IF NOT EXISTS FOR (n:Task) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT investor_id IF NOT EXISTS FOR (n:Investor) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT document_id IF NOT EXISTS FOR (n:Document) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (n:Chunk) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT audit_id IF NOT EXISTS FOR (n:AuditEvent) REQUIRE n.id IS UNIQUE",
        # Day 2b: users and saved conversations. Uniqueness makes MERGE safe to repeat.
        "CREATE CONSTRAINT user_username IF NOT EXISTS FOR (n:User) REQUIRE n.username IS UNIQUE",
        "CREATE CONSTRAINT conversation_id IF NOT EXISTS FOR (n:Conversation) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (n:Message) REQUIRE n.id IS UNIQUE",
        # Every thread query filters by owner, so this index keeps the sidebar list fast.
        "CREATE INDEX conversation_owner IF NOT EXISTS FOR (c:Conversation) ON (c.owner)",
        "CREATE CONSTRAINT order_id IF NOT EXISTS FOR (n:Order) REQUIRE n.id IS UNIQUE",
        "CREATE CONSTRAINT allocation_id IF NOT EXISTS FOR (n:Allocation) REQUIRE n.id IS UNIQUE",
        "CREATE INDEX order_deal IF NOT EXISTS FOR (o:Order) ON (o.deal_id)",
        "CREATE INDEX task_status IF NOT EXISTS FOR (t:Task) ON (t.status)",
        "CREATE INDEX audit_ts IF NOT EXISTS FOR (a:AuditEvent) ON (a.ts)",
        "CREATE INDEX audit_deal IF NOT EXISTS FOR (a:AuditEvent) ON (a.deal_id)",
        (
            "CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS FOR (c:Chunk) ON (c.embedding) "
            "OPTIONS {indexConfig: {`vector.dimensions`: "
            f"{dims}, `vector.similarity_function`: 'cosine'}}}}"
        ),
    ]


async def ensure_schema(client: Neo4jClient, embed_dimensions: int) -> int:
    """Run every statement at startup; IF NOT EXISTS makes repeating it harmless."""
    statements = schema_statements(embed_dimensions)
    for statement in statements:
        await client.run_auto(statement)
    log.info("schema_ready", statements=len(statements))
    return len(statements)
