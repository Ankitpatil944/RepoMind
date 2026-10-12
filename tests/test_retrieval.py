from app.embed import HashingEmbedder
from app.retrieval import hybrid_search, rrf


class _ReverseReranker:
    """Scores later documents higher, so we can see reranking take effect."""

    def score(self, query, documents):
        return [float(i) for i in range(len(documents))]


def test_rrf_rewards_agreement_between_retrievers():
    scores = rrf({"vector": [1, 2, 3], "keyword": [3, 4]})

    assert scores[3] > scores[1] > scores[2]
    assert set(scores) == {1, 2, 3, 4}


def test_rrf_empty():
    assert rrf({"vector": [], "keyword": []}) == {}


def test_hybrid_search_finds_login_endpoint(conn, indexed_repo):
    hits = hybrid_search(conn, indexed_repo, "which endpoint handles login", HashingEmbedder())

    assert hits[0].qualified_name == "login"
    assert hits[0].file == "auth.py"
    assert hits[0].start_line == 10
    assert "keyword" in hits[0].matched_by


def test_hybrid_search_matches_split_identifiers(conn, indexed_repo):
    hits = hybrid_search(conn, indexed_repo, "password hashing", HashingEmbedder(), top_k=3)

    assert "hash_password" in [h.qualified_name for h in hits]


def test_hybrid_search_applies_reranker(conn, indexed_repo):
    plain = hybrid_search(conn, indexed_repo, "login", HashingEmbedder(), top_k=20)
    reranked = hybrid_search(
        conn, indexed_repo, "login", HashingEmbedder(), _ReverseReranker(), top_k=20
    )

    assert [h.chunk_id for h in reranked] == [h.chunk_id for h in reversed(plain)]


def test_hybrid_search_is_scoped_to_repo(conn, indexed_repo):
    assert hybrid_search(conn, indexed_repo + 10_000, "login", HashingEmbedder()) == []
