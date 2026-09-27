"""Neo4jStore — production graph database store."""
from __future__ import annotations
from typing import Any, Dict, List, Tuple

from code_analyser.models import StoredEdge, StoredNode
from code_analyser import config


_CREATE_SCHEMA = """
CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE;
"""
_CREATE_TENANT_IDX = """
CREATE INDEX node_tenant IF NOT EXISTS FOR (n:Node) ON (n.user_id, n.run_id);
"""
_CREATE_VECTOR_IDX = """
CREATE VECTOR INDEX node_embedding IF NOT EXISTS FOR (n:Node) ON n.embedding
  OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}};
"""

_UPSERT_NODES = """
UNWIND $nodes AS n
MERGE (x:Node {id: n.id})
SET x += {user_id: $user_id, run_id: $run_id, type: n.type, name: n.name,
          description: n.description, path: n.path, line_start: n.line_start,
          line_end: n.line_end, parent_id: n.parent_id,
          ancestor_ids: n.ancestor_ids, props_json: n.props_json,
          embedding: n.embedding}
"""

_UPSERT_EDGES = """
UNWIND $rels AS r
MATCH (a:Node {id: r.source_id}) MATCH (b:Node {id: r.target_id})
MERGE (a)-[e:REL {type: r.type, source_id: r.source_id, target_id: r.target_id}]->(b)
SET e.description = r.description, e.evidence_path = r.evidence_path,
    e.evidence_line = r.evidence_line
"""

_VECTOR_QUERY = """
CALL db.index.vector.queryNodes('node_embedding', $over_fetch, $qvec)
YIELD node, score
WHERE node.user_id = $user_id AND node.run_id = $run_id
RETURN node, score
ORDER BY score DESC
LIMIT $k
"""


class Neo4jStore:
    def __init__(self) -> None:
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
        )

    def ensure_schema(self) -> None:
        with self._driver.session() as session:
            for stmt in [_CREATE_SCHEMA, _CREATE_TENANT_IDX, _CREATE_VECTOR_IDX]:
                try:
                    session.run(stmt)
                except Exception:
                    pass  # index may already exist

    def write(
        self,
        nodes: List[StoredNode],
        edges: List[StoredEdge],
        user_id: str,
        run_id: str,
    ) -> Tuple[int, int]:
        total_n = 0
        total_e = 0
        batch = config.BATCH_SIZE

        with self._driver.session() as session:
            # write nodes in batches
            for i in range(0, len(nodes), batch):
                chunk = nodes[i : i + batch]
                node_dicts = [
                    {
                        "id": n.id,
                        "type": n.type,
                        "name": n.name,
                        "description": n.description,
                        "path": n.path,
                        "line_start": n.line_start,
                        "line_end": n.line_end,
                        "parent_id": n.parent_id,
                        "ancestor_ids": n.ancestor_ids,
                        "props_json": n.props_json,
                        "embedding": n.embedding,
                    }
                    for n in chunk
                ]
                session.run(_UPSERT_NODES, nodes=node_dicts, user_id=user_id, run_id=run_id)
                total_n += len(chunk)

            # write edges in batches
            for i in range(0, len(edges), batch):
                chunk = edges[i : i + batch]
                edge_dicts = [
                    {
                        "source_id": e.source_id,
                        "target_id": e.target_id,
                        "type": e.type,
                        "description": e.description,
                        "evidence_path": e.evidence_path,
                        "evidence_line": e.evidence_line,
                    }
                    for e in chunk
                ]
                session.run(_UPSERT_EDGES, rels=edge_dicts)
                total_e += len(chunk)

        return total_n, total_e

    def query(
        self,
        user_id: str,
        run_id: str,
        qvec: List[float],
        k: int = 8,
    ) -> List[Dict[str, Any]]:
        over_fetch = k * 5
        with self._driver.session() as session:
            result = session.run(
                _VECTOR_QUERY,
                user_id=user_id,
                run_id=run_id,
                qvec=qvec,
                over_fetch=over_fetch,
                k=k,
            )
            nodes = []
            node_ids = set()
            for record in result:
                node = dict(record["node"])
                nodes.append(node)
                node_ids.add(node["id"])

            # expand: ancestors, children, 1-hop neighbours
            expanded_ids = set(node_ids)
            for node in nodes:
                for aid in node.get("ancestor_ids", []):
                    expanded_ids.add(aid)

            # fetch expanded nodes
            expanded_result = session.run(
                "UNWIND $ids AS id MATCH (n:Node {id: id}) RETURN n",
                ids=list(expanded_ids),
            )
            all_nodes = [dict(r["n"]) for r in expanded_result]

            # fetch children
            children_result = session.run(
                "MATCH (n:Node) WHERE n.parent_id IN $ids AND n.user_id = $user_id RETURN n",
                ids=list(expanded_ids),
                user_id=user_id,
            )
            child_nodes = [dict(r["n"]) for r in children_result]
            for cn in child_nodes:
                if cn["id"] not in expanded_ids:
                    all_nodes.append(cn)
                    expanded_ids.add(cn["id"])

            # cap at 60
            all_nodes = all_nodes[:60]
            final_ids = {n["id"] for n in all_nodes}

            # A relationship's own properties do not include its endpoints, so
            # they must be returned explicitly or nobody can tell who calls whom.
            edges_result = session.run(
                """MATCH (a:Node)-[e:REL]->(b:Node)
                WHERE a.id IN $ids AND b.id IN $ids
                RETURN a.id AS source_id, b.id AS target_id, e.type AS type,
                       e.description AS description,
                       e.evidence_path AS evidence_path,
                       e.evidence_line AS evidence_line""",
                ids=list(final_ids),
            )
            edges = [dict(r) for r in edges_result]

            return [{"nodes": all_nodes, "edges": edges}]

    def query_all(
        self, user_id: str, run_id: str, *, limit: int = 500
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """The whole graph for one run: every node and every edge."""
        with self._driver.session() as session:
            nodes = [
                {k: v for k, v in dict(r["n"]).items() if k != "embedding"}
                for r in session.run(
                    "MATCH (n:Node {user_id: $u, run_id: $r}) RETURN n LIMIT $l",
                    u=user_id, r=run_id, l=limit,
                )
            ]
            edges = [
                dict(r) for r in session.run(
                    """MATCH (a:Node {user_id: $u, run_id: $r})-[e:REL]->(b:Node)
                    RETURN a.id AS source_id, b.id AS target_id, e.type AS type,
                           e.description AS description,
                           e.evidence_path AS evidence_path,
                           e.evidence_line AS evidence_line""",
                    u=user_id, r=run_id,
                )
            ]
        return nodes, edges

    def query_nodes(self, user_id: str, run_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
        return self.query_all(user_id, run_id, limit=limit)[0]

    def close(self) -> None:
        self._driver.close()
