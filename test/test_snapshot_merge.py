"""Scalanie snapshotow daily/weekly bez gita."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import snapshot_merge as sm  # noqa: E402


def dumps(obj) -> bytes:
    return json.dumps(obj).encode()


class SnapshotMergeTests(unittest.TestCase):
    def test_history_unions_keys_and_timestamps(self):
        main = {
            "a": [{"time": 1, "v": "main"}, {"time": 2, "v": "main"}],
            "c": [{"time": 9, "v": "main"}],
        }
        ours = {
            "a": [{"time": 1, "v": "ours"}, {"time": 3, "v": "ours"}],
            "b": [{"time": 4, "v": "ours"}],
            "c": [],
        }
        merged = sm.merge_parsed("data/raw/2026-10-17/market_history_top.json", ours, main)
        self.assertEqual([snap["v"] for snap in merged["a"]], ["ours", "main", "ours"])
        self.assertEqual(merged["b"][0]["v"], "ours")
        self.assertEqual(merged["c"][0]["v"], "main")  # pusty ours nie kasuje serii

    def test_orderbook_prefers_newer_update_and_keeps_unique_items(self):
        main = {
            "1": {"update_time": 10, "sellers": [{"price": 1}], "buyers": []},
            "3": {"update_time": 1, "sellers": [], "buyers": [{"price": 2}]},
        }
        ours = {
            "1": {"update_time": 20, "sellers": [{"price": 9}], "buyers": []},
            "2": {"update_time": 5, "sellers": [{"price": 3}], "buyers": []},
        }
        merged = sm.merge_parsed("data/raw/2026-10-17/orderbook_nevia.json", ours, main)
        self.assertEqual(merged["1"]["update_time"], 20)
        self.assertIn("2", merged)
        self.assertIn("3", merged)

    def test_market_values_prefer_later_time_and_keep_both_ids(self):
        main = [{"id": 1, "time": 10, "buy_offer": 1}, {"id": 2, "time": 10, "buy_offer": 2}]
        ours = [{"id": 1, "time": 12, "buy_offer": 5}, {"id": 3, "time": 1, "buy_offer": 3}]
        merged = sm.merge_parsed("data/raw/2026-10-17/market_values_nevia.json", ours, main)
        by_id = {row["id"]: row for row in merged}
        self.assertEqual(by_id[1]["buy_offer"], 5)
        self.assertEqual(by_id[2]["buy_offer"], 2)
        self.assertEqual(by_id[3]["buy_offer"], 3)

    def test_metadata_keeps_richer_row(self):
        main = [{"id": 7, "name": "rope belt"}]
        ours = [{"id": 7, "name": "rope belt", "wiki_name": "Rope Belt"}]
        merged = sm.merge_parsed("data/raw/2026-10-17/market_metadata_all.json", ours, main)
        self.assertEqual(merged[0]["wiki_name"], "Rope Belt")

    def test_world_prefers_later_last_update(self):
        main = [{"name": "Nevia", "last_update": "2026-10-17T05:00:00"}]
        ours = [{"name": "Nevia", "last_update": "2026-10-17T08:00:00"},
                {"name": "Antica", "last_update": "2026-10-17T01:00:00"}]
        merged = sm.merge_parsed("data/raw/2026-10-17/market_world_data.json", ours, main)
        by_name = {row["name"]: row for row in merged}
        self.assertEqual(by_name["Nevia"]["last_update"], "2026-10-17T08:00:00")
        self.assertIn("Antica", by_name)

    def test_events_and_creatures_and_failed_dates(self):
        events = sm.merge_parsed(
            "data/raw/2026-10-17/events.json",
            [{"date": "2026-10-18", "name": "Rapid"}],
            [{"date": "2026-10-17", "name": "Double"}, {"date": "2026-10-18", "name": "Rapid"}],
        )
        self.assertEqual([row["date"] for row in events], ["2026-10-17", "2026-10-18"])
        creatures = sm.merge_parsed(
            "data/raw/2026-10-17/creatures.json",
            {"Dragon": {"experience_points": 700, "loot_list": ["gold coin"]}},
            {"Dragon": {"experience_points": 210, "hitpoints": 1000}, "Rat": {"experience_points": 5}},
        )
        self.assertEqual(creatures["Dragon"]["experience_points"], 700)
        self.assertEqual(creatures["Dragon"]["hitpoints"], 1000)
        self.assertIn("Rat", creatures)
        failed = sm.merge_parsed(
            "data/raw/creatures_failed.json",
            {"Orc": "2026-10-17"},
            {"Orc": "2026-10-10", "Troll": "2026-09-01"},
        )
        self.assertEqual(failed["Orc"], "2026-10-17")
        self.assertEqual(failed["Troll"], "2026-09-01")

    def test_config_yaml_keeps_main_and_csv_unions_rows(self):
        self.assertEqual(
            sm.merge_file("config.yaml", b"world: Base\n", b"world: Weekly\n", b"world: Daily\n"),
            b"world: Daily\n",
        )
        ours = b"id,spawn\n2,tiger\n1,quara\n"
        main = b"id,spawn\n1,demon\n3,werehyena\n"
        merged = sm.merge_file("data/raw/2026-10-17/hunts.csv", None, ours, main).decode()
        self.assertIn("3,werehyena", merged)
        self.assertIn("2,tiger", merged)
        self.assertIn("1,quara", merged)
        self.assertNotIn("1,demon", merged)

    def test_deletion_rules_and_tibiadata_snapshot(self):
        self.assertEqual(sm.merge_file("data/raw/x.json", b"{}", None, b'{"a": 1}'), b'{"a": 1}')
        self.assertEqual(sm.merge_file("data/raw/x.json", b"{}", b'{"b": 2}', None), b'{"b": 2}')
        self.assertIsNone(sm.merge_file("data/raw/x.json", b"{}", None, None))
        self.assertEqual(
            sm.merge_parsed("data/raw/2026-10-17/tibiadata_world.json", {"online": 9}, {"online": 1}),
            {"online": 9},
        )

    def test_identical_bytes_and_derived_prefix(self):
        blob = dumps({"a": 1})
        self.assertEqual(sm.merge_file("data/raw/2026-10-17/market_history_top.json", None, blob, blob), blob)
        self.assertTrue(sm.is_derived("docs/data/history/1.csv"))
        self.assertTrue(sm.is_derived("data/gold/dashboard.xlsx"))
        self.assertFalse(sm.is_derived("data/raw/2026-10-17/hunts.csv"))


if __name__ == "__main__":
    unittest.main()
