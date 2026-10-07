#!/usr/bin/env python3
import json
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
    "docs/usage/standalone-gpio-walkthrough.md",
    "docs/observability/local.md",
    "docs/reference/measurement-statistics.md",
    "docs/reference/validation.md",
    "docs/development/architecture.md",
    "docs/development/development-and-testing.md",
    "docs/development/change-guide.md",
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

    def test_reader_documents_have_mirrors_and_language_switches(self):
        docs = ROOT / "docs"
        for source in sorted(docs.rglob("*.md")):
            relative = source.relative_to(docs)
            if relative.parts[0] in ("ru", "agents", "adr"):
                continue
            mirror = docs / "ru" / relative
            with self.subTest(document=str(relative)):
                self.assertTrue(mirror.is_file(), f"Missing mirror: {mirror}")
                source_links = re.findall(r"\[[^]]*\]\(([^)]+)\)", source.read_text())
                self.assertIn(mirror.resolve(), [
                    (source.parent / link).resolve()
                    for link in source_links if "://" not in link
                ])
                if mirror.is_file():
                    mirror_links = re.findall(r"\[[^]]*\]\(([^)]+)\)", mirror.read_text())
                    self.assertIn(source.resolve(), [
                        (mirror.parent / link).resolve()
                        for link in mirror_links if "://" not in link
                    ])

    def test_bilingual_executable_examples_match(self):
        docs = ROOT / "docs"

        def executable_blocks(text):
            blocks = re.findall(r"```(bash|python|sql|ini|json|yaml|promql)\n(.*?)```", text, re.S)
            return [(language, "\n".join(
                line for line in code.strip().splitlines()
                if not line.lstrip().startswith("#")
            )) for language, code in blocks]

        for source in sorted(docs.rglob("*.md")):
            relative = source.relative_to(docs)
            if relative.parts[0] in ("ru", "agents", "adr"):
                continue
            mirror = docs / "ru" / relative
            with self.subTest(document=str(relative)):
                self.assertTrue(mirror.is_file())
                if mirror.is_file():
                    self.assertEqual(executable_blocks(source.read_text()),
                                     executable_blocks(mirror.read_text()))

    def test_arduino_json_example_is_valid_and_accounts_for_tail(self):
        text = (ROOT / "docs/hardware/arduino.md").read_text()
        samples = re.findall(r"```json\n(.*?)```", text, re.S)
        self.assertTrue(samples)
        for sample in samples:
            data = json.loads(sample)
            self.assertEqual(data["requests_sent"],
                             data["responses_received"] + data["timeouts"])
            self.assertEqual(len(data["worst_latencies_us"]), data["worst_count"])
            self.assertGreaterEqual(data["avg_latency_us"], data["mean_latency_us"])
            self.assertAlmostEqual(data["avg_latency_us"],
                sum(data["worst_latencies_us"]) / data["worst_count"], places=2)


if __name__ == "__main__":
    unittest.main()
