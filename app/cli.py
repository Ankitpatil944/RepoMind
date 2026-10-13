"""Small command-line client for a running RepoMind API.

    docker compose exec api python -m app.cli ingest /samples/shop_api
    docker compose exec api python -m app.cli ask shop_api "How do users log in?"

A repo can be given by id or by name. REPOMIND_URL overrides the API address.
"""

import argparse
import os
import sys

import httpx


def _client() -> httpx.Client:
    # Generous timeout: the first request may load the embedding models.
    return httpx.Client(base_url=os.environ.get("REPOMIND_URL", "http://localhost:8000"), timeout=600)


def resolve_repo(client: httpx.Client, ref: str) -> int:
    if ref.isdigit():
        return int(ref)
    repos = client.get("/repos").json()
    matches = [r for r in repos if r["name"] == ref]
    if not matches:
        known = ", ".join(r["name"] for r in repos) or "none yet - run `ingest` first"
        raise SystemExit(f"No repo named '{ref}'. Known repos: {known}")
    return max(r["id"] for r in matches)  # newest wins


def format_search(rows: list[dict]) -> str:
    if not rows:
        return "No matches."
    return "\n".join(
        f"[{r['ref']}] {r['file']}:{r['start_line']}-{r['end_line']}  {r['name']} ({r['kind']})"
        for r in rows
    )


def format_endpoints(rows: list[dict]) -> str:
    if not rows:
        return "No endpoints found."
    lines = []
    for e in rows:
        tags = []
        if e["handles_authentication"]:
            tags.append("AUTH")
        if e["requires_auth"]:
            tags.append("protected")
        lines.append(
            f"{e['method']:<7} {e['path']:<34} {e['file']}:{e['line']}  "
            f"{e['handler'] or '(inline)'}  {' '.join(tags)}"
        )
    return "\n".join(lines)


def format_ask(resp: dict) -> str:
    out = []
    if resp.get("answer"):
        out.append(resp["answer"])
    if resp.get("error"):
        out.append(
            f"! No answer: {resp['error']}\n"
            "  Retrieval worked (sources below). To get answers, configure an LLM - see the "
            "README section 'Enable /ask'."
        )
    if resp.get("sources"):
        out.append("\nSources:")
        out.extend(
            f"  [{s['ref']}] {s['file']}:{s['start_line']}-{s['end_line']}  {s['name']}"
            for s in resp["sources"]
        )
    return "\n".join(out)


def format_repos(rows: list[dict]) -> str:
    if not rows:
        return "No repos indexed yet."
    return "\n".join(
        f"{r['id']:>4}  {r['name']:<24} {r['files']:>4} files  {r['chunks']:>5} chunks  {r['path']}"
        for r in rows
    )


def _ingest_path(raw: str) -> str:
    """'myproject' -> '/repos/myproject'; absolute container paths pass through."""
    return raw if raw.startswith("/") else f"/repos/{raw}"


def main(argv: list[str] | None = None, client: httpx.Client | None = None) -> int:
    p = argparse.ArgumentParser(prog="repomind", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("ingest", help="index a folder (path inside the container, e.g. /repos/myproj)")
    s.add_argument("path")
    sub.add_parser("repos", help="list indexed repos")
    for name, help_ in (("ask", "ask a question (needs an LLM)"), ("search", "retrieval only, no LLM")):
        s = sub.add_parser(name, help=help_)
        s.add_argument("repo", help="repo id or name")
        s.add_argument("text", help="your question")
        s.add_argument("-k", type=int, default=6, help="number of results")
    s = sub.add_parser("endpoints", help="list HTTP endpoints with auth classification")
    s.add_argument("repo")
    s.add_argument("--auth", choices=["authentication", "protected", "public"])

    args = p.parse_args(argv)
    c = client or _client()
    try:
        if args.cmd == "ingest":
            r = c.post("/ingest", json={"path": _ingest_path(args.path)})
            _raise(r)
            d = r.json()
            print(
                f"Indexed repo id {d['repo_id']}: {d['files_indexed']} new/changed files, "
                f"{d['files_unchanged']} unchanged, {d['chunks']} chunks."
            )
        elif args.cmd == "repos":
            r = c.get("/repos")
            _raise(r)
            print(format_repos(r.json()))
        elif args.cmd in ("ask", "search"):
            repo_id = resolve_repo(c, args.repo)
            if args.cmd == "ask":
                r = c.post("/ask", json={"repo_id": repo_id, "question": args.text, "top_k": args.k})
            else:
                r = c.post("/search", json={"repo_id": repo_id, "query": args.text, "top_k": args.k})
            _raise(r)
            print(format_ask(r.json()) if args.cmd == "ask" else format_search(r.json()))
        elif args.cmd == "endpoints":
            repo_id = resolve_repo(c, args.repo)
            r = c.get(f"/repos/{repo_id}/endpoints", params={"auth": args.auth} if args.auth else None)
            _raise(r)
            print(format_endpoints(r.json()))
    except httpx.ConnectError:
        print(
            f"Cannot reach RepoMind at {c.base_url}. Is it running? Try: docker compose up -d",
            file=sys.stderr,
        )
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


def _raise(r: httpx.Response) -> None:
    if r.is_success:
        return
    try:
        detail = r.json().get("detail", r.text)
    except ValueError:
        detail = r.text
    raise RuntimeError(f"{r.status_code}: {detail}")


if __name__ == "__main__":
    sys.exit(main())
