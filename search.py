"""
Semantic search CLI over a target project's OpenSpec documents.

Usage (inside container):
  python -m AgentLoop.search "query"
  python -m AgentLoop.search --reindex "query"

Env vars:
  TARGET_PROJECT    required: target project name (same as main workflow)
  ANTHROPIC_API_KEY required: for RAG answer generation
  SEARCH_MODEL      optional: short model name (haiku/sonnet/opus/fable, default: haiku)
"""
import os
import sys
import struct
import sqlite3
from pathlib import Path
from dotenv import load_dotenv

from AgentLoop.lib.claude_runner import MODEL_IDS

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

_PACKAGE_ROOT = Path(__file__).parent
_REPO_ROOT = _PACKAGE_ROOT.parent

_TOP_K = 5
_EMBEDDING_DIM = 384
_FASTEMBED_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
_DEFAULT_MODEL = "haiku"
_INDEX_SUBDIR = Path("openspec") / ".vector_index"
_DB_NAME = "vector.db"

_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_model_cache = None


def _resolve_project_dir() -> Path:
    target = os.environ.get("TARGET_PROJECT", "").strip()
    if not target:
        print("\033[1;31m[error] TARGET_PROJECT not set. Add it to .env\033[0m", file=sys.stderr)
        sys.exit(1)
    project_dir = _REPO_ROOT / target
    if not project_dir.is_dir():
        print(f"\033[1;31m[error] Project directory not found: {project_dir}\033[0m", file=sys.stderr)
        sys.exit(1)
    return project_dir


def _db_path(project_dir: Path) -> Path:
    index_dir = project_dir / _INDEX_SUBDIR
    index_dir.mkdir(parents=True, exist_ok=True)
    return index_dir / _DB_NAME


def _is_stale(db: Path, openspec_dir: Path) -> bool:
    if not db.exists():
        return True
    db_mtime = db.stat().st_mtime
    for f in openspec_dir.rglob("*.md"):
        if ".vector_index" in f.parts:
            continue
        if f.stat().st_mtime > db_mtime:
            return True
    return False


def _doc_type(path: Path, openspec_dir: Path) -> str:
    rel = path.relative_to(openspec_dir)
    parts = rel.parts
    if parts[0] == "specs":
        return "spec"
    if parts[0] == "changes":
        is_archive = len(parts) > 1 and parts[1] == "archive"
        prefix = "archive" if is_archive else "change"
        kind = {"proposal.md": "proposal", "design.md": "design", "tasks.md": "tasks"}.get(
            path.name, "spec"
        )
        return f"{prefix}_{kind}"
    return "doc"


def _collect_documents(project_dir: Path) -> list[dict]:
    openspec_dir = project_dir / "openspec"
    if not openspec_dir.exists():
        print(
            f"\033[1;31m[error] openspec/ directory not found in {project_dir}\033[0m",
            file=sys.stderr,
        )
        sys.exit(1)
    docs = []
    for path in sorted(openspec_dir.rglob("*.md")):
        if ".vector_index" in path.parts:
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not content:
            continue
        docs.append({
            "path": str(path.relative_to(project_dir)),
            "doc_type": _doc_type(path, openspec_dir),
            "content": content,
        })
    return docs


def _serialize(v) -> bytes:
    arr = list(v)
    return struct.pack(f"{len(arr)}f", *arr)


def _get_model():
    global _model_cache
    if _model_cache is None:
        import warnings
        from fastembed import TextEmbedding
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _model_cache = TextEmbedding(_FASTEMBED_MODEL)
    return _model_cache


