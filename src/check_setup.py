"""Kiểm tra môi trường Lab07 (checkpoint C0). Chỉ dùng thư viện chuẩn, chạy được trước khi cài gì.

    python -m src.check_setup

Không in giá trị bí mật: với biến trong .env chỉ báo "đã điền" hay "trống".
Thoát với mã 1 nếu có mục bắt buộc chưa đạt.
"""
import json
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_ENV = ("DATABASE_URL", "OPENAI_API_KEY", "LAB_AGENT_MODEL", "PERRY_OLLAMA_URL")
EMBEDDING_MODEL = "embeddinggemma-2"
EMBEDDING_DIMENSIONS = 768
LAB_REPO = "dpduc313/K5-L3A-DAY07-2A202603580-DauPhucDuc-RetrievalContext"
ASSIGNMENT_REPO = "VinUni-AI20k/K5-L3-Day07-Retrieval-Context-Engineering"

# (tên, đạt?, chi tiết); đạt = None là mục thông tin, không tính đạt hay trượt.
results: list[tuple[str, bool | None, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    return ok


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60)


def read_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def check_python() -> None:
    v = sys.version_info
    check("Python ≥ 3.11", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro}")


def check_env() -> dict[str, str]:
    path = ROOT / ".env"
    if not check(".env tồn tại", path.exists(), "chép .env.example thành .env" if not path.exists() else ""):
        return {}
    env = read_env(path)
    for key in REQUIRED_ENV:
        check(f".env: {key}", bool(env.get(key)), "đã điền" if env.get(key) else "trống hoặc thiếu")
    gitignored = run("git", "check-ignore", "-q", ".env").returncode == 0
    check(".env bị git bỏ qua", gitignored, "" if gitignored else "thêm .env vào .gitignore")
    return env


def check_database(env: dict[str, str]) -> None:
    url = urlparse(env.get("DATABASE_URL") or "postgresql://day7:@127.0.0.1:55434/day7_lab")
    host, port = url.hostname or "127.0.0.1", url.port or 5432
    try:
        with socket.create_connection((host, port), timeout=3):
            reachable = True
    except OSError:
        reachable = False
    if not check(f"Postgres nghe ở {host}:{port}", reachable, "" if reachable else "chạy: docker compose up -d"):
        return
    user, db = url.username or "day7", url.path.lstrip("/") or "day7_lab"
    proc = run("docker", "compose", "exec", "-T", "postgres", "psql", "-U", user, "-d", db, "-tAc",
               "SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    version = proc.stdout.strip()
    check("pgvector đã bật trong database", proc.returncode == 0 and bool(version),
          f"vector {version}" if version else (proc.stderr.strip().splitlines() or ["không đọc được"])[-1])
    proc = run("docker", "compose", "exec", "-T", "postgres", "psql", "-U", user, "-d", db, "-tAc",
               "SELECT count(*) FROM lab_chunks")
    count = proc.stdout.strip()
    # Bảng lab_chunks được dựng ở C1, nên ở C0 chưa có là bình thường (không tính lỗi).
    results.append(("Bảng lab_chunks (C1)", None, f"{count} chunk" if proc.returncode == 0 else "chưa có, dựng ở C1"))


def check_ollama(env: dict[str, str]) -> None:
    base = (env.get("PERRY_OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as r:
            models = [m["name"] for m in json.load(r)["models"]]
    except OSError as e:
        check(f"Ollama ở {base}", False, f"không kết nối được: {e}")
        return
    check(f"Ollama ở {base}", True)
    have = any(m.split(":")[0] == EMBEDDING_MODEL for m in models)
    if not check(f"Ollama có {EMBEDDING_MODEL}", have, "" if have else f"chạy: ollama pull {EMBEDDING_MODEL}"):
        return
    body = json.dumps({"model": EMBEDDING_MODEL, "input": "kiểm tra embedding"}).encode()
    req = urllib.request.Request(f"{base}/api/embed", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            dims = len(json.load(r)["embeddings"][0])
    except (OSError, KeyError, IndexError) as e:
        check("Embedding chạy được", False, str(e))
        return
    check(f"Embedding {EMBEDDING_DIMENSIONS} chiều", dims == EMBEDDING_DIMENSIONS, f"{dims} chiều")


def check_git() -> None:
    proc = run("git", "remote", "-v")
    remotes = {}
    for line in proc.stdout.splitlines():
        name, url, kind = line.split()
        remotes.setdefault(name, {})[kind.strip("()")] = url
    origin = remotes.get("origin", {}).get("fetch", "")
    upstream = remotes.get("upstream", {}).get("fetch", "")
    check("origin là repo nộp bài", LAB_REPO.lower() in origin.lower(), origin or "chưa có origin")
    check("upstream là repo đề", ASSIGNMENT_REPO.lower() in upstream.lower(), upstream or "chưa có upstream")
    stale = [u for r in remotes.values() for u in r.values() if re.search(r"github\.com[/:]dpduc/", u, re.I)]
    check("Không remote nào dùng tài khoản dpduc", not stale, ", ".join(stale))


def check_benchmark() -> None:
    path = ROOT / "data" / "questions.json"
    if not check("data/questions.json tồn tại", path.exists()):
        return
    qs = json.loads(path.read_text(encoding="utf-8"))
    count = {(s, a): sum(q["split"] == s and q["answerable"] == a for q in qs) for s in ("dev", "test") for a in (True, False)}
    ok = count[("dev", True)] >= 15 and count[("dev", False)] >= 2 and count[("test", True)] >= 5 and count[("test", False)] >= 2
    check("Benchmark đủ mức tối thiểu", ok,
          f"dev {count[('dev', True)]}+{count[('dev', False)]}, test {count[('test', True)]}+{count[('test', False)]}")


def main() -> int:
    check_python()
    env = check_env()
    check_database(env)
    check_ollama(env)
    check_git()
    check_benchmark()
    width = max(len(name) for name, _, _ in results)
    for name, ok, detail in results:
        mark = "–" if ok is None else ("✓" if ok else "✗")
        print(f"{mark} {name:<{width}}  {detail}")
    failed = [name for name, ok, _ in results if ok is False]
    print(f"\n{len(failed)} mục chưa đạt." if failed else "\nC0: mọi mục bắt buộc đã đạt.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
