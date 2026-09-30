"""Maximum lines per Python file (ruff has no such rule)."""

from slopguard import vcs
from slopguard.checks.base import Context, edit_targets
from slopguard.report import Finding


class FileLength:
    name = "file_length"

    def run(self, ctx: Context) -> list[Finding]:
        limit = ctx.config["edit"]["max_file_lines"]
        allow_existing = ctx.config["edit"]["existing_violations"] == "allow"
        findings = []
        for path in edit_targets(ctx):
            text = (ctx.project_dir / path).read_text(encoding="utf-8", errors="replace")
            count = len(text.splitlines())
            if count <= limit:
                continue
            if allow_existing:
                before = len(vcs.committed_content(ctx.project_dir, path).splitlines())
                if count <= before:
                    continue
            message = f"file has {count} lines (> {limit}). Split the module by responsibility."
            findings.append(Finding(path, 1, "file-length", message))
        return findings
