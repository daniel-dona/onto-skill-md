"""
report_format.py — Shared standardized report format for all ontology audit skills.

Provides a common Issue dataclass and serialization so that every skill can
emit findings in a consistent structure consumable by ontology-full-audit.

Format per issue:
    {
      "file": "relative/path.ttl",
      "line": 15,
      "element": "ex:ClassName",
      "predicate": "rdfs:label",
      "message": "Human-readable description of the problem",
      "severity": "error | warning | info",
      "check": "RULE_ID or check name",
      "suggestion": "What to do about it"
    }

Top-level wrapper:
    {
      "skill": "typo-audit",
      "timestamp": "2026-05-13T...",
      "summary": {"errors": 5, "warnings": 3, "info": 1},
      "issues": [...]
    }
"""
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Issue:
    file: str
    element: str
    message: str
    severity: str          # "error" | "warning" | "info"
    check: str = ""
    suggestion: str = ""
    line: int = 0
    predicate: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove empty optional fields for cleaner output
        return {k: v for k, v in d.items() if v not in (0, "", None) or k in ("file", "message", "severity")}


@dataclass
class AuditReport:
    skill: str
    issues: list = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def add(self, file: str, element: str, message: str, severity: str,
            check: str = "", suggestion: str = "", line: int = 0, predicate: str = "") -> None:
        self.issues.append(Issue(
            file=file, element=element, message=message, severity=severity,
            check=check, suggestion=suggestion, line=line, predicate=predicate,
        ))

    @property
    def summary(self) -> dict:
        errors = sum(1 for i in self.issues if i.severity == "error")
        warnings = sum(1 for i in self.issues if i.severity == "warning")
        info = sum(1 for i in self.issues if i.severity == "info")
        return {"errors": errors, "warnings": warnings, "info": info}

    def to_dict(self) -> dict:
        return {
            "skill": self.skill,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_markdown_table(self) -> str:
        """Render as a unified Markdown table."""
        if not self.issues:
            return f"## {self.skill}\n\n✅ No issues found.\n"

        lines = [
            f"## {self.skill}",
            "",
            f"| # | File | Element | Severity | Issue | Suggestion |",
            f"|---|------|---------|----------|-------|------------|",
        ]
        for i, iss in enumerate(self.issues, 1):
            sev_icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(iss.severity, "")
            suggestion = iss.suggestion[:80] if iss.suggestion else "—"
            lines.append(
                f"| {i} | `{iss.file}` | `{iss.element}` | {sev_icon} {iss.severity} | "
                f"{iss.message[:100]} | {suggestion} |"
            )
        lines.append("")
        return "\n".join(lines)
