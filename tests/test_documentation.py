#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "docs/README.md",
    "docs/getting-started.md",
    "docs/modes/standalone-gpio.md",
    "docs/modes/supervised-raw-ethernet.md",
    "docs/modes/linux-benchmarks.md",
    "docs/usage/publish-cyclictest.md",
    "docs/methodology/cyclictest-comparisons.md",
    "docs/reference/dependencies.md",
    "docs/reference/runtime-paths.md",
    "docs/reference/sqlite-schema.md",
    "docs/results/README.md",
)
RETIRED = (
    "PROMETHEUS_INTEGRATION.md",
    "docs/linux-benchmarks-prototype.md",
    "docs/prometheus.md",
    "docs/receiver.md",
    "docs/standalone-gpio.md",
)


class DocumentationTest(unittest.TestCase):
    def test_canonical_structure_exists(self):
        for relative in REQUIRED:
            with self.subTest(path=relative):
                self.assertTrue((ROOT / relative).is_file())
        for relative in RETIRED:
            with self.subTest(path=relative):
                self.assertFalse((ROOT / relative).exists())

    def test_local_markdown_links_resolve(self):
        sources = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
        broken = []
        escaped = []
        for source in sources:
            text = source.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", text):
                path = target.split("#", 1)[0]
                if not path or "://" in path or path.startswith(("#", "mailto:")):
                    continue
                resolved = (source.parent / path).resolve()
                if not resolved.exists():
                    broken.append(
                        f"{source.relative_to(ROOT)} -> {target}"
                    )
                if source != ROOT / "README.md" and not resolved.is_relative_to(
                    ROOT / "docs"
                ):
                    escaped.append(
                        f"{source.relative_to(ROOT)} -> {target}"
                    )
        self.assertEqual(broken, [])
        self.assertEqual(escaped, [])


if __name__ == "__main__":
    unittest.main()
