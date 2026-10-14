"""Call resolution is name-based, so it must not guess on ubiquitous names."""

import shutil

from app.embed import HashingEmbedder
from app.ingest.service import ingest_repo

SOURCE = """
class Store:
    def get(self, key):
        return self.cache.get(key)      # dict.get on an attribute: not Store.get

    def helper(self):
        return self.get(1)              # self.get -> Store.get (same file)

    def tool(self):
        return 1


def use(d):
    return d.get("x")                   # some dict: must NOT resolve to Store.get


def get():
    return 0                            # a plain function that happens to share the name


def run(obj):
    obj.tool()                          # rarely-common name on another object: resolves
    get()                               # bare call: the function, never the method
"""


def _callers(conn, repo_id, qualified_name):
    rows = conn.execute(
        """
        SELECT DISTINCT c.qualified_name FROM call_edges e
        JOIN chunks c ON c.id = e.caller_chunk_id
        JOIN chunks t ON t.id = e.callee_chunk_id
        WHERE e.repo_id = %s AND t.qualified_name = %s
        """,
        (repo_id, qualified_name),
    ).fetchall()
    return {r[0] for r in rows}


def test_common_method_names_are_not_guessed(conn, tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    (repo / "mod.py").write_text(SOURCE)
    repo_id = ingest_repo(conn, repo, HashingEmbedder())["repo_id"]
    try:
        # Store.get is reached only via self.get(); d.get / self.cache.get are not it
        assert _callers(conn, repo_id, "Store.get") == {"Store.helper"}
        # a bare get() is the module-level function
        assert _callers(conn, repo_id, "get") == {"run"}
        # an uncommon method name on an arbitrary object still resolves
        assert _callers(conn, repo_id, "Store.tool") == {"run"}
    finally:
        conn.execute("DELETE FROM repos WHERE id = %s", (repo_id,))
        conn.commit()
        shutil.rmtree(repo, ignore_errors=True)
