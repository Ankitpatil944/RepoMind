from app.text import query_terms, search_text, split_identifiers


def test_split_identifiers_handles_snake_camel_and_acronyms():
    assert split_identifiers("hash_password") == ["hash", "password"]
    assert split_identifiers("hashPassword") == ["hash", "password"]
    assert split_identifiers("HTTPServer2") == ["http", "server", "2"]


def test_query_terms_drops_stopwords_and_dedupes():
    assert query_terms("Which endpoint handles the login login?") == ["endpoint", "handles", "login"]


def test_search_text_exposes_split_names():
    text = search_text("app/auth.py", "SessionStore.get", "return None")

    assert "session store get" in text
    assert text.endswith("return None")
