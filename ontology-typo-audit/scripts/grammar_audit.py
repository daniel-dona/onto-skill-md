#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for spelling/grammar errors.

Three-tier spell checking with automatic fallback:
  1. Hunspell via ctypes (if libhunspell.so is on the system) — best quality
  2. pyspellchecker (pip-only, always works) — 8 languages
  3. LanguageTool (optional --grammar) — grammar + 30+ languages

Usage:
    python grammar_audit.py <repo-path> [-o report.md] [--lang es en]

Requires:
    pip install rdflib pyspellchecker
    # Optional: LanguageTool for grammar checking
    pip install language-tool-python
    # Optional: libhunspell on system (autodetected, no pip needed)
"""
import argparse
import ctypes
import ctypes.util
import glob
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
# Hunspell via ctypes (Tier 1 — best, autodetected)
# ---------------------------------------------------------------------------

# BCP47 → hunspell dict paths
HUNSPELL_DICT_MAP = {
    "en": "en_US", "en-us": "en_US", "en-gb": "en_GB",
    "es": "es_ES", "es-es": "es_ES", "es-419": "es_ANY", "es-ar": "es_AR",
    "fr": "fr_FR", "fr-fr": "fr_FR",
    "de": "de_DE", "de-de": "de_DE", "de-at": "de_AT", "de-ch": "de_CH",
    "pt": "pt_PT", "pt-pt": "pt_PT", "pt-br": "pt_BR",
    "it": "it_IT", "it-it": "it_IT",
    "nl": "nl_NL", "ru": "ru_RU",
    "pl": "pl_PL", "uk": "uk_UA",
    "ca": "ca_ES", "gl": "gl_ES",
    "ro": "ro_RO", "sv": "sv_SE",
    "cs": "cs_CZ", "da": "da_DK", "el": "el_GR",
    "fi": "fi_FI", "hu": "hu_HU", "ko": "ko_KR",
    "no": "nb_NO", "nb": "nb_NO",
    "sk": "sk_SK", "sl": "sl_SI", "tr": "tr_TR",
    "ar": "ar", "he": "he_IL",
}

# Standard hunspell dictionary search paths
_HUNSPELL_DICT_DIRS = [
    "/usr/share/hunspell",
    "/usr/share/myspell/dicts",
    "/usr/local/share/hunspell",
    "/app/share/hunspell",  # Flatpak
    os.path.expanduser("~/.local/share/hunspell"),
]

# Technical terms whitelist
TECHNICAL_WORDS = {
    "rdf", "rdfs", "owl", "skos", "xsd", "shacl", "sh", "sosa", "ssn",
    "qudt", "geosparql", "voaf", "void", "dcat", "foaf", "schema", "dc",
    "dcterms", "bibo", "frbr", "prov", "org", "time", "hydra", "ldp",
    "owl2", "owlrl", "n3", "turtle", "ttl", "nt", "nquads", "nq", "trig",
    "jsonld", "rdfa", "sparql",
    "hcho", "nox", "sox", "pm10", "pm25", "co2", "ch4", "n2o", "o3",
    "uri", "url", "urn", "iri", "bnode", "http", "https", "api", "json",
    "xml", "html", "css", "isbn", "issn", "doi", "orcid",
}


class HunspellCTypes:
    """Wrapper around libhunspell via ctypes — no pip package needed."""

    def __init__(self):
        self._lib = None
        self._handles: dict[str, int] = {}  # lang → hunhandle
        self._available = False
        self._dict_dirs: list[str] = []
        self._try_load()

    def _try_load(self):
        """Try to find and load libhunspell."""
        # Search common paths
        search_patterns = [
            "/usr/lib/x86_64-linux-gnu/libhunspell-1.7.so*",
            "/usr/lib/x86_64-linux-gnu/libhunspell-1.6.so*",
            "/usr/lib/aarch64-linux-gnu/libhunspell-*.so*",
            "/usr/lib/libhunspell-*.so*",
            "/usr/local/lib/libhunspell*.so*",
            "/opt/homebrew/lib/libhunspell*.dylib",   # macOS ARM
            "/usr/local/lib/libhunspell*.dylib",       # macOS Intel
        ]
        so_paths = []
        for pattern in search_patterns:
            so_paths.extend(glob.glob(pattern))

        # Also try ctypes.util.find_library
        lib_name = ctypes.util.find_library("hunspell")
        if lib_name:
            so_paths.insert(0, lib_name)

        for so_path in so_paths:
            try:
                lib = ctypes.CDLL(so_path)
                # Verify API exists
                if not hasattr(lib, 'Hunspell_create'):
                    continue
                lib.Hunspell_create.restype = ctypes.c_void_p
                lib.Hunspell_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
                lib.Hunspell_spell.restype = ctypes.c_int
                lib.Hunspell_spell.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
                lib.Hunspell_suggest.restype = ctypes.c_int
                lib.Hunspell_suggest.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),
                    ctypes.c_char_p,
                ]
                lib.Hunspell_free_list.restype = None
                lib.Hunspell_free_list.argtypes = [
                    ctypes.c_void_p,
                    ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),
                    ctypes.c_int,
                ]
                lib.Hunspell_destroy.restype = None
                lib.Hunspell_destroy.argtypes = [ctypes.c_void_p]
                self._lib = lib
                self._available = True
                break
            except OSError:
                continue

        # Find dictionary directories
        for d in _HUNSPELL_DICT_DIRS:
            if os.path.isdir(d) and glob.glob(os.path.join(d, "*.dic")):
                self._dict_dirs.append(d)

    @property
    def available(self) -> bool:
        return self._available and bool(self._dict_dirs)

    @property
    def supported_languages(self) -> set[str]:
        """Return BCP47 tags for which we have hunspell dictionaries."""
        langs = set()
        if not self._dict_dirs:
            return langs
        # Scan available .dic files
        available_dicts = set()
        for d in self._dict_dirs:
            for f in os.listdir(d):
                if f.endswith(".dic"):
                    available_dicts.add(f[:-4])  # e.g. "es_ES"
        # Map BCP47 → available dicts
        for bcp47, dict_name in HUNSPELL_DICT_MAP.items():
            if dict_name in available_dicts:
                langs.add(bcp47)
        return langs

    def _get_handle(self, lang: str) -> int | None:
        """Get or create a hunspell handle for a language."""
        if not self._available:
            return None

        lang_lower = lang.lower()
        if lang_lower in self._handles:
            return self._handles[lang_lower]

        dict_name = HUNSPELL_DICT_MAP.get(lang_lower)
        if not dict_name:
            return None

        # Find .aff and .dic files
        aff_path = None
        dic_path = None
        for d in self._dict_dirs:
            candidate_aff = os.path.join(d, dict_name + ".aff")
            candidate_dic = os.path.join(d, dict_name + ".dic")
            if os.path.isfile(candidate_aff) and os.path.isfile(candidate_dic):
                aff_path = candidate_aff
                dic_path = candidate_dic
                break

        if not aff_path:
            self._handles[lang_lower] = None
            return None

        try:
            handle = self._lib.Hunspell_create(
                aff_path.encode(), dic_path.encode()
            )
            if handle:
                self._handles[lang_lower] = handle
                return handle
        except Exception:
            pass

        self._handles[lang_lower] = None
        return None

    def check(self, words: list[str], lang: str) -> list[dict]:
        """Check a list of words. Returns issues for misspelled words."""
        handle = self._get_handle(lang)
        if not handle:
            return []

        # Filter words
        check_words = []
        for w in words:
            w_lower = w.lower()
            if len(w_lower) < 3 or w_lower.isdigit() or w_lower in TECHNICAL_WORDS:
                continue
            check_words.append(w)

        if not check_words:
            return []

        issues = []
        for word in check_words:
            result = self._lib.Hunspell_spell(handle, word.encode("utf-8"))
            if not result:
                # Get suggestions
                suggestions = []
                try:
                    slst = ctypes.POINTER(ctypes.c_char_p)()
                    n = self._lib.Hunspell_suggest(
                        handle, ctypes.byref(slst), word.encode("utf-8")
                    )
                    for i in range(min(n, 5)):
                        suggestions.append(
                            slst[i].decode("utf-8", errors="replace")
                        )
                    self._lib.Hunspell_free_list(handle, ctypes.byref(slst), n)
                except Exception:
                    pass

                issues.append({
                    "checker": "hunspell",
                    "message": f"Misspelled word: '{word}'",
                    "rule": "spelling",
                    "word": word,
                    "suggestions": suggestions,
                    "offset": 0,
                    "error_length": len(word),
                })

        return issues

    def __del__(self):
        if self._lib:
            for handle in self._handles.values():
                if handle:
                    try:
                        self._lib.Hunspell_destroy(handle)
                    except Exception:
                        pass


# Global instance (lazy init)
_hunspell: HunspellCTypes | None = None


def get_hunspell() -> HunspellCTypes:
    global _hunspell
    if _hunspell is None:
        _hunspell = HunspellCTypes()
        if _hunspell.available:
            langs = _hunspell.supported_languages
            print(f"[INFO] Hunspell (ctypes) available — dicts: "
                  f"{', '.join(sorted(langs))}", file=sys.stderr)
        else:
            print("[INFO] Hunspell not found on system, using pyspellchecker",
                  file=sys.stderr)
    return _hunspell


# ---------------------------------------------------------------------------
# pyspellchecker (Tier 2 — pip-only, always works)
# ---------------------------------------------------------------------------

SPELL_LANG_MAP = {
    "en": "en", "en-us": "en_US", "en-gb": "en_GB",
    "es": "es", "es-es": "es", "es-ar": "es_AR",
    "fr": "fr", "fr-fr": "fr",
    "de": "de", "de-de": "de_DE",
    "pt": "pt", "pt-pt": "pt_PT", "pt-br": "pt_BR",
    "it": "it", "it-it": "it_IT",
    "nl": "nl", "ru": "ru", "ar": "ar",
}

_spell_cache: dict = {}


def _get_spell_checker(lang: str):
    """Get or create a SpellChecker for a BCP47 language tag."""
    from spellchecker import SpellChecker

    spell_lang = SPELL_LANG_MAP.get(lang.lower())
    if spell_lang is None:
        return None

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


def check_with_spellchecker(value: str, lang: str) -> list[dict] | None:
    """Spell-check a literal with pyspellchecker. Returns None if lang unsupported."""
    sc = _get_spell_checker(lang)
    if sc is None:
        return None

    words = re.findall(r"[\w']+", value)
    if not words:
        return []

    check_words = []
    for w in words:
        w_lower = w.lower()
        if len(w_lower) < 3 or w_lower.isdigit() or w_lower in TECHNICAL_WORDS:
            continue
        check_words.append(w)

    if not check_words:
        return []

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
# LanguageTool (Tier 3 — grammar, 30+ languages)
# ---------------------------------------------------------------------------

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

DEFAULT_DISABLED_RULES = {}
_lt_cache: dict = {}
LT_MIN_LENGTH_DEFAULT = 10
DEFAULT_WORKERS = 4


def _get_lt_tool(lang_code: str):
    """Get or create a LanguageTool instance."""
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
    """Run LanguageTool on a literal value."""
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
    """Compare declared language against other languages. Fast — uses spell checkers."""
    if len(value.strip()) < 20:
        return []

    issues_declared = spell_check_value(value, lang)
    if issues_declared is None:
        return []  # Language unsupported by all spell checkers

    error_count = len(issues_declared)
    if error_count < 3:
        return []

    other_langs = all_langs - {lang}
    best_alt = None
    best_errors = error_count

    for alt in other_langs:
        alt_issues = spell_check_value(value, alt)
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
# Unified spell check: Hunspell → pyspellchecker
# ---------------------------------------------------------------------------

def spell_check_value(value: str, lang: str) -> list[dict] | None:
    """
    Spell-check a literal value. Uses hunspell (ctypes) if available,
    falls back to pyspellchecker. Returns None if language unsupported.
    """
    hunspell = get_hunspell()

    # Try hunspell first (more languages, better affix handling)
    if hunspell.available and lang.lower() in hunspell.supported_languages:
        words = re.findall(r"[\w']+", value)
        return hunspell.check(words, lang)

    # Fallback to pyspellchecker
    return check_with_spellchecker(value, lang)


# ---------------------------------------------------------------------------
# Main audit
# ---------------------------------------------------------------------------

def audit_repo(repo_path: str, filter_langs: list[str] | None = None,
               use_grammar: bool = False, check_mismatch: bool = False,
               custom_words: list[str] | None = None,
               custom_dict_file: str | None = None,
               lt_max_errors: int = 5, lt_min_length: int = LT_MIN_LENGTH_DEFAULT,
               workers: int = DEFAULT_WORKERS) -> list[dict]:
    """Main audit: extract literals and check spelling/grammar."""
    print(f"[INFO] Extracting literals from {repo_path}...", file=sys.stderr)
    literals = extract_literals(repo_path, include_no_lang=False)

    if not literals:
        print("[WARN] No literals with lang tags found.", file=sys.stderr)
        return []

    if filter_langs:
        lang_set = set(l.lower() for l in filter_langs)
        literals = [l for l in literals if l["lang"] and l["lang"].lower() in lang_set]

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

    # Pre-warm spell checkers
    for lang in all_langs:
        _get_spell_checker(lang)
    if custom:
        load_custom_words(custom)
        print(f"[INFO] Added {len(custom)} custom words to spell checkers",
              file=sys.stderr)

    # Determine which checker is active for each language
    hunspell = get_hunspell()
    hs_langs = hunspell.supported_languages if hunspell.available else set()
    sc_langs = set(SPELL_LANG_MAP.keys())
    supported = all_langs & (hs_langs | sc_langs)
    unsupported = all_langs - (hs_langs | sc_langs)

    unique_count = len(seen)
    print(f"[INFO] Checking {unique_count} unique literal+lang combinations "
          f"({len(literals)} total occurrences)...", file=sys.stderr)
    if unsupported:
        print(f"[INFO] Languages not supported by spell checkers (skipped): "
              f"{', '.join(sorted(unsupported))}", file=sys.stderr)
        print(f"[INFO]   Use --grammar to check these with LanguageTool.",
              file=sys.stderr)
    if check_mismatch:
        print(f"[INFO] Lang-mismatch detection: ON", file=sys.stderr)

    # Phase 1: spelling check (instant)
    report = []
    checked = 0

    for (value, lang), occurrences in seen.items():
        checked += 1
        if checked % 200 == 0 or checked == unique_count:
            print(f"  ...checked {checked}/{unique_count}", file=sys.stderr)

        issues = spell_check_value(value, lang)
        if issues is None:
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

        if check_mismatch and issues:
            warnings = detect_lang_mismatch(value, lang, all_langs)
            if warnings:
                entry["lang_warnings"] = warnings

        if issues or entry.get("lang_warnings"):
            report.append(entry)

    # Phase 2: grammar check with LanguageTool (optional, parallel)
    if use_grammar:
        # Check literals in unsupported languages
        for (value, lang), occurrences in seen.items():
            if lang.lower() in supported:
                continue
            lt_issues = check_with_languagetool(value, lang,
                                                max_errors=lt_max_errors,
                                                min_length=lt_min_length)
            if lt_issues:
                report.append({
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
                })

        # Grammar check on spelling-issue literals
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

    report = [e for e in report if e["issues"] or e.get("lang_warnings")]
    print(f"[INFO] Done. Found {len(report)} literals with issues.", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report_markdown(report: list[dict]) -> str:
    """Format the report as Markdown."""
    lines = ["# Ontology Typo Audit Report", ""]
    lines.append("_Generated by `ontology-typo-audit` skill_")
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

            by_checker = {}
            for issue in entry["issues"]:
                by_checker.setdefault(issue.get("checker", "?"), []).append(issue)

            for checker_key, checker_issues in by_checker.items():
                label = {
                    "hunspell": "📖 Hunspell",
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
                    "Uses hunspell (ctypes, autodetected) or pyspellchecker "
                    "(pip-only) for spelling, LanguageTool for grammar."
    )
    parser.add_argument("repo_path",
                        help="Path to the ontology repository")
    parser.add_argument("-o", "--output",
                        help="Output file (.json or .md, inferred from extension)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags (e.g. --lang es en)")
    parser.add_argument("--grammar", action="store_true",
                        help="Also run LanguageTool grammar check (slow)")
    parser.add_argument("--lt-max-errors", type=int, default=5,
                        help="Max LanguageTool issues per literal (default: 5)")
    parser.add_argument("--lt-min-length", type=int, default=10,
                        help="Skip LanguageTool on literals shorter than N chars "
                             "(default: 10)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel LanguageTool workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--dict", dest="custom_dict", default=None,
                        help="File with custom words (one per line, # comments)")
    parser.add_argument("--word", nargs="+", default=None,
                        help="Add custom words (e.g. --word pádel Straßenlaterne)")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: spelling only, no mismatch, "
                             "higher LT min-length")
    parser.add_argument("--dump", action="store_true",
                        help="Dump all string literals without checking")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag when dumping")
    parser.add_argument("--mismatch", action="store_true",
                        help="Enable lang-tag mismatch detection")
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
