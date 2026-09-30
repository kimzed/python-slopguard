"""Findings and the capped report shown to Claude."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    code: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.code} {self.message}"


def format_report(findings: list[Finding], config: dict[str, Any]) -> str:
    cap = config["max_findings"]
    lines = [f"slopguard: {len(findings)} problem(s) must be fixed before you finish:"]
    lines += [finding.render() for finding in findings[:cap]]
    if len(findings) > cap:
        lines.append(f"...and {len(findings) - cap} more")
    lines.append(config["feedback_footer"])
    return "\n".join(lines)
