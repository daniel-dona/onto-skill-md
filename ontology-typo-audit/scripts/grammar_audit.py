#!/usr/bin/env python3
"""
typo_audit.py — Single-script ontology typo audit.

Extracts all string literals with language tags from an RDF repository and runs
LanguageTool on each one in its declared language. Supports 30+ languages.

Usage:
    # Full grammar audit
    python typo_audit.py <repo-path> -o report.md

    # Only check Spanish and English
    python typo_audit.py . --lang es en

    # Dump raw extracted literals (exploratory mode)
    python typo_audit.py . --dump

    # Dump including literals without lang tags
    python typo_audit.py . --dump --no-lang

Requires:
    pip install rdflib language-tool-python
"""
import argparse
import json
import os
import sys
from pathlib import Path

from rdflib import Graph, RDFS, OWL, SKOS, Literal, URIRef

from rdf_utils import find_rdf_files, compact_uri

# --------------------------------------------------------------------------- #
# 1. Literal extraction (absorbed from former rdf_extract.py)
# --------------------------------------------------------------------------- #

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


def dump_literals(repo_path: str, output: str | None, include_no_lang: bool):
    """Dump mode: extract literals and print summary."""
    literals = extract_literals(repo_path, include_no_lang=include_no_lang)
    literals.sort(key=lambda x: (x["file"], x["subject"], x["predicate"], x["lang"] or ""))

    if output:
        Path(output).write_text(json.dumps(literals, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[INFO] Dumped {len(literals)} literals to {output}", file=sys.stderr)
    else:
        print(json.dumps(literals, indent=2, ensure_ascii=False))

    # Summary to stderr
    langs = {}
    files = set()
    for lit in literals:
        langs[lit["lang"] or "(none)"] = langs.get(lit["lang"] or "(none)", 0) + 1
        files.add(lit["file"])
    print(f"\n--- Summary ---", file=sys.stderr)
    print(f"  Files parsed:   {len(files)}", file=sys.stderr)
    print(f"  Total literals: {len(literals)}", file=sys.stderr)
    print(f"  By language:", file=sys.stderr)
    for lang, count in sorted(langs.items()):
        print(f"    {lang}: {count}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# 2. LanguageTool integration
# --------------------------------------------------------------------------- #

LANG_MAP = {
    "en": "en-US", "en-us": "en-US", "en-gb": "en-GB",
    "es": "es", "es-es": "es", "es-419": "es",
    "fr": "fr", "fr-fr": "fr", "de": "de-DE", "de-de": "de-DE",
    "pt": "pt-PT", "pt-pt": "pt-PT", "pt-br": "pt-BR",
    "it": "it", "nl": "nl", "pl": "pl", "ru": "ru", "uk": "uk",
    "ja": "ja", "zh": "zh-CN", "zh-cn": "zh-CN", "ar": "ar",
    "ca": "ca", "cs": "cs", "da": "da", "el": "el", "fi": "fi",
    "gl": "gl", "he": "he", "hi": "hi", "hu": "hu", "ko": "ko",
    "no": "no", "nb": "no", "ro": "ro", "sk": "sk", "sl": "sl",
    "sv": "sv", "tl": "tl", "tr": "tr", "fa": "fa",
}

DEFAULT_DISABLED_RULES = {
    "en": {"COMMA_COMPOUND_SENTENCE", "EN_QUOTES", "DASH_RULE", "WHITESPACE_RULE",
           "SENTENCE_WHITESPACE", "UPPERCASE_SENTENCE_START", "FIRST_PERSON",
           "MORFOLOGIK_RULE", "CONTRACTION_IT_IS", "IT_IS",
           "ENGLISH_WORD_REPEAT_BEGINNING_RULE"},
    "es": {"WHITESPACE_RULE", "SENTENCE_WHITESPACE", "MORFOLOGIK_RULE",
           "UPPERCASE_SENTENCE_START", "ES_COMA_INCORRECTA"},
}

MIN_LENGTH = 3


def get_tool_for_lang(lang_code: str, _cache: dict = {}):
    """Get or create a LanguageTool instance for a given language."""
    lt_lang = LANG_MAP.get(lang_code.lower(), lang_code)
    if lt_lang not in _cache:
        try:
            import language_tool_python
            tool = language_tool_python.LanguageTool(lt_lang)
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
    if tool is None or len(value.strip()) < MIN_LENGTH:
        return []
    try:
        matches = tool.check(value)
    except Exception as e:
        print(f"[WARN] LanguageTool error on '{value[:50]}...' ({lang}): {e}", file=sys.stderr)
        return []
    issues = []
    for match in matches[:max_errors]:
        if hasattr(match, 'category') and match.category == 'STYLE' and getattr(match, 'rule_issue_type', '') == 'suggestion':
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


def detect_lang_mismatch(literal_entry: dict) -> list[str]:
    """Flag literals whose text looks like a different language than their tag."""
    value = literal_entry["value"]
    lang = literal_entry["lang"]
    if len(value.strip()) < 20:
        return []
    issues_declared = check_literal(value, lang)
    error_count = len(issues_declared)
    alternatives = {"en": "es", "es": "en", "fr": "en", "de": "en", "pt": "es"}
    alt = alternatives.get(lang)
    if alt and error_count >= 3:
        issues_alt = check_literal(value, alt)
        if len(issues_alt) == 0:
            return [f"Possible lang tag mismatch: declared @{lang} but text looks like @{alt} "
                    f"({error_count} errors in {lang} vs 0 in {alt})"]
    return []


# --------------------------------------------------------------------------- #
# 3. Audit orchestration
# --------------------------------------------------------------------------- #

def audit_repo(repo_path: str, max_errors: int = 5,
               filter_langs: list[str] | None = None,
               check_mismatch: bool = True) -> list[dict]:
    """Extract all literals and check grammar in each declared language."""
    print(f"[INFO] Extracting literals from {repo_path}...", file=sys.stderr)
    literals = extract_literals(repo_path, include_no_lang=False)
    if not literals:
        print("[WARN] No literals with lang tags found.", file=sys.stderr)
        return []

    if filter_langs:
        lang_set = set(l.lower() for l in filter_langs)
        literals = [l for l in literals if l["lang"] and l["lang"].lower() in lang_set]

    seen = {}
    for lit in literals:
        key = (lit["value"], lit["lang"])
        seen.setdefault(key, []).append(lit)

    print(f"[INFO] Checking {len(seen)} unique literal+lang combinations "
          f"({len(literals)} total occurrences)...", file=sys.stderr)

    report = []
    for idx, ((value, lang), occurrences) in enumerate(seen.items(), 1):
        if idx % 50 == 0:
            print(f"  ...checked {idx}/{len(seen)}", file=sys.stderr)
        issues = check_literal(value, lang, max_errors)
        if not issues and not check_mismatch:
            continue

        entry = {
            "value": value, "lang": lang, "issues": issues,
            "occurrences": [{"file": o["file"], "subject_short": o["subject_short"],
                             "predicate_short": o["predicate_short"]} for o in occurrences],
        }
        if check_mismatch and issues:
            warnings = detect_lang_mismatch(occurrences[0])
            if warnings:
                entry["lang_warnings"] = warnings
        if issues or entry.get("lang_warnings"):
            report.append(entry)

    print(f"[INFO] Done. Found {len(report)} literals with issues.", file=sys.stderr)
    return report


def format_report_markdown(report: list[dict]) -> str:
    """Render audit results as Markdown."""
    lines = ["# Ontology Grammar & Spelling Audit", "",
             "_Generated by `ontology-typo-audit` skill (rdflib + LanguageTool)_", ""]
    if not report:
        lines.append("**No grammar or spelling issues found.** ✅")
        return "\n".join(lines)

    lines.append(f"**{len(report)} literals with issues found.**")
    lines.append("")

    by_lang = {}
    for entry in report:
        by_lang.setdefault(entry["lang"] or "(none)", []).append(entry)

    for lang in sorted(by_lang.keys()):
        entries = by_lang[lang]
        lines.append(f"## Language: `@{lang}` ({len(entries)} issues)")
        lines.append("")
        for i, entry in enumerate(entries, 1):
            val = entry["value"]
            short = val[:100] + ("..." if len(val) > 100 else "")
            lines.append(f"### {i}. `{short}`")
            lines.append(f"- **Full text:** {val}")
            for w in entry.get("lang_warnings", []):
                lines.append(f"- ⚠️ **Lang tag warning:** {w}")
            for issue in entry["issues"]:
                suggestions = ", ".join(f"`{s}`" for s in issue["suggestions"]) if issue["suggestions"] else "(none)"
                lines.append(f"- **{issue['rule']}**: {issue['message']}")
                lines.append(f"  - Context: ...{issue['context']}...")
                lines.append(f"  - Suggestions: {suggestions}")
            lines.append("- **Occurs in:**")
            for occ in entry["occurrences"]:
                lines.append(f"  - `{occ['file']}` — {occ['subject_short']} → {occ['predicate_short']}")
            lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 4. Main CLI
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Audit RDF string literals for grammar/spelling errors using LanguageTool"
    )
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md)")
    parser.add_argument("--dump", action="store_true",
                        help="Only extract and dump all literals (no grammar check)")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag (only with --dump)")
    parser.add_argument("--max-errors", type=int, default=5,
                        help="Max grammar issues per literal (default: 5)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags (e.g. --lang es en)")
    parser.add_argument("--no-mismatch", action="store_true",
                        help="Skip lang tag mismatch detection")
    parser.add_argument("--format", choices=["json", "markdown"], default="markdown",
                        help="Output format (default: markdown)")
    args = parser.parse_args()

    # Dump mode: extract only, no LanguageTool
    if args.dump:
        dump_literals(args.repo_path, args.output, include_no_lang=args.no_lang)
        return

    # Audit mode
    report = audit_repo(args.repo_path, max_errors=args.max_errors,
                        filter_langs=args.lang, check_mismatch=not args.no_mismatch)

    fmt = args.format
    if args.output:
        ext = Path(args.output).suffix.lower()
        if ext == ".json":
            fmt = "json"

    if fmt == "json":
        output_text = json.dumps(report, indent=2, ensure_ascii=False)
    else:
        output_text = format_report_markdown(report)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
