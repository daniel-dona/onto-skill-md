#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for grammar/spelling errors.

Extracts all string literals with language tags from an RDF repository and runs
LanguageTool on each one in its declared language. Supports 30+ languages.

Usage:
    python grammar_audit.py <repo-path> [-o report.md] [--lang es en]

Requires:
    pip install rdflib language-tool-python
"""
import argparse
import json
import os
import sys
from pathlib import Path

from rdflib import Graph, Literal

from rdf_utils import find_rdf_files, compact_uri


# ---------------------------------------------------------------------------
# Literal extraction
# ---------------------------------------------------------------------------

def extract_literals(repo_path: str, include_no_lang: bool = False) -> list[dict]:
    """Parse all RDF files and return string literals with optional lang tags."""
    results = []
    rdf_files = find_rdf_files(repo_path)
    if not rdf_files:
        print(f"[WARN] No RDF files found in {repo_path}", file=sys.stderr)
        return results
    for fpath in rdf_files:
        g = Graph()
        try:
            g.parse(fpath, format=None)
        except Exception as e:
            print(f"[WARN] Could not parse {fpath}: {e}", file=sys.stderr)
            continue
        rel_path = os.path.relpath(fpath, repo_path)
        for s, p, o in g.triples((None, None, None)):
            if not isinstance(o, Literal):
                continue
            if o.datatype and str(o.datatype) not in (
                "http://www.w3.org/2001/XMLSchema#string",
                "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString",
            ) and o.datatype is not None:
                continue
            if not o.value or not str(o.value).strip():
                continue
            lang = str(o.language) if o.language else None
            if not include_no_lang and lang is None:
                continue
            results.append({
                "file": rel_path,
                "subject": str(s),
                "subject_short": compact_uri(s, g),
                "predicate": str(p),
                "predicate_short": compact_uri(p, g),
                "value": str(o.value),
                "lang": lang,
            })
    return results

# Map BCP47 lang tags to LanguageTool language codes
LANG_MAP = {
    "en": "en-US",
    "en-us": "en-US",
    "en-gb": "en-GB",
    "es": "es",
    "es-es": "es",
    "es-419": "es",
    "fr": "fr",
    "fr-fr": "fr",
    "de": "de-DE",
    "de-de": "de-DE",
    "pt": "pt-PT",
    "pt-pt": "pt-PT",
    "pt-br": "pt-BR",
    "it": "it",
    "nl": "nl",
    "pl": "pl",
    "ru": "ru",
    "uk": "uk",
    "ja": "ja",
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "ar": "ar",
    "ca": "ca",
    "cs": "cs",
    "da": "da",
    "el": "el",
    "fi": "fi",
    "gl": "gl",
    "he": "he",
    "hi": "hi",
    "hu": "hu",
    "ko": "ko",
    "no": "no",
    "nb": "no",
    "ro": "ro",
    "sk": "sk",
    "sl": "sl",
    "sv": "sv",
    "tl": "tl",
    "tr": "tr",
    "fa": "fa",
}

# Rules that are often noisy on ontology labels/comments.
# Empty by default — add language-specific rules here if needed.
# Example for Spanish:
#   "es": {"WHITESPACE_RULE", "UPPERCASE_SENTENCE_START"}
DEFAULT_DISABLED_RULES = {}

# Minimum literal length to check (skip single words, abbreviations)
MIN_LENGTH = 3


def get_tool_for_lang(lang_code: str, _cache: dict | None = None):
    """Get or create a LanguageTool instance for a given language."""
    if _cache is None:
        _cache = {}
    lt_lang = LANG_MAP.get(lang_code.lower(), lang_code)

    if lt_lang not in _cache:
        try:
            import language_tool_python
            tool = language_tool_python.LanguageTool(lt_lang)
            # Disable noisy rules
            two_letter = lang_code[:2].lower() if len(lang_code) >= 2 else lang_code.lower()
            disabled = DEFAULT_DISABLED_RULES.get(two_letter, set())
            if disabled:
                tool.disabled_rules.update(disabled)
            _cache[lt_lang] = tool
        except Exception as e:
            print(f"[WARN] Cannot create LanguageTool for '{lt_lang}': {e}", file=sys.stderr)
            _cache[lt_lang] = None

    return _cache.get(lt_lang)


def check_literal(value: str, lang: str, max_errors: int = 5) -> list[dict]:
    """Run LanguageTool on a literal value in its language."""
    tool = get_tool_for_lang(lang)
    if tool is None:
        return []

    if len(value.strip()) < MIN_LENGTH:
        return []

    try:
        matches = tool.check(value)
    except Exception as e:
        print(f"[WARN] LanguageTool error on '{value[:50]}...' ({lang}): {e}", file=sys.stderr)
        return []

    issues = []
    for match in matches[:max_errors]:
        # Skip style suggestions that are very low confidence
        if hasattr(match, 'category') and match.category == 'STYLE' and match.rule_issue_type == 'suggestion':
            continue

        issues.append({
            "message": match.message,
            "context": match.context,
            "rule": match.rule_id,
            "suggestions": match.replacements[:3] if match.replacements else [],
            "offset": match.offset,
            "error_length": match.error_length,
        })

    return issues


def detect_lang_mismatch(literal_entry: dict, all_langs: set[str]) -> list[str]:
    """
    Compare the declared language against all other languages in the repo.
    If another language produces significantly fewer errors, flag a possible mismatch.
    """
    value = literal_entry["value"]
    lang = literal_entry["lang"]

    if len(value.strip()) < 20:
        return []

    issues_declared = check_literal(value, lang)
    error_count = len(issues_declared)

    if error_count < 3:
        return []

    # Compare against every other language present in the repo
    other_langs = all_langs - {lang}
    best_alt = None
    best_errors = error_count

    for alt in other_langs:
        issues_alt = check_literal(value, alt)
        if len(issues_alt) < best_errors:
            best_errors = len(issues_alt)
            best_alt = alt

    if best_alt and best_errors <= 1 and error_count - best_errors >= 3:
        return [
            f"Possible lang tag mismatch: declared @{lang} but text looks like @{best_alt} "
            f"({error_count} errors in {lang} vs {best_errors} in {best_alt})"
        ]

    return []


def audit_repo(repo_path: str, max_errors: int = 5,
               filter_langs: list[str] | None = None,
               check_mismatch: bool = True) -> list[dict]:
    """Main audit: extract literals and check grammar."""
    print(f"[INFO] Extracting literals from {repo_path}...", file=sys.stderr)
    literals = extract_literals(repo_path, include_no_lang=False)

    if not literals:
        print("[WARN] No literals with lang tags found.", file=sys.stderr)
        return []

    # Filter by requested languages
    if filter_langs:
        lang_set = set(l.lower() for l in filter_langs)
        literals = [l for l in literals if l["lang"] and l["lang"].lower() in lang_set]

    # Collect all languages present in the repo (for mismatch detection)
    all_langs = set()
    for lit in literals:
        if lit["lang"]:
            all_langs.add(lit["lang"].lower())

    # Deduplicate by (value, lang) — same text in same lang is same check
    seen = {}
    for lit in literals:
        key = (lit["value"], lit["lang"])
        if key not in seen:
            seen[key] = []
        seen[key].append(lit)

    print(f"[INFO] Checking {len(seen)} unique literal+lang combinations "
          f"({len(literals)} total occurrences)...", file=sys.stderr)

    report = []
    checked = 0

    for (value, lang), occurrences in seen.items():
        checked += 1
        if checked % 50 == 0:
            print(f"  ...checked {checked}/{len(seen)}", file=sys.stderr)

        issues = check_literal(value, lang, max_errors)
        if not issues and not check_mismatch:
            continue

        entry = {
            "value": value,
            "lang": lang,
            "issues": issues,
            "occurrences": [
                {
                    "file": o["file"],
                    "subject_short": o["subject_short"],
                    "predicate_short": o["predicate_short"],
                }
                for o in occurrences
            ],
        }

        # Lang tag mismatch detection
        if check_mismatch and issues:
            warnings = detect_lang_mismatch(occurrences[0], all_langs)
            if warnings:
                entry["lang_warnings"] = warnings

        if issues or entry.get("lang_warnings"):
            report.append(entry)

    print(f"[INFO] Done. Found {len(report)} literals with issues.", file=sys.stderr)
    return report


def format_report_markdown(report: list[dict]) -> str:
    """Format the report as Markdown."""
    lines = ["# Ontology Grammar Audit Report", ""]
    lines.append(f"Generated by `ontology-typo-audit` skill (rdflib + LanguageTool)")
    lines.append("")

    if not report:
        lines.append("**No grammar or spelling issues found.** ✅")
        return "\n".join(lines)

    lines.append(f"**{len(report)} literals with issues found.**")
    lines.append("")

    # Group by language
    by_lang = {}
    for entry in report:
        lang = entry["lang"] or "(none)"
        by_lang.setdefault(lang, []).append(entry)

    for lang in sorted(by_lang.keys()):
        entries = by_lang[lang]
        lines.append(f"## Language: `@{lang}` ({len(entries)} issues)")
        lines.append("")

        for i, entry in enumerate(entries, 1):
            value_short = entry["value"][:100] + ("..." if len(entry["value"]) > 100 else "")
            lines.append(f"### {i}. `{value_short}`")
            lines.append(f"- **Full text:** {entry['value']}")

            if entry.get("lang_warnings"):
                for w in entry["lang_warnings"]:
                    lines.append(f"- ⚠️ **Lang tag warning:** {w}")

            for issue in entry["issues"]:
                suggestions = ", ".join(f"`{s}`" for s in issue["suggestions"]) if issue["suggestions"] else "(none)"
                lines.append(f"- **{issue['rule']}**: {issue['message']}")
                lines.append(f"  - Context: ...{issue['context']}...")
                lines.append(f"  - Suggestions: {suggestions}")

            lines.append(f"- **Occurs in:**")
            for occ in entry["occurrences"]:
                lines.append(f"  - `{occ['file']}` — {occ['subject_short']} → {occ['predicate_short']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit RDF literals for grammar/spelling errors using LanguageTool"
    )
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md, inferred from extension)")
    parser.add_argument("--max-errors", type=int, default=5,
                        help="Max grammar issues per literal (default: 5)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags (e.g. --lang es en)")
    parser.add_argument("--dump", action="store_true",
                        help="Dump all string literals without checking grammar")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag when dumping")
    parser.add_argument("--no-mismatch", action="store_true",
                        help="Skip lang tag mismatch detection")
    parser.add_argument("--format", choices=["json", "markdown", "report"], default="markdown",
                        help="Output format: markdown (default), json, or report (standardized table)")
    args = parser.parse_args()

    if args.dump:
        literals = extract_literals(args.repo_path, include_no_lang=args.no_lang)
        for lit in literals:
            lang_str = f"@{lit['lang']}" if lit['lang'] else "(no lang)"
            print(f"{lang_str}\t{lit['subject_short']}\t{lit['predicate_short']}\t{lit['value']}")
        return

    report = audit_repo(
        args.repo_path,
        max_errors=args.max_errors,
        filter_langs=args.lang,
        check_mismatch=not args.no_mismatch,
    )

    # Determine format from output extension if given
    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"
        elif ext in (".md", ".markdown"):
            fmt = "markdown"

    if fmt == "json":
        output_text = json.dumps(report, indent=2, ensure_ascii=False)
    elif fmt == "report":
        from report_format import AuditReport
        ar = AuditReport(skill="typo-audit")
        for entry in report:
            for issue in entry.get("issues", []):
                for occ in entry.get("occurrences", []):
                    ar.add(
                        file=occ["file"], element=occ["subject_short"],
                        message=issue["message"], severity="warning",
                        check=issue.get("rule", ""),
                        suggestion=issue["suggestions"][0] if issue.get("suggestions") else "",
                        predicate=occ.get("predicate_short", ""),
                    )
            for w in entry.get("lang_warnings", []):
                for occ in entry.get("occurrences", []):
                    ar.add(file=occ["file"], element=occ["subject_short"],
                           message=w, severity="warning", check="lang-mismatch")
        output_text = ar.to_json()
    else:
        output_text = format_report_markdown(report)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
