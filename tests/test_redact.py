from app.redact import Redactor


def _clean(text: str) -> tuple[str, dict]:
    r = Redactor()
    return r.clean(text), r.report()


def test_known_token_formats_are_removed():
    text = (
        "aws = 'AKIAIOSFODNN7EXAMPLE'\n"
        "gh = ghp_" + "a" * 36 + "\n"
        "stripe = sk_live_" + "b" * 24 + "\n"
        "jwt = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27uhbUJU1p1r\n"
    )

    out, report = _clean(text)

    for leaked in ("AKIAIOSFODNN7EXAMPLE", "ghp_a", "sk_live_b", "eyJhbGci"):
        assert leaked not in out
    assert report["total"] == 4
    assert set(report["by_kind"]) == {"aws-access-key", "github-token", "stripe-key", "jwt"}


def test_private_key_blocks_are_removed_whole():
    text = "k = '''-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nabc\n-----END RSA PRIVATE KEY-----'''"

    out, report = _clean(text)

    assert "MIIEow" not in out and "[REDACTED:private-key]" in out
    assert report["by_kind"] == {"private-key": 1}


def test_credential_assignments_keep_the_name_and_drop_the_value():
    text = 'DB_PASSWORD = "s3cr3t-value-123"\napi_key: \'abcdef123456\'\nclient_secret="topsecretvalue"'

    out, report = _clean(text)

    assert 'DB_PASSWORD = "[REDACTED:credential-assignment]"' in out
    assert "s3cr3t-value-123" not in out and "abcdef123456" not in out and "topsecretvalue" not in out
    assert report["total"] == 3


def test_urls_with_embedded_passwords_are_scrubbed():
    out, report = _clean("DATABASE_URL = 'postgresql://repomind:hunter2pw@db:5432/repomind'")

    assert "hunter2pw" not in out
    assert "postgresql://repomind:[REDACTED:url-password]@db:5432/repomind" in out
    assert report["by_kind"].get("url-password") == 1


def test_placeholders_and_normal_code_are_left_alone():
    text = (
        'password = "changeme"\n'
        'token = "<your-token>"\n'
        "def hash_password(raw: str, salt: bytes) -> str:\n"
        '    """Derive a PBKDF2 hash for a plaintext password."""\n'
        "    token_ttl = 3600\n"
        'monkey = "banana-split-123"\n'
    )

    out, report = _clean(text)

    assert out == text
    assert report["total"] == 0


def test_counts_accumulate_across_calls():
    r = Redactor()
    r.clean("a = 'AKIAIOSFODNN7EXAMPLE'")
    r.clean("b = 'AKIAIOSFODNN7EXAMPL2'")

    assert r.report() == {"total": 2, "by_kind": {"aws-access-key": 2}}


def test_annotated_defaults_are_redacted_too():
    out, report = _clean('def connect(password: str = "hunter2-hunter2", retries: int = 3): ...')

    assert "hunter2-hunter2" not in out
    assert "retries: int = 3" in out
    assert report["total"] == 1
