"""Commit data/docs i push na main, nawet gdy main ruszyl sie w trakcie joba.

weekly-history odpala sie w sobote o 03:00 UTC i przez kilka godzin trzyma
checkout. daily-nevia o 05:00 commituje na main. Sam `git push` konczy sie
`! [rejected] main -> main (fetch first)` i caly fetch przepada.

Tu: commit lokalny, fetch origin/main, a jesli main poszedl do przodu —
odtwarzamy nasze pliki na nowym main. Nakladajace sie surowe JSON/CSV
scalamy (snapshot_merge), a data/gold i docs/data budujemy od nowa
(build_gold), bo to pochodne. Push powtarzamy, gdy w miedzyczasie znowu
ktos zdazyl popchnac.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from snapshot_merge import is_derived, merge_file

PATHS = ("config.yaml", "data", "docs")
ENV = {
    **os.environ,
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_EDITOR": "true",
    "GIT_PAGER": "cat",
}


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=ENV,
    )
    if check and result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {' '.join(args)} failed ({result.returncode}): {stderr}")
    return result


def git_text(repo: Path, *args: str, check: bool = True) -> str:
    result = git(repo, *args, check=check)
    return result.stdout.decode("utf-8", "replace")


def ensure_identity(repo: Path) -> None:
    git(repo, "config", "user.email", "github-actions[bot]@users.noreply.github.com")
    git(repo, "config", "user.name", "github-actions[bot]")


def _existing(repo: Path) -> list[str]:
    return [path for path in PATHS if (repo / path).exists()]


def commit_paths(repo: Path, message: str) -> bool:
    paths = _existing(repo)
    if not paths:
        print("nothing to commit (no config.yaml/data/docs)")
        return False
    git(repo, "add", "--", *paths)
    if git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("nothing to commit")
        return False
    git(repo, "commit", "-m", message)
    print(f"committed {git_text(repo, 'rev-parse', '--short', 'HEAD').strip()}")
    return True


def _shallow(repo: Path) -> bool:
    return git_text(repo, "rev-parse", "--is-shallow-repository").strip() == "true"


def fetch_main(repo: Path, remote: str, branch: str) -> None:
    if _shallow(repo):
        # checkout@v4 domyslnie bierze jeden commit. Bez historii merge-base
        # z main, ktory odjechal, nie ma sie na czym oprzec.
        unshallow = git(repo, "fetch", "--unshallow", remote, check=False)
        if unshallow.returncode != 0:
            git(repo, "fetch", "--deepen=500", remote, branch, check=False)
    result = git(repo, "fetch", remote, branch, check=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git fetch {remote} {branch} failed: {stderr}")
    if git(repo, "rev-parse", "--verify", "--quiet", f"{remote}/{branch}", check=False).returncode != 0:
        raise RuntimeError(f"{remote}/{branch} does not exist after fetch")


def _rev(repo: Path, ref: str) -> str:
    return git_text(repo, "rev-parse", ref).strip()


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    return git(repo, "merge-base", "--is-ancestor", ancestor, descendant, check=False).returncode == 0


def _blob(repo: Path, rev: str, path: str) -> bytes | None:
    result = git(repo, "show", f"{rev}:{path}", check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def _changed(repo: Path, a: str, b: str) -> list[str]:
    text = git_text(repo, "diff", "--name-only", "--no-renames", a, b)
    return [line for line in text.splitlines() if line]


def _merge_base(repo: Path, a: str, b: str) -> str:
    result = git(repo, "merge-base", a, b, check=False)
    if result.returncode != 0:
        raise RuntimeError(
            "no merge-base with origin/main: "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    return result.stdout.decode().strip()


def replay(repo: Path, ours: str, upstream: str, message: str, rebuild) -> None:
    base = _merge_base(repo, ours, upstream)
    ours_files = _changed(repo, base, ours)
    main_files = set(_changed(repo, base, upstream))
    raw_overlap = [path for path in ours_files if path in main_files and not is_derived(path)]
    print(
        f"replaying {ours[:8]} onto {upstream[:8]}: "
        f"{len(raw_overlap)} raw file(s) overlap, derived outputs rebuilt"
    )
    for path in raw_overlap:
        print(f"  merge {path}")
    git(repo, "checkout", "--detach", upstream)
    for path in ours_files:
        if is_derived(path):
            continue
        ours_blob = _blob(repo, ours, path)
        if path not in main_files:
            if ours_blob is None:
                git(repo, "rm", "-f", "--ignore-unmatch", "--", path, check=False)
            else:
                git(repo, "checkout", ours, "--", path)
            continue
        merged = merge_file(path, _blob(repo, base, path), ours_blob, _blob(repo, upstream, path))
        dest = repo / path
        if merged is None:
            if dest.exists() or ours_blob is None:
                git(repo, "rm", "-f", "--ignore-unmatch", "--", path, check=False)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(merged)
        git(repo, "add", "--", path)
    print("rebuilding gold from merged raw data")
    rebuild(repo)
    paths = _existing(repo)
    if paths:
        git(repo, "add", "--", *paths)
    if git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0:
        print("replay produced no new changes")
        return
    git(repo, "commit", "-m", message)
    print(f"replay commit {git_text(repo, 'rev-parse', '--short', 'HEAD').strip()}")


def push_rejected(stderr: str) -> bool:
    text = stderr.lower()
    return any(token in text for token in ("fetch first", "non-fast-forward", "[rejected]", "cannot lock ref"))


def push_head(repo: Path, remote: str, branch: str) -> bool:
    result = git(repo, "push", remote, f"HEAD:{branch}", check=False)
    stderr = result.stderr.decode("utf-8", "replace")
    if result.returncode == 0:
        return True
    if push_rejected(stderr):
        print(stderr.strip())
        return False
    raise RuntimeError(f"git push failed ({result.returncode}): {stderr.strip()}")


def default_rebuild(repo: Path) -> None:
    script = repo / "scripts" / "build_gold.py"
    result = subprocess.run([sys.executable, str(script)], cwd=repo)
    if result.returncode != 0:
        raise SystemExit(f"build_gold failed ({result.returncode})")


def publish(
    repo: Path,
    message: str,
    *,
    rebuild=default_rebuild,
    remote: str = "origin",
    branch: str = "main",
    max_attempts: int = 5,
) -> None:
    repo = repo.resolve()
    ensure_identity(repo)
    if not commit_paths(repo, message):
        return
    for attempt in range(1, max_attempts + 1):
        fetch_main(repo, remote, branch)
        head = _rev(repo, "HEAD")
        upstream = _rev(repo, f"{remote}/{branch}")
        if _is_ancestor(repo, upstream, head):
            print(f"push attempt {attempt}: {head[:8]} -> {branch}")
            if push_head(repo, remote, branch):
                print("pushed")
                return
            print("push rejected; fetching and retrying")
            continue
        print(f"{branch} moved to {upstream[:8]} while this job was running (local {head[:8]})")
        replay(repo, head, upstream, message, rebuild)
        print(f"push attempt {attempt} after replay")
        if push_head(repo, remote, branch):
            print("pushed")
            return
        print("push rejected after replay; retrying")
    raise SystemExit(f"failed to push to {remote}/{branch} after {max_attempts} attempts")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Commit pipeline data and push to main.")
    parser.add_argument("--message", required=True)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default="main")
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--no-rebuild", action="store_true")
    args = parser.parse_args(argv)
    if args.repo is not None:
        repo = args.repo
    else:
        top = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
        repo = Path(top.stdout.strip())
    rebuild = (lambda _repo: None) if args.no_rebuild else default_rebuild
    publish(
        repo,
        args.message,
        rebuild=rebuild,
        remote=args.remote,
        branch=args.branch,
        max_attempts=args.max_attempts,
    )


if __name__ == "__main__":
    main()
