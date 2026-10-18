"""git_publish dogrywa commit na przesuniety main i scala surowe JSON-y."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import git_publish  # noqa: E402


def run(repo, *args, check=True):
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stderr}")
    return result


def identity(repo: Path) -> None:
    run(repo, "config", "user.email", "test@example.com")
    run(repo, "config", "user.name", "Test")


def show(bare: Path, spec: str) -> bytes:
    result = subprocess.run(
        ["git", "--git-dir", str(bare), "show", spec],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return result.stdout


class GitPublishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="nevia-publish-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _repo_pair(self):
        bare = self.tmp / "origin.git"
        seed = self.tmp / "seed"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(bare)], check=True, stdout=subprocess.PIPE)
        subprocess.run(["git", "init", "-b", "main", str(seed)], check=True, stdout=subprocess.PIPE)
        identity(seed)
        day = seed / "data" / "raw" / "2026-10-17"
        day.mkdir(parents=True)
        (day / "market_history_top.json").write_text(json.dumps({"a": [{"time": 1, "v": "base"}]}))
        (day / "orderbook_nevia.json").write_text(json.dumps({"1": {"update_time": 1, "sellers": [], "buyers": []}}))
        (seed / "config.yaml").write_text("world: Base\n")
        (seed / "data" / "gold").mkdir()
        (seed / "data" / "gold" / "from_daily.csv").write_text("base\n")
        run(seed, "add", "-A")
        run(seed, "commit", "-m", "base")
        run(seed, "remote", "add", "origin", str(bare))
        run(seed, "push", "-u", "origin", "main")
        work = self.tmp / "work"
        subprocess.run(["git", "clone", str(bare), str(work)], check=True, stdout=subprocess.PIPE)
        identity(work)
        return bare, work

    def test_fast_forward_push_does_not_rebuild(self):
        bare, work = self._repo_pair()
        day = work / "data" / "raw" / "2026-10-17"
        hist = json.loads((day / "market_history_top.json").read_text())
        hist["z"] = [{"time": 3, "v": "ff"}]
        (day / "market_history_top.json").write_text(json.dumps(hist))

        def rebuild(_repo):
            raise AssertionError("rebuild should not run when main has not moved")

        git_publish.publish(work, "nevia daily snapshot", rebuild=rebuild)
        pushed = json.loads(show(bare, "main:data/raw/2026-10-17/market_history_top.json"))
        self.assertEqual(pushed["z"][0]["v"], "ff")
        subject = subprocess.run(
            ["git", "--git-dir", str(bare), "log", "-1", "--format=%s"],
            stdout=subprocess.PIPE, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(subject, "nevia daily snapshot")

    def test_replay_unions_raw_files_and_rebuilds_derived(self):
        bare, work = self._repo_pair()
        base = run(work, "rev-parse", "HEAD").stdout.strip()
        day = work / "data" / "raw" / "2026-10-17"
        (day / "market_history_top.json").write_text(json.dumps({
            "a": [{"time": 1, "v": "daily"}, {"time": 2, "v": "daily"}],
            "c": [{"time": 9, "v": "daily"}],
        }))
        (day / "orderbook_nevia.json").write_text(json.dumps({
            "1": {"update_time": 10, "sellers": [{"price": 1}], "buyers": []},
            "3": {"update_time": 1, "sellers": [], "buyers": [{"price": 2}]},
        }))
        (day / "hunts.csv").write_text("id,spawn\n1,demon\n")
        (work / "config.yaml").write_text("world: Daily\n")
        (work / "data" / "gold" / "from_daily.csv").write_text("daily\n")
        run(work, "add", "-A")
        run(work, "commit", "-m", "nevia daily snapshot")
        run(work, "push", "origin", "main")
        daily = run(work, "rev-parse", "HEAD").stdout.strip()
        run(work, "reset", "--hard", base)

        (day / "market_history_top.json").write_text(json.dumps({
            "a": [{"time": 1, "v": "weekly"}, {"time": 3, "v": "weekly"}],
            "b": [{"time": 4, "v": "weekly"}],
        }))
        (day / "orderbook_nevia.json").write_text(json.dumps({
            "1": {"update_time": 20, "sellers": [{"price": 9}], "buyers": []},
            "2": {"update_time": 5, "sellers": [{"price": 3}], "buyers": []},
        }))
        (work / "config.yaml").write_text("world: Weekly\n")
        (work / "data" / "gold" / "from_weekly.csv").write_text("weekly-only\n")
        (work / "data" / "gold" / "from_daily.csv").write_text("weekly\n")
        seen = {}

        def rebuild(repo: Path):
            seen["n"] = seen.get("n", 0) + 1
            hist = json.loads((repo / "data" / "raw" / "2026-10-17" / "market_history_top.json").read_text())
            seen["keys"] = sorted(hist)
            seen["a"] = [snap["v"] for snap in hist["a"]]
            gold = repo / "data" / "gold"
            gold.mkdir(parents=True, exist_ok=True)
            (gold / "from_daily.csv").write_text("rebuilt\n")
            (gold / "seen.txt").write_text("rebuilt\n")

        git_publish.publish(work, "nevia weekly history backfill", rebuild=rebuild)
        self.assertEqual(seen["n"], 1)
        self.assertEqual(seen["keys"], ["a", "b", "c"])
        self.assertEqual(seen["a"], ["weekly", "daily", "weekly"])

        hist = json.loads(show(bare, "main:data/raw/2026-10-17/market_history_top.json"))
        self.assertEqual(sorted(hist), ["a", "b", "c"])
        book = json.loads(show(bare, "main:data/raw/2026-10-17/orderbook_nevia.json"))
        self.assertEqual(sorted(book), ["1", "2", "3"])
        self.assertEqual(book["1"]["update_time"], 20)
        self.assertEqual(show(bare, "main:config.yaml"), b"world: Daily\n")
        self.assertEqual(show(bare, "main:data/raw/2026-10-17/hunts.csv"), b"id,spawn\n1,demon\n")
        self.assertEqual(show(bare, "main:data/gold/from_daily.csv"), b"rebuilt\n")
        self.assertEqual(show(bare, "main:data/gold/seen.txt"), b"rebuilt\n")
        missing = subprocess.run(
            ["git", "--git-dir", str(bare), "cat-file", "-e", "main:data/gold/from_weekly.csv"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertNotEqual(missing.returncode, 0)
        parent = subprocess.run(
            ["git", "--git-dir", str(bare), "rev-parse", "main^"],
            stdout=subprocess.PIPE, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(parent, daily)
        subject = subprocess.run(
            ["git", "--git-dir", str(bare), "log", "-1", "--format=%s"],
            stdout=subprocess.PIPE, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(subject, "nevia weekly history backfill")

    def test_shallow_clone_replays_when_main_moves(self):
        """Jak w Actions: checkout --depth 1, a main dostaje commit daily w trakcie."""
        bare, work = self._repo_pair()
        shallow = self.tmp / "shallow"
        subprocess.run(
            ["git", "clone", "--depth", "1", f"file://{bare}", str(shallow)],
            check=True, stdout=subprocess.PIPE,
        )
        self.assertEqual(run(shallow, "rev-parse", "--is-shallow-repository").stdout.strip(), "true")
        day = work / "data" / "raw" / "2026-10-17"
        (day / "market_history_top.json").write_text(json.dumps({
            "a": [{"time": 1, "v": "daily"}],
            "c": [{"time": 9, "v": "daily"}],
        }))
        (day / "hunts.csv").write_text("id,spawn\n1,demon\n")
        run(work, "add", "-A")
        run(work, "commit", "-m", "nevia daily snapshot")
        run(work, "push", "origin", "main")
        daily = run(work, "rev-parse", "HEAD").stdout.strip()

        sday = shallow / "data" / "raw" / "2026-10-17"
        (sday / "market_history_top.json").write_text(json.dumps({
            "a": [{"time": 1, "v": "weekly"}, {"time": 3, "v": "weekly"}],
            "b": [{"time": 4, "v": "weekly"}],
        }))

        def rebuild(repo: Path):
            gold = repo / "data" / "gold"
            gold.mkdir(parents=True, exist_ok=True)
            (gold / "marker.txt").write_text("ok\n")

        git_publish.publish(shallow, "nevia weekly history backfill", rebuild=rebuild)
        hist = json.loads(show(bare, "main:data/raw/2026-10-17/market_history_top.json"))
        self.assertEqual(sorted(hist), ["a", "b", "c"])
        self.assertEqual([snap["v"] for snap in hist["a"]], ["weekly", "weekly"])
        self.assertEqual(show(bare, "main:data/raw/2026-10-17/hunts.csv"), b"id,spawn\n1,demon\n")
        self.assertEqual(show(bare, "main:data/gold/marker.txt"), b"ok\n")
        parent = subprocess.run(
            ["git", "--git-dir", str(bare), "rev-parse", "main^"],
            stdout=subprocess.PIPE, text=True, check=True,
        ).stdout.strip()
        self.assertEqual(parent, daily)

    def test_nothing_to_commit(self):
        _bare, work = self._repo_pair()
        before = run(work, "rev-parse", "HEAD").stdout.strip()
        git_publish.publish(work, "nevia daily snapshot", rebuild=lambda _repo: None)
        self.assertEqual(run(work, "rev-parse", "HEAD").stdout.strip(), before)

    def test_push_rejected_detector(self):
        self.assertTrue(git_publish.push_rejected("! [rejected] main -> main (fetch first)"))
        self.assertTrue(git_publish.push_rejected("non-fast-forward"))
        self.assertFalse(git_publish.push_rejected("Authentication failed"))


if __name__ == "__main__":
    unittest.main()