def _build_index(db: Path, docs: list[dict]) -> None:
    import sqlite_vec

    print(f"{_DIM}  indexing {len(docs)} documents...{_RESET}", flush=True)
    model = _get_model()
    embeddings = list(model.embed([d["content"] for d in docs]))

    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    conn.executescript("""
        DROP TABLE IF EXISTS vec_documents;
        DROP TABLE IF EXISTS documents;
        CREATE TABLE documents (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            path     TEXT NOT NULL,
            doc_type TEXT NOT NULL,
            content  TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE vec_documents USING vec0(
            embedding float[384]
        );
    """)

    for doc, emb in zip(docs, embeddings):
        cur = conn.execute(
            "INSERT INTO documents (path, doc_type, content) VALUES (?, ?, ?)",
            (doc["path"], doc["doc_type"], doc["content"]),
        )
        conn.execute(
            "INSERT INTO vec_documents (rowid, embedding) VALUES (?, ?)",
            (cur.lastrowid, _serialize(emb)),
        )

    conn.commit()
    conn.close()
    print(f"  ✓ index built ({len(docs)} documents)", flush=True)


def _search(db: Path, query: str) -> list[dict]:
    import sqlite_vec

    model = _get_model()
    query_emb = next(model.query_embed(query))

    conn = sqlite3.connect(db)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    rows = conn.execute(
        """
        SELECT d.path, d.doc_type, d.content, v.distance
        FROM (
            SELECT rowid, distance
            FROM vec_documents
            WHERE embedding MATCH ?
            ORDER BY distance
            LIMIT ?
        ) v
        JOIN documents d ON d.id = v.rowid
        """,
        (_serialize(query_emb), _TOP_K),
    ).fetchall()
    conn.close()

    return [
        {"path": r[0], "doc_type": r[1], "content": r[2], "distance": r[3]}
        for r in rows
    ]


def _build_rag_prompt(query: str, results: list[dict], project_name: str) -> str:
    doc_blocks = "\n\n".join(
        f"--- [{r['path']}] ({r['doc_type']}) ---\n{r['content']}"
        for r in results
    )
    return (
        f'You are a spec knowledge base assistant for the project "{project_name}".\n'
        "Answer the following question based ONLY on the provided spec documents.\n"
        "If the documents don't contain the answer, say so explicitly — "
        "do not supplement with general knowledge.\n"
        "Answer in the same language as the question.\n\n"
        f"Question: {query}\n\n"
        f"Spec documents:\n{doc_blocks}"
    )


def _ask_claude(query: str, results: list[dict], project_name: str) -> str:
    import subprocess

    model_key = os.environ.get("SEARCH_MODEL", _DEFAULT_MODEL)
    model = MODEL_IDS.get(model_key, model_key)
    prompt = _build_rag_prompt(query, results, project_name)

    # Try Anthropic SDK first (when ANTHROPIC_API_KEY is set)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    # Fallback: claude CLI (uses container's OAuth auth)
    result = subprocess.run(
        ["claude", "-p", prompt, "--model", model],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"claude CLI error: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m AgentLoop.search",
        description="Semantic search over target project's OpenSpec documents",
    )
    parser.add_argument("query", help="Question to ask about the project specs")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Force rebuild the vector index before searching",
    )
    args = parser.parse_args()

    # Auth check: SDK path needs ANTHROPIC_API_KEY; CLI path needs claude to be logged in.
    # We can't easily verify CLI auth here, so just proceed and let claude CLI report its own error.

    project_dir = _resolve_project_dir()
    openspec_dir = project_dir / "openspec"
    db = _db_path(project_dir)

    if args.reindex or _is_stale(db, openspec_dir):
        docs = _collect_documents(project_dir)
        if not docs:
            print(
                f"\033[1;31m[error] No markdown documents found in {openspec_dir}\033[0m",
                file=sys.stderr,
            )
            sys.exit(1)
        _build_index(db, docs)

    print(f"\n{_BOLD}> {args.query}{_RESET}\n", flush=True)

    results = _search(db, args.query)
    if not results:
        print("規格文件中沒有找到相關內容。")
        return

    answer = _ask_claude(args.query, results, project_dir.name)
    print(answer)

    print(f"\n{_DIM}Referenced files:{_RESET}")
    for r in results:
        print(f"{_DIM}  - {r['path']} ({r['doc_type']}){_RESET}")


if __name__ == "__main__":
    main()
