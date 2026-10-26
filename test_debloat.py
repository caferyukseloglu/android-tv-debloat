import json
import pathlib
import tempfile
import unittest
from unittest import mock

import debloat


class Parsing(unittest.TestCase):
    def test_packages(self):
        self.assertEqual(debloat.parse_packages("package:a.b\npackage:c.d\njunk"), {"a.b", "c.d"})

    def test_rss_folds_subprocesses(self):
        ps = "  RSS NAME\n100 com.tcl.bi\n50 com.tcl.bi:service\n7 [kthreadd]\n"
        self.assertEqual(debloat.parse_rss(ps), {"com.tcl.bi": 150, "[kthreadd]": 7})

    def test_meminfo(self):
        mem = debloat.parse_kv("MemTotal:  2097152 kB\nMemAvailable: 410256 kB")
        self.assertEqual(debloat.kb(mem["MemAvailable"]), 410256)
        self.assertEqual(debloat.kb(mem.get("SwapFree")), 0)


class Selection(unittest.TestCase):
    entries = [{"id": "s", "tier": "safe"}, {"id": "o", "tier": "optional"}]

    def test_safe_excludes_optional(self):
        self.assertEqual([e["id"] for e in debloat.select(self.entries, "safe", None)], ["s"])

    def test_optional_includes_safe(self):
        self.assertEqual([e["id"] for e in debloat.select(self.entries, "optional", None)], ["s", "o"])

    def test_also_adds_to_tier(self):
        self.assertEqual([e["id"] for e in debloat.select(self.entries, "safe", None, ["o"])], ["s", "o"])

    def test_only_listed(self):
        self.assertEqual([e["id"] for e in debloat.select(self.entries, "safe", ["o", "x"])], ["o"])


class Restore(unittest.TestCase):
    """Fake TV: records every shell command instead of running adb."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.calls = []
        patches = [
            mock.patch.object(debloat, "BACKUPS", pathlib.Path(self.tmp.name)),
            mock.patch.object(debloat, "serial", lambda: "tv1"),
            mock.patch.object(debloat, "sh", lambda cmd: self.calls.append(cmd) or ""),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def backup(self, name, packages, settings):
        path = pathlib.Path(self.tmp.name) / name
        path.write_text(json.dumps({"path": str(path), "packages": packages, "settings": settings}))
        return path

    def test_undoes_every_apply_newest_first_and_skips_other_tvs(self):
        self.backup("tv1-20260101-100000.json", ["a"], {"global/anim": "1.0"})
        self.backup("tv1-20260101-110000.json", ["b"], {"global/anim": "0.5"})
        self.backup("tv2-20260101-120000.json", ["other.tv"], {})
        debloat.cmd_restore(mock.Mock(backup=None))
        self.assertEqual(self.calls, [
            "pm enable --user 0 b", "settings put global anim 0.5",
            "pm enable --user 0 a", "settings put global anim 1.0",
        ])

    def test_restored_backups_are_not_replayed(self):
        self.backup("tv1-20260101-100000.json", ["a"], {})
        debloat.cmd_restore(mock.Mock(backup=None))
        with self.assertRaises(SystemExit):
            debloat.cmd_restore(mock.Mock(backup=None))

    def test_null_setting_is_deleted_and_values_are_quoted(self):
        self.backup("tv1-20260101-100000.json", [], {"secure/a": "null", "secure/b": "pkg/.Foo$Dream"})
        debloat.cmd_restore(mock.Mock(backup=None))
        self.assertEqual(self.calls, ["settings delete secure a", "settings put secure b 'pkg/.Foo$Dream'"])


class Lists(unittest.TestCase):
    def test_lists_are_valid(self):
        for path in pathlib.Path(debloat.LISTS).glob("*.json"):
            ids = [e["id"] for e in json.loads(path.read_text())["packages"]]
            self.assertEqual(len(ids), len(set(ids)), f"duplicate in {path.name}")
            for e in json.loads(path.read_text())["packages"]:
                self.assertIn(e["tier"], debloat.TIERS, e["id"])


if __name__ == "__main__":
    unittest.main()
