#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for spelling/grammar errors.

Primary checker: Hunspell (C library, instant). Fallback: LanguageTool
(Java, slow). Hunspell catches misspellings and missing accents — the most
common ontology label issues. LanguageTool adds grammar checking but is
~100x slower.

Usage:
    python grammar_audit.py <repo-path> [-o report.md] [--lang es en]

Requires:
    hunspell (apt install hunspell + dictionaries) — recommended, fast
    rdflib (pip install rdflib)
    language-tool-python (pip install language-tool-python) — optional, slow
"""
import argparse
import json
import os
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
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


# ---------------------------------------------------------------------------
# BCP47 → hunspell dictionary mapping
# ---------------------------------------------------------------------------

# Two-letter BCP47 tag → hunspell dict name (as installed by e.g. hunspell-es)
HUNSPELL_DICT_MAP = {
    "en": "en_US",
    "en-us": "en_US",
    "en-gb": "en_GB",
    "es": "es_ES",
    "es-es": "es_ES",
    "es-419": "es_ANY",
    "fr": "fr_FR",
    "fr-fr": "fr_FR",
    "de": "de_DE",
    "de-de": "de_DE",
    "de-at": "de_AT",
    "de-ch": "de_CH",
    "pt": "pt_PT",
    "pt-pt": "pt_PT",
    "pt-br": "pt_BR",
    "it": "it_IT",
    "nl": "nl_NL",
    "pl": "pl_PL",
    "ru": "ru_RU",
    "uk": "uk_UA",
    "ca": "ca_ES",
    "gl": "gl_ES",
    "ro": "ro_RO",
    "sv": "sv_SE",
    "cs": "cs_CZ",
    "da": "da_DK",
    "el": "el_GR",
    "fi": "fi_FI",
    "hu": "hu_HU",
    "ko": "ko_KR",
    "no": "nb_NO",
    "nb": "nb_NO",
    "sk": "sk_SK",
    "sl": "sl_SI",
    "tr": "tr_TR",
}

# Map BCP47 lang tags to LanguageTool language codes (fallback)
LT_LANG_MAP = {
    "en": "en-US", "en-us": "en-US", "en-gb": "en-GB",
    "es": "es", "es-es": "es", "es-419": "es",
    "fr": "fr", "fr-fr": "fr",
    "de": "de-DE", "de-de": "de-DE",
    "pt": "pt-PT", "pt-pt": "pt-PT", "pt-br": "pt-BR",
    "it": "it", "nl": "nl", "pl": "pl", "ru": "ru", "uk": "uk",
    "ja": "ja", "zh": "zh-CN", "zh-cn": "zh-CN",
    "ar": "ar", "ca": "ca", "cs": "cs", "da": "da", "el": "el",
    "fi": "fi", "gl": "gl", "he": "he", "hi": "hi", "hu": "hu",
    "ko": "ko", "no": "no", "nb": "no", "ro": "ro", "sk": "sk",
    "sl": "sl", "sv": "sv", "tl": "tl", "tr": "tr", "fa": "fa",
}

# Technical terms common in ontologies — skip these during spell-check
TECHNICAL_WORDS = {
    # W3C / Semantic Web
    "rdf", "rdfs", "owl", "skos", "xsd", "shacl", "sh", "sosa", "ssn",
    "qudt", "geosparql", "voaf", "void", "dcat", "foaf", "schema", "dc",
    "dcterms", "bibo", "frbr", "prov", "org", "time", "hydra", "ldp",
    "owl2", "owlrl", "n3", "turtle", "ttl", "nt", "nquads", "nq", "trig",
    "jsonld", "rdfa", "sparql", "sparql1.1",
    # Chemistry / physics abbreviations
    "hcho", "nox", "sox", "pm10", "pm25", "co2", "ch4", "n2o", "o3",
    # Common acronyms
    "uri", "url", "urn", "iri", "bnode", "http", "https", "api", "json",
    "xml", "html", "css", "isbn", "issn", "doi", "orcid",
}

# LanguageTool disabled rules (per language 2-letter code)
DEFAULT_DISABLED_RULES = {}

MIN_LENGTH_DEFAULT = 3
MIN_LENGTH_FAST = 10
DEFAULT_WORKERS = 4


# ---------------------------------------------------------------------------
# Hunspell checker (fast, primary)
# ---------------------------------------------------------------------------

def _hunspell_available() -> bool:
    """Check if hunspell binary is installed."""
    try:
        result = subprocess.run(["hunspell", "--version"], capture_output=True,
                               text=True, timeout=5)
        return result.returncode == 0 or "Hunspell" in (result.stdout + result.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _hunspell_dict_for_lang(lang: str) -> str | None:
    """Return the hunspell dictionary name for a BCP47 lang tag, or None."""
    return HUNSPELL_DICT_MAP.get(lang.lower())


def check_with_hunspell(value: str, lang: str) -> list[dict]:
    """
    Spell-check a literal with hunspell. Returns list of misspelled words
    with suggestions.

    Uses `hunspell -d <dict> -l` which prints misspelled words to stdout,
    then `hunspell -d <dict>` in pipe mode for suggestions.
    """
    dict_name = _hunspell_dict_for_lang(lang)
    if not dict_name:
        return []

    # Tokenize: split on non-word chars, keep unicode letters
    words = re.findall(r"[\w']+", value)
    if not words:
        return []

    # Filter out: short words, pure numbers, technical terms
    check_words = []
    for w in words:
        w_lower = w.lower()
        if len(w_lower) < 3:
            continue
        if w_lower.isdigit():
            continue
        if w_lower in TECHNICAL_WORDS:
            continue
        check_words.append(w)

    if not check_words:
        return []

    # Run hunspell in pipe mode: send words, get misspelled + suggestions
    try:
        input_text = "\n".join(check_words) + "\n"
        result = subprocess.run(
            ["hunspell", "-d", dict_name, "-a"],
            input=input_text, capture_output=True, text=True, timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    # Parse hunspell pipe output
    # Lines starting with '&' = misspelled with suggestions
    # Lines starting with '#' = misspelled, no suggestions
    issues = []
    for line in result.stdout.splitlines():
        if line.startswith("&"):
            # Format: & word count offset: suggestion1, suggestion2, ...
            # e.g. & Lampara 5 0: Lámpara, Lampar, ...
            m = re.match(r'^& (\S+) \d+ \d+: (.+)', line)
            if m:
                word = m.group(1)
                suggestions = [s.strip() for s in m.group(2).split(",")]
                issues.append({
                    "checker": "hunspell",
                    "message": f"Misspelled word: '{word}'",
                    "rule": "spelling",
                    "word": word,
                    "suggestions": suggestions[:5],
                    "offset": 0,
                    "error_length": len(word),
                })
        elif line.startswith("#"):
            # Format: # word offset
            m = re.match(r'^# (\S+) \d+', line)
            if m:
                word = m.group(1)
                issues.append({
                    "checker": "hunspell",
                    "message": f"Unknown word: '{word}'",
                    "rule": "spelling",
                    "word": word,
                    "suggestions": [],
                    "offset": 0,
                    "error_length": len(word),
                })

    return issues


# ---------------------------------------------------------------------------
# LanguageTool checker (slow, fallback for grammar)
# ---------------------------------------------------------------------------

_lt_cache: dict = {}


def _get_lt_tool(lang_code: str):
    """Get or create a LanguageTool instance for a given language."""
    lt_lang = LT_LANG_MAP.get(lang_code.lower(), lang_code)

    if lt_lang not in _lt_cache:
        try:
            import language_tool_python
            tool = language_tool_python.LanguageTool(lt_lang)
            two_letter = lang_code[:2].lower() if len(lang_code) >= 2 else lang_code.lower()
            disabled = DEFAULT_DISABLED_RULES.get(two_letter, set())
            if disabled:
                tool.disabled_rules.update(disabled)
            _lt_cache[lt_lang] = tool
        except Exception as e:
            print(f"[WARN] Cannot create LanguageTool for '{lt_lang}': {e}",
                  file=sys.stderr)
            _lt_cache[lt_lang] = None

    return _lt_cache.get(lt_lang)


def check_with_languagetool(value: str, lang: str, max_errors: int = 5,
                             min_length: int = 10) -> list[dict]:
    """Run LanguageTool on a literal value in its language."""
    tool = _get_lt_tool(lang)
    if tool is None:
        return []

    if len(value.strip()) < min_length:
        return []

    try:
        matches = tool.check(value)
    except Exception as e:
        print(f"[WARN] LanguageTool error on '{value[:50]}...' ({lang}): {e}",
              file=sys.stderr)
        return []

    issues = []
    for match in matches[:max_errors]:
        if hasattr(match, 'category') and match.category == 'STYLE' \
                and match.rule_issue_type == 'suggestion':
            continue
        issues.append({
            "checker": "languagetool",
            "message": match.message,
            "context": match.context,
            "rule": match.rule_id,
            "suggestions": match.replacements[:3] if match.replacements else [],
            "offset": match.offset,
            "error_length": match.error_length,
        })

    return issues


# ---------------------------------------------------------------------------
# Lang-mismatch detection (optional, expensive)
# ---------------------------------------------------------------------------

def detect_lang_mismatch(value: str, lang: str, all_langs: set[str],
                         use_hunspell: bool = True) -> list[str]:
    """
    Compare the declared language against all other languages in the repo.
    If another language produces significantly fewer errors, flag a mismatch.

    Uses hunspell (fast) if available, otherwise LanguageTool (slow).
    """
    if len(value.strip()) < 20:
        return []

    if use_hunspell and _hunspell_available():
        issues_declared = check_with_hunspell(value, lang)
    else:
        issues_declared = check_with_languagetool(value, lang)

    error_count = len(issues_declared)
    if error_count < 3:
        return []

    other_langs = all_langs - {lang}
    best_alt = None
    best_errors = error_count

    for alt in other_langs:
        if use_hunspell and _hunspell_available():
            issues_alt = check_with_hunspell(value, alt)
        else:
            issues_alt = check_with_languagetool(value, alt)
        if len(issues_alt) < best_errors:
            best_errors = len(issues_alt)
            best_alt = alt

    if best_alt and best_errors <= 1 and error_count - best_errors >= 3:
        return [
            f"Possible lang tag mismatch: declared @{lang} but text looks like "
            f"@{best_alt} ({error_count} errors in {lang} vs {best_errors} in {best_alt})"
        ]

    return []


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit_repo(repo_path: str, filter_langs: list[str] | None = None,
               use_grammar: bool = False, check_mismatch: bool = False,
               min_length_lt: int = 10, lt_max_errors: int = 5,
               workers: int = DEFAULT_WORKERS) -> list[dict]:
    """
    Main audit: extract literals and check spelling/grammar.

    By default uses hunspell (fast, spelling-only).
    With --grammar also runs LanguageTool (grammar, slow).
    """
    print(f"[INFO] Extracting literals from {repo_path}...", file=sys.stderr)
    literals = extract_literals(repo_path, include_no_lang=False)

    if not literals:
        print("[WARN] No literals with lang tags found.", file=sys.stderr)
        return []

    # Filter by requested languages
    if filter_langs:
        lang_set = set(l.lower() for l in filter_langs)
        literals = [l for l in literals if l["lang"] and l["lang"].lower() in lang_set]

    # Collect all languages present in the repo
    all_langs = set()
    for lit in literals:
        if lit["lang"]:
            all_langs.add(lit["lang"].lower())

    # Deduplicate by (value, lang)
    seen: dict[tuple, list] = {}
    for lit in literals:
        key = (lit["value"], lit["lang"])
        seen.setdefault(key, []).append(lit)

    unique_count = len(seen)
    hunspell_ok = _hunspell_available()

    checker_name = "hunspell" if hunspell_ok else "LanguageTool"
    print(f"[INFO] Checker: {checker_name} (spelling)"
          f"{' + LanguageTool (grammar)' if use_grammar else ''}",
          file=sys.stderr)
    print(f"[INFO] Checking {unique_count} unique literal+lang combinations "
          f"({len(literals)} total occurrences)...", file=sys.stderr)
    if check_mismatch:
        print(f"[INFO] Lang-mismatch detection: ON", file=sys.stderr)

    report = []
    checked = 0

    # Phase 1: spelling check with hunspell (instant, no parallelism needed)
    for (value, lang), occurrences in seen.items():
        checked += 1
        if checked % 200 == 0 or checked == unique_count:
            print(f"  ...checked {checked}/{unique_count}", file=sys.stderr)

        issues = []

        # Hunspell (spelling) — always run if available
        if hunspell_ok:
            hs_issues = check_with_hunspell(value, lang)
            issues.extend(hs_issues)

        # Build entry
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
            warnings = detect_lang_mismatch(value, lang, all_langs,
                                            use_hunspell=hunspell_ok)
            if warnings:
                entry["lang_warnings"] = warnings

        if issues or entry.get("lang_warnings"):
            report.append(entry)

    # Phase 2: grammar check with LanguageTool (optional, parallel)
    if use_grammar and report:
        print(f"[INFO] Running LanguageTool grammar check on "
              f"{len(report)} literals with spelling issues...",
              file=sys.stderr)

        def _lt_check_one(value, lang):
            lt_issues = check_with_languagetool(value, lang,
                                                max_errors=lt_max_errors,
                                                min_length=min_length_lt)
            return (value, lang, lt_issues)

        done = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {}
            for entry in report:
                f = executor.submit(_lt_check_one, entry["value"], entry["lang"])
                futures[f] = (entry["value"], entry["lang"])

            for f in as_completed(futures):
                key = futures[f]
                try:
                    _val, _lang, lt_issues = f.result()
                    # Find the matching report entry and append grammar issues
                    for entry in report:
                        if entry["value"] == key[0] and entry["lang"] == key[1]:
                            entry["issues"].extend(lt_issues)
                            break
                except Exception as e:
                    print(f"[WARN] LT check failed for {key}: {e}", file=sys.stderr)
                done += 1
                if done % 50 == 0 or done == len(report):
                    print(f"  ...LT checked {done}/{len(report)}", file=sys.stderr)

    # Remove entries that ended up with no issues after filtering
    report = [e for e in report if e["issues"] or e.get("lang_warnings")]

    print(f"[INFO] Done. Found {len(report)} literals with issues.", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report_markdown(report: list[dict], hunspell_used: bool) -> str:
    """Format the report as Markdown."""
    checker = "hunspell" if hunspell_used else "LanguageTool"
    lines = ["# Ontology Typo Audit Report", ""]
    lines.append(f"_Generated by `ontology-typo-audit` skill (rdflib + {checker})_")
    lines.append("")

    if not report:
        lines.append("**No spelling or grammar issues found.** ✅")
        return "\n".join(lines)

    lines.append(f"**{len(report)} literals with issues found.**")
    lines.append("")

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

            # Group by checker
            by_checker = {}
            for issue in entry["issues"]:
                by_checker.setdefault(issue.get("checker", "?"), []).append(issue)

            for checker_key, checker_issues in by_checker.items():
                label = {"hunspell": "📖 Spelling", "languagetool": "✍️ Grammar"}.get(checker_key, checker_key)
                lines.append(f"- **{label}:**")
                for issue in checker_issues:
                    suggestions = ", ".join(f"`{s}`" for s in issue["suggestions"]) \
                                  if issue["suggestions"] else "(none)"
                    word_info = f" `{issue['word']}`" if issue.get("word") else ""
                    lines.append(f"  - **{issue['rule']}**{word_info}: {issue['message']}")
                    if suggestions != "(none)":
                        lines.append(f"    - Suggestions: {suggestions}")

            lines.append(f"- **Occurs in:**")
            for occ in entry["occurrences"]:
                lines.append(f"  - `{occ['file']}` — {occ['subject_short']} → {occ['predicate_short']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit RDF literals for spelling/grammar errors. "
                    "Uses hunspell (fast) by default, LanguageTool with --grammar."
    )
    parser.add_argument("repo_path", help="Path to the ontology repository")
    parser.add_argument("-o", "--output", help="Output file (.json or .md, inferred from extension)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags (e.g. --lang es en)")
    parser.add_argument("--grammar", action="store_true",
                        help="Also run LanguageTool grammar check (slow — "
                             "spelling is checked first with hunspell, then grammar "
                             "only on literals with issues)")
    parser.add_argument("--lt-max-errors", type=int, default=5,
                        help="Max LanguageTool issues per literal (default: 5)")
    parser.add_argument("--lt-min-length", type=int, default=10,
                        help="Skip LanguageTool on literals shorter than N chars "
                             "(default: 10 — short labels produce mostly grammar noise)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel LanguageTool workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: spelling only, skip short literals for LT, "
                             "no mismatch detection")
    parser.add_argument("--dump", action="store_true",
                        help="Dump all string literals without checking")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag when dumping")
    parser.add_argument("--mismatch", action="store_true",
                        help="Enable lang-tag mismatch detection (fast with hunspell, "
                             "slow with LanguageTool)")
    parser.add_argument("--format", choices=["json", "markdown", "report"],
                        default="markdown",
                        help="Output format: markdown (default), json, or report")
    args = parser.parse_args()

    if args.dump:
        literals = extract_literals(args.repo_path, include_no_lang=args.no_lang)
        for lit in literals:
            lang_str = f"@{lit['lang']}" if lit['lang'] else "(no lang)"
            print(f"{lang_str}\t{lit['subject_short']}\t{lit['predicate_short']}\t{lit['value']}")
        return

    report = audit_repo(
        args.repo_path,
        filter_langs=args.lang,
        use_grammar=args.grammar and not args.fast,
        check_mismatch=args.mismatch and not args.fast,
        min_length_lt=args.lt_min_length if not args.fast else 20,
        lt_max_errors=2 if args.fast else args.lt_max_errors,
        workers=args.workers,
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
        hunspell_used = _hunspell_available()
        output_text = format_report_markdown(report, hunspell_used)

    if args.output:
        Path(args.output).write_text(output_text, encoding="utf-8")
        print(f"[INFO] Report written to {args.output}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == "__main__":
    main()
