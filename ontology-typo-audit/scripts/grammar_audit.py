#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for spelling/grammar errors.

Primary checker: pyspellchecker (pure Python, pip-installable, instant).
Fallback for grammar: LanguageTool (Java, slow, optional).

Usage:
    python grammar_audit.py <repo-path> [-o report.md] [--lang es en]

Requires:
    pip install rdflib pyspellchecker
    # Optional (for grammar checking):
    pip install language-tool-python
"""
import argparse
import json
import os
import re
import sys
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
# BCP47 → pyspellchecker language mapping
# ---------------------------------------------------------------------------

# pyspellchecker supports: en, es, de, fr, pt, it, nl, ru, ar
# (plus es_AR, en_GB, en_US, de_DE, fr_FR, pt_BR, pt_PT, it_IT)
SPELL_LANG_MAP = {
    "en": "en",
    "en-us": "en_US",
    "en-gb": "en_GB",
    "es": "es",
    "es-es": "es",
    "es-ar": "es_AR",
    "es-419": "es_AR",
    "fr": "fr",
    "fr-fr": "fr",
    "de": "de",
    "de-de": "de_DE",
    "pt": "pt",
    "pt-pt": "pt_PT",
    "pt-br": "pt_BR",
    "it": "it",
    "it-it": "it_IT",
    "nl": "nl",
    "ru": "ru",
    "ar": "ar",
}

# Map BCP47 → LanguageTool codes
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

# Languages supported by pyspellchecker
SPELL_SUPPORTED = set(SPELL_LANG_MAP.values())

# Technical terms common in ontologies — skip during spell-check
TECHNICAL_WORDS = {
    # W3C / Semantic Web
    "rdf", "rdfs", "owl", "skos", "xsd", "shacl", "sh", "sosa", "ssn",
    "qudt", "geosparql", "voaf", "void", "dcat", "foaf", "schema", "dc",
    "dcterms", "bibo", "frbr", "prov", "org", "time", "hydra", "ldp",
    "owl2", "owlrl", "n3", "turtle", "ttl", "nt", "nquads", "nq", "trig",
    "jsonld", "rdfa", "sparql",
    # Chemistry / physics
    "hcho", "nox", "sox", "pm10", "pm25", "co2", "ch4", "n2o", "o3",
    # Common acronyms
    "uri", "url", "urn", "iri", "bnode", "http", "https", "api", "json",
    "xml", "html", "css", "isbn", "issn", "doi", "orcid",
}

# LanguageTool disabled rules
DEFAULT_DISABLED_RULES = {}

LT_MIN_LENGTH_DEFAULT = 10
DEFAULT_WORKERS = 4


# ---------------------------------------------------------------------------
# pyspellchecker (fast, primary)
# ---------------------------------------------------------------------------

_spell_cache: dict = {}


def _get_spell_checker(lang: str):
    """Get or create a SpellChecker for a BCP47 language tag."""
    from spellchecker import SpellChecker

    lang_lower = lang.lower()
    spell_lang = SPELL_LANG_MAP.get(lang_lower)

    if spell_lang is None:
        return None  # Language not supported by pyspellchecker

    if spell_lang not in _spell_cache:
        try:
            sc = SpellChecker(language=spell_lang, distance=2)
            _spell_cache[spell_lang] = sc
        except Exception as e:
            print(f"[WARN] Cannot create SpellChecker for '{spell_lang}': {e}",
                  file=sys.stderr)
            _spell_cache[spell_lang] = None

    return _spell_cache.get(spell_lang)


def load_custom_words(words: list[str]):
    """Add custom words to all cached spell checkers."""
    for sc in _spell_cache.values():
        if sc is not None:
            sc.word_frequency.load_words(words)


def check_with_spellchecker(value: str, lang: str) -> list[dict]:
    """Spell-check a literal with pyspellchecker. Returns misspelled words."""
    sc = _get_spell_checker(lang)
    if sc is None:
        return []

    # Tokenize: split on non-word chars, keep unicode letters
    words = re.findall(r"[\w']+", value)
    if not words:
        return []

    # Filter: skip short, numeric, technical terms
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

    # pyspellchecker.unknown() returns the set of words not in dictionary
    unknown = sc.unknown(check_words)
    if not unknown:
        return []

    issues = []
    for word in sorted(unknown, key=lambda w: check_words.index(w)):
        correction = sc.correction(word)
        candidates = sc.candidates(word) or set()
        suggestions = sorted(candidates, key=lambda c: (
            0 if c == correction else 1, c))[:5]

        issues.append({
            "checker": "pyspellchecker",
            "message": f"Unknown word: '{word}'",
            "rule": "spelling",
            "word": word,
            "suggestions": suggestions,
            "offset": 0,
            "error_length": len(word),
        })

    return issues


# ---------------------------------------------------------------------------
# LanguageTool (slow, for grammar)
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
                             min_length: int = LT_MIN_LENGTH_DEFAULT) -> list[dict]:
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
# Lang-mismatch detection
# ---------------------------------------------------------------------------

def detect_lang_mismatch(value: str, lang: str, all_langs: set[str]) -> list[str]:
    """
    Compare the declared language against all other languages in the repo.
    If another language produces significantly fewer errors, flag a mismatch.

    Uses pyspellchecker (fast) when available.
    """
    if len(value.strip()) < 20:
        return []

    issues_declared = check_with_spellchecker(value, lang)
    if issues_declared is None:
        # pyspellchecker doesn't support this language — skip
        return []

    error_count = len(issues_declared)
    if error_count < 3:
        return []

    other_langs = all_langs - {lang}
    best_alt = None
    best_errors = error_count

    for alt in other_langs:
        alt_issues = check_with_spellchecker(value, alt)
        if alt_issues is None:
            continue
        if len(alt_issues) < best_errors:
            best_errors = len(alt_issues)
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
               custom_words: list[str] | None = None,
               custom_dict_file: str | None = None,
               lt_max_errors: int = 5, lt_min_length: int = LT_MIN_LENGTH_DEFAULT,
               workers: int = DEFAULT_WORKERS) -> list[dict]:
    """
    Main audit: extract literals and check spelling/grammar.

    By default uses pyspellchecker (fast, spelling-only).
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

    # Load custom words
    custom = list(custom_words) if custom_words else []
    if custom_dict_file:
        try:
            with open(custom_dict_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip().split("#")[0].strip()
                    if word:
                        custom.append(word)
            print(f"[INFO] Loaded {len(custom)} custom words from {custom_dict_file}",
                  file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Cannot read custom dict {custom_dict_file}: {e}",
                  file=sys.stderr)

    # Pre-warm spell checkers for all languages and load custom words
    for lang in all_langs:
        _get_spell_checker(lang)
    if custom:
        load_custom_words(custom)
        print(f"[INFO] Added {len(custom)} custom words to spell checkers",
              file=sys.stderr)

    unique_count = len(seen)
    supported_langs = {l for l in all_langs if _get_spell_checker(l) is not None}
    unsupported_langs = all_langs - supported_langs

    print(f"[INFO] Checking {unique_count} unique literal+lang combinations "
          f"({len(literals)} total occurrences)...", file=sys.stderr)
    if unsupported_langs:
        print(f"[INFO] Languages not supported by pyspellchecker (skipped): "
              f"{', '.join(sorted(unsupported_langs))}", file=sys.stderr)
        print(f"[INFO]   Use --grammar to check these with LanguageTool.",
              file=sys.stderr)
    if check_mismatch:
        print(f"[INFO] Lang-mismatch detection: ON", file=sys.stderr)

    # Phase 1: spelling check (instant, no parallelism needed)
    report = []
    checked = 0

    for (value, lang), occurrences in seen.items():
        checked += 1
        if checked % 200 == 0 or checked == unique_count:
            print(f"  ...checked {checked}/{unique_count}", file=sys.stderr)

        issues = check_with_spellchecker(value, lang)
        if issues is None:
            # Language not supported — skip (LT will catch it if --grammar)
            issues = []

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
            warnings = detect_lang_mismatch(value, lang, all_langs)
            if warnings:
                entry["lang_warnings"] = warnings

        if issues or entry.get("lang_warnings"):
            report.append(entry)

    # Phase 2: grammar check with LanguageTool (optional, parallel)
    if use_grammar:
        # Also check literals in unsupported languages
        unsupported_entries = []
        for (value, lang), occurrences in seen.items():
            if lang.lower() in supported_langs:
                continue
            # Check with LT for unsupported languages
            lt_issues = check_with_languagetool(value, lang,
                                                max_errors=lt_max_errors,
                                                min_length=lt_min_length)
            if lt_issues:
                entry = {
                    "value": value,
                    "lang": lang,
                    "issues": lt_issues,
                    "occurrences": [
                        {
                            "file": o["file"],
                            "subject_short": o["subject_short"],
                            "predicate_short": o["predicate_short"],
                        }
                        for o in occurrences
                    ],
                }
                report.append(entry)

        # Also run LT on literals that have spelling issues for grammar
        if report:
            print(f"[INFO] Running LanguageTool grammar check on "
                  f"{len(report)} literals...", file=sys.stderr)

            done = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {}
                for entry in report:
                    f = executor.submit(check_with_languagetool,
                                        entry["value"], entry["lang"],
                                        lt_max_errors, lt_min_length)
                    futures[f] = (entry["value"], entry["lang"])

                for f in as_completed(futures):
                    key = futures[f]
                    try:
                        lt_issues = f.result()
                        for entry in report:
                            if entry["value"] == key[0] and entry["lang"] == key[1]:
                                entry["issues"].extend(lt_issues)
                                break
                    except Exception as e:
                        print(f"[WARN] LT check failed for {key}: {e}",
                              file=sys.stderr)
                    done += 1
                    if done % 50 == 0 or done == len(report):
                        print(f"  ...LT checked {done}/{len(report)}",
                              file=sys.stderr)

    # Remove entries that ended up with no issues
    report = [e for e in report if e["issues"] or e.get("lang_warnings")]

    print(f"[INFO] Done. Found {len(report)} literals with issues.", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report_markdown(report: list[dict]) -> str:
    """Format the report as Markdown."""
    lines = ["# Ontology Typo Audit Report", ""]
    lines.append("_Generated by `ontology-typo-audit` skill "
                 "(rdflib + pyspellchecker)_")
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

            # Group issues by checker
            by_checker = {}
            for issue in entry["issues"]:
                by_checker.setdefault(issue.get("checker", "?"), []).append(issue)

            for checker_key, checker_issues in by_checker.items():
                label = {
                    "pyspellchecker": "📖 Spelling",
                    "languagetool": "✍️ Grammar",
                }.get(checker_key, checker_key)
                lines.append(f"- **{label}:**")
                for issue in checker_issues:
                    suggestions = ", ".join(
                        f"`{s}`" for s in issue["suggestions"]
                    ) if issue["suggestions"] else "(none)"
                    word_info = f" `{issue['word']}`" if issue.get("word") else ""
                    lines.append(f"  - **{issue['rule']}**{word_info}: "
                                 f"{issue['message']}")
                    if suggestions != "(none)":
                        lines.append(f"    - Suggestions: {suggestions}")

            lines.append(f"- **Occurs in:**")
            for occ in entry["occurrences"]:
                lines.append(f"  - `{occ['file']}` — "
                             f"{occ['subject_short']} → "
                             f"{occ['predicate_short']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit RDF literals for spelling/grammar errors. "
                    "Uses pyspellchecker (fast, pip-only) by default, "
                    "LanguageTool with --grammar."
    )
    parser.add_argument("repo_path",
                        help="Path to the ontology repository")
    parser.add_argument("-o", "--output",
                        help="Output file (.json or .md, inferred from extension)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags (e.g. --lang es en)")
    parser.add_argument("--grammar", action="store_true",
                        help="Also run LanguageTool grammar check (slow — "
                             "spelling checked first with pyspellchecker, "
                             "then grammar only on problem literals)")
    parser.add_argument("--lt-max-errors", type=int, default=5,
                        help="Max LanguageTool issues per literal (default: 5)")
    parser.add_argument("--lt-min-length", type=int, default=10,
                        help="Skip LanguageTool on literals shorter than N chars "
                             "(default: 10 — short labels produce mostly noise)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel LanguageTool workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--dict", dest="custom_dict", default=None,
                        help="File with custom words (one per line, # comments) "
                             "to add to the spell checker dictionary")
    parser.add_argument("--word", nargs="+", default=None,
                        help="Add custom words to the dictionary "
                             "(e.g. --word pádel Straßenlaterne)")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: spelling only, no mismatch, "
                             "higher LT min-length, fewer suggestions")
    parser.add_argument("--dump", action="store_true",
                        help="Dump all string literals without checking")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag when dumping")
    parser.add_argument("--mismatch", action="store_true",
                        help="Enable lang-tag mismatch detection "
                             "(fast with pyspellchecker)")
    parser.add_argument("--format", choices=["json", "markdown", "report"],
                        default="markdown",
                        help="Output format: markdown (default), json, or report")
    args = parser.parse_args()

    if args.dump:
        literals = extract_literals(args.repo_path, include_no_lang=args.no_lang)
        for lit in literals:
            lang_str = f"@{lit['lang']}" if lit['lang'] else "(no lang)"
            print(f"{lang_str}\t{lit['subject_short']}\t"
                  f"{lit['predicate_short']}\t{lit['value']}")
        return

    report = audit_repo(
        args.repo_path,
        filter_langs=args.lang,
        use_grammar=args.grammar and not args.fast,
        check_mismatch=args.mismatch and not args.fast,
        custom_words=args.word,
        custom_dict_file=args.custom_dict,
        lt_max_errors=2 if args.fast else args.lt_max_errors,
        lt_min_length=20 if args.fast else args.lt_min_length,
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
                        suggestion=issue["suggestions"][0]
                                   if issue.get("suggestions") else "",
                        predicate=occ.get("predicate_short", ""),
                    )
            for w in entry.get("lang_warnings", []):
                for occ in entry.get("occurrences", []):
                    ar.add(file=occ["file"], element=occ["subject_short"],
                           message=w, severity="warning",
                           check="lang-mismatch")
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
