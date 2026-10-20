"""Tests for the docs link-check (sprint TEMPLATE-INVERT, M2).

Closes downstream fork feedback **#11**: only 20 of 55 design-doc references
resolved in the published template. Two structural causes — promoting a doc to
`implemented/` invalidates every link to it, and the sanitizer deletes docs
that surviving files still link to.

Why it matters more than a tidiness bug: those pointers exist so a fork reads
the rationale instead of re-deriving it. A dead link sends the reader back to
re-deriving, which is the failure the doc was written to prevent.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
LINK_CHECK = REPO_ROOT / "scripts" / "link-check.py"


def _run(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(LINK_CHECK), "--root", str(root)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "target.md").write_text("# Target\n")
    return tmp_path


class TestResolution:
    def test_resolving_link_passes(self, docs):
        (docs / "docs" / "index.md").write_text("See [target](design/target.md)\n")

        result = _run(docs)

        assert result.returncode == 0, result.stderr

    def test_dangling_link_fails_and_names_the_file_and_line(self, docs):
        (docs / "docs" / "index.md").write_text("intro\nSee [gone](design/gone.md)\n")

        result = _run(docs)

        assert result.returncode == 1
        assert "docs/index.md:2" in result.stderr
        assert "design/gone.md" in result.stderr

    def test_the_implemented_move_is_caught(self, docs):
        """The #1 cause in downstream feedback #11: a doc gets promoted to implemented/
        and every link to its old path silently rots."""
        (docs / "docs" / "design" / "implemented").mkdir()
        (docs / "docs" / "design" / "implemented" / "feature.md").write_text("# F\n")
        (docs / "docs" / "index.md").write_text("[feature](design/feature.md)\n")

        assert _run(docs).returncode == 1


class TestWhatIsNotChecked:
    """Deliberate non-goals — a checker that cries wolf gets switched off."""

    @pytest.mark.parametrize(
        "target",
        ["https://example.com", "http://example.com", "mailto:a@b.c", "#anchor"],
    )
    def test_external_and_anchor_targets_are_skipped(self, docs, target):
        (docs / "docs" / "index.md").write_text(f"[x]({target})\n")

        assert _run(docs).returncode == 0

    def test_fenced_and_inline_examples_are_not_live_links(self, docs):
        (docs / "docs" / "index.md").write_text(
            "```markdown\n[example](missing.md)\n```\n"
            "`[inline example](also-missing.md)`\n"
            "[citation](aip://doc/id/block/line)\n"
        )
        assert _run(docs).returncode == 0

    def test_missing_image_in_prose_is_rejected(self, docs):
        (docs / "docs" / "index.md").write_text("![diagram](missing.svg)\n")
        assert _run(docs).returncode == 1

    def test_anchor_on_a_real_file_resolves(self, docs):
        """We verify the FILE resolves, not the heading — heading checks would
        break on every legitimate rename of a section."""
        (docs / "docs" / "index.md").write_text("[t](design/target.md#some-heading)\n")

        assert _run(docs).returncode == 0


class TestShippedWiring:
    def test_script_exists_and_is_executable(self):
        assert LINK_CHECK.is_file()
        assert LINK_CHECK.stat().st_mode & 0o111

    def test_make_target_is_wired(self):
        assert "link-check:" in (REPO_ROOT / "Makefile").read_text()

    def test_ci_reports_dangling_links(self):
        ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "link-check.py" in ci


class TestRepositoryLinks:
    def test_repository_has_no_dangling_document_links(self):
        result = _run(REPO_ROOT)
        assert result.returncode == 0, result.stderr
