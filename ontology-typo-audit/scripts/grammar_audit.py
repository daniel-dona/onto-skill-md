#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for spelling/grammar errors.

Primary: Hunspell via ctypes (autodetected or compiled from source).
Optional: LanguageTool for grammar (--grammar).

The script looks for libhunspell in:
  1. System paths (/usr/lib, /usr/local/lib, etc.)
  2. HUNSPELL_PREFIX env var (set by build_hunspell.sh)
  3. ~/.local/share/hunspell-built/ (build_hunspell.sh default)

If not found, prints instructions to run build_hunspell.sh.

Usage:
    python grammar_audit.py <repo-path> [-o report.md] [--lang es en]

Requires:
    pip install rdflib
    libhunspell — run scripts/build_hunspell.sh if not on system
    Optional: pip install language-tool-python  (for --grammar)
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
# Hunspell via ctypes
# ---------------------------------------------------------------------------

# BCP47 → hunspell dict name
HUNSPELL_DICT_MAP = {
    "en": "en_US", "en-us": "en_US", "en-gb": "en_GB",
    "es": "es_ES", "es-es": "es_ES", "es-419": "es_ANY", "es-ar": "es_AR",
    "fr": "fr", "fr-fr": "fr",
    "de": "de_DE_frami", "de-de": "de_DE_frami",
    "de-at": "de_AT_frami", "de-ch": "de_CH_frami",
    "pt": "pt_BR", "pt-pt": "pt_PT", "pt-br": "pt_BR",
    "it": "it_IT", "it-it": "it_IT",
    "nl": "nl_NL", "ru": "ru_RU", "ar": "ar",
    "ca": "ca", "gl": "gl", "ro": "ro", "sv": "sv_SE",
    "cs": "cs_CZ", "da": "da_DK", "el": "el_GR",
    "fi": "fi_FI", "hu": "hu_HU", "ko": "ko_KR",
    "no": "no", "nb": "no",
    "pl": "pl_PL", "sk": "sk_SK", "sl": "sl_SI",
    "tr": "tr_TR", "uk": "uk_UA", "he": "he_IL",
    "id": "id_ID", "vi": "vi_VN",
}

# Where to look for libhunspell
_LIB_SEARCH_PATTERNS = [
    # Built by build_hunspell.sh (HUNSPELL_PREFIX or default)
    "{prefix}/lib/libhunspell-1.7.so",
    "{prefix}/lib/libhunspell-1.7.so.0",
    "{prefix}/lib/libhunspell-1.7.so.0.1.0",
    "{prefix}/lib/libhunspell-1.7.dylib",
    "{prefix}/lib/libhunspell-1.7.dll",
    # System paths — Linux
    "/usr/lib/x86_64-linux-gnu/libhunspell-1.7.so*",
    "/usr/lib/x86_64-linux-gnu/libhunspell-1.6.so*",
    "/usr/lib/aarch64-linux-gnu/libhunspell-*.so*",
    "/usr/lib/libhunspell-*.so*",
    "/usr/local/lib/libhunspell*.so*",
    # System paths — macOS
    "/opt/homebrew/lib/libhunspell*.dylib",
    "/usr/local/lib/libhunspell*.dylib",
    # System paths — Windows/MSYS2
    "/mingw64/lib/libhunspell*.dll",
    "/mingw64/bin/libhunspell*.dll",
]

# Where to look for dictionaries (.aff + .dic)
_DICT_SEARCH_DIRS = [
    # Built by build_hunspell.sh
    "{prefix}/share/hunspell",
    # System paths
    "/usr/share/hunspell",
    "/usr/share/myspell/dicts",
    "/usr/local/share/hunspell",
    # macOS Homebrew
    "/opt/homebrew/share/hunspell",
    # Flatpak
    "/app/share/hunspell",
    # User
    os.path.expanduser("~/.local/share/hunspell"),
]

# Technical terms whitelist — skipped during spell-check
TECHNICAL_WORDS = frozenset({
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
})

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


class Hunspell:
    """Hunspell spell checker via ctypes — no Python binding needed."""

    def __init__(self):
        self._lib = None
        self._handles: dict[str, int] = {}
        self._available = False
        self._dict_dirs: list[str] = []
        self._prefix = os.environ.get(
            "HUNSPELL_PREFIX",
            os.path.expanduser("~/.local/share/hunspell-built"),
        )
        self._try_load()

    def _try_load(self):
        """Find and load libhunspell shared library."""
        # Expand prefix in search patterns
        patterns = []
        for p in _LIB_SEARCH_PATTERNS:
            if "{prefix}" in p:
                patterns.append(p.format(prefix=self._prefix))
            else:
                patterns.append(p)

        # Try ctypes.util.find_library first
        lib_name = ctypes.util.find_library("hunspell")
        if lib_name:
            patterns.insert(0, lib_name)

        so_paths = []
        for pattern in patterns:
            if "*" in pattern:
                so_paths.extend(sorted(glob.glob(pattern), reverse=True))
            else:
                so_paths.append(pattern)

        for so_path in so_paths:
            try:
                lib = ctypes.CDLL(so_path)
                if not hasattr(lib, "Hunspell_create"):
                    continue
                self._setup_api(lib)
                # Quick test: create and destroy a handle
                test_handle = lib.Hunspell_create(b"/dev/null", b"/dev/null")
                lib.Hunspell_destroy(test_handle)
                self._lib = lib
                self._available = True
                break
            except OSError:
                continue

        # Find dictionary directories
        for d in _DICT_SEARCH_DIRS:
            expanded = d.format(prefix=self._prefix) if "{prefix}" in d else d
            if os.path.isdir(expanded) and glob.glob(os.path.join(expanded, "*.aff")):
                self._dict_dirs.append(expanded)

    @staticmethod
    def _setup_api(lib):
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
        lib.Hunspell_add.restype = ctypes.c_int
        lib.Hunspell_add.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.Hunspell_add_with_affix.restype = ctypes.c_int
        lib.Hunspell_add_with_affix.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p,
        ]
        lib.Hunspell_destroy.restype = None
        lib.Hunspell_destroy.argtypes = [ctypes.c_void_p]

    @property
    def available(self) -> bool:
        return self._available

    @property
    def supported_languages(self) -> set[str]:
        """Return BCP47 tags for which we have dictionaries."""
        if not self._dict_dirs:
            return set()
        available_dicts = set()
        for d in self._dict_dirs:
            for f in os.listdir(d):
                if f.endswith(".aff"):
                    available_dicts.add(f[:-4])
        return {
            bcp47 for bcp47, dict_name in HUNSPELL_DICT_MAP.items()
            if dict_name in available_dicts
        }

    def _get_handle(self, lang: str) -> int | None:
        lang_lower = lang.lower()
        if lang_lower in self._handles:
            return self._handles[lang_lower]

        dict_name = HUNSPELL_DICT_MAP.get(lang_lower)
        if not dict_name:
            self._handles[lang_lower] = None
            return None

        aff_path, dic_path = None, None
        for d in self._dict_dirs:
            ca = os.path.join(d, dict_name + ".aff")
            cd = os.path.join(d, dict_name + ".dic")
            if os.path.isfile(ca) and os.path.isfile(cd):
                aff_path, dic_path = ca, cd
                break

        if not aff_path:
            self._handles[lang_lower] = None
            return None

        try:
            handle = self._lib.Hunspell_create(
                aff_path.encode(), dic_path.encode()
            )
            self._handles[lang_lower] = handle if handle else None
            return self._handles[lang_lower]
        except Exception:
            self._handles[lang_lower] = None
            return None

    def add_word(self, word: str, lang: str, example: str | None = None):
        """Add a word to the runtime dictionary for a language."""
        handle = self._get_handle(lang)
        if not handle:
            return
        encoded = word.encode("utf-8")
        if example:
            self._lib.Hunspell_add_with_affix(handle, encoded, example.encode("utf-8"))
        else:
            self._lib.Hunspell_add(handle, encoded)

    def check(self, words: list[str], lang: str) -> list[dict]:
        """Check a list of words. Returns issues for misspelled ones."""
        handle = self._get_handle(lang)
        if not handle:
            return []

        check_words = [
            w for w in words
            if len(w) >= 3 and not w.isdigit() and w.lower() not in TECHNICAL_WORDS
        ]
        if not check_words:
            return []

        issues = []
        for word in check_words:
            result = self._lib.Hunspell_spell(handle, word.encode("utf-8"))
            if not result:
                suggestions = self._get_suggestions(handle, word)
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

    def _get_suggestions(self, handle: int, word: str) -> list[str]:
        """Get spelling suggestions for a word."""
        try:
            slst = ctypes.POINTER(ctypes.c_char_p)()
            n = self._lib.Hunspell_suggest(
                handle, ctypes.byref(slst), word.encode("utf-8")
            )
            result = [
                slst[i].decode("utf-8", errors="replace")
                for i in range(min(n, 5))
            ]
            self._lib.Hunspell_free_list(handle, ctypes.byref(slst), n)
            return result
        except Exception:
            return []

    def __del__(self):
        if self._lib:
            for handle in self._handles.values():
                if handle:
                    try:
                        self._lib.Hunspell_destroy(handle)
                    except Exception:
                        pass


# Global instance
_hunspell: Hunspell | None = None


def get_hunspell() -> Hunspell:
    global _hunspell
    if _hunspell is None:
        _hunspell = Hunspell()
        if _hunspell.available:
            langs = sorted(_hunspell.supported_languages)
            dicts = sorted(set(HUNSPELL_DICT_MAP[l] for l in langs))
            print(f"[INFO] Hunspell loaded — {len(dicts)} dictionaries: "
                  f"{', '.join(dicts)}", file=sys.stderr)
        else:
            print("[ERROR] libhunspell not found!", file=sys.stderr)
            print("", file=sys.stderr)
            print("Install hunspell one of:", file=sys.stderr)
            print("  1. Build from source (no root):", file=sys.stderr)
            print("       bash scripts/build_hunspell.sh", file=sys.stderr)
            print("  2. System package:", file=sys.stderr)
            print("       Debian/Ubuntu: sudo apt install libhunspell-dev hunspell-es", file=sys.stderr)
            print("       Fedora:        sudo dnf install hunspell-devel hunspell-es", file=sys.stderr)
            print("       macOS:         brew install hunspell", file=sys.stderr)
            sys.exit(1)
    return _hunspell


# ---------------------------------------------------------------------------
# LanguageTool (optional, for grammar)
# ---------------------------------------------------------------------------

def _get_lt_tool(lang_code: str):
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
    """Compare declared language against other languages in the repo."""
    hs = get_hunspell()
    if len(value.strip()) < 20:
        return []

    words = re.findall(r"[\w']+", value)
    issues_declared = hs.check(words, lang)
    if not issues_declared and lang not in hs.supported_languages:
        return []

    error_count = len(issues_declared)
    if error_count < 3:
        return []

    other_langs = all_langs - {lang} - {lang.lower()}
    best_alt, best_errors = None, error_count

    for alt in other_langs:
        if alt not in hs.supported_languages:
            continue
        alt_issues = hs.check(words, alt)
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
    hs = get_hunspell()

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

    # Load custom words into hunspell runtime dictionaries
    custom = list(custom_words) if custom_words else []
    if custom_dict_file:
        try:
            with open(custom_dict_file, "r", encoding="utf-8") as f:
                for line in f:
                    word = line.strip().split("#")[0].strip()
                    if word:
                        custom.append(word)
            print(f"[INFO] Loaded custom words from {custom_dict_file}",
                  file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Cannot read {custom_dict_file}: {e}", file=sys.stderr)

    if custom:
        for lang in all_langs:
            if lang in hs.supported_languages:
                for word in custom:
                    hs.add_word(word, lang)
        print(f"[INFO] Added {len(custom)} custom words to runtime dictionaries",
              file=sys.stderr)

    supported = all_langs & hs.supported_languages
    unsupported = all_langs - supported

    unique_count = len(seen)
    print(f"[INFO] Checking {unique_count} unique literal+lang combinations "
          f"({len(literals)} total)...", file=sys.stderr)
    if unsupported:
        print(f"[INFO] No dictionaries for: {', '.join(sorted(unsupported))} "
              f"— use --grammar for these", file=sys.stderr)
    if check_mismatch:
        print(f"[INFO] Lang-mismatch detection: ON", file=sys.stderr)

    # Phase 1: spelling
    report = []
    checked = 0

    for (value, lang), occurrences in seen.items():
        checked += 1
        if checked % 200 == 0 or checked == unique_count:
            print(f"  ...checked {checked}/{unique_count}", file=sys.stderr)

        words = re.findall(r"[\w']+", value)
        issues = hs.check(words, lang)

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

    # Phase 2: grammar (optional)
    if use_grammar:
        # Check unsupported languages with LT
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
            print(f"[INFO] Running LanguageTool on {len(report)} literals...",
                  file=sys.stderr)
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
                        print(f"[WARN] LT error for {key}: {e}", file=sys.stderr)
                    done += 1
                    if done % 50 == 0 or done == len(report):
                        print(f"  ...LT checked {done}/{len(report)}",
                              file=sys.stderr)

    report = [e for e in report if e["issues"] or e.get("lang_warnings")]
    print(f"[INFO] Done. {len(report)} literals with issues.", file=sys.stderr)
    return report


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def format_report_markdown(report: list[dict]) -> str:
    lines = ["# Ontology Typo Audit Report", ""]
    lines.append("_Generated by `ontology-typo-audit` skill (rdflib + hunspell)_")
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
            val = entry["value"]
            short = val[:100] + ("..." if len(val) > 100 else "")
            lines.append(f"### {i}. `{short}`")
            lines.append(f"- **Full text:** {val}")

            if entry.get("lang_warnings"):
                for w in entry["lang_warnings"]:
                    lines.append(f"- ⚠️ **Lang tag warning:** {w}")

            by_checker = {}
            for issue in entry["issues"]:
                by_checker.setdefault(issue.get("checker", "?"), []).append(issue)

            for ck, ck_issues in by_checker.items():
                label = {"hunspell": "📖 Spelling",
                         "languagetool": "✍️ Grammar"}.get(ck, ck)
                lines.append(f"- **{label}:**")
                for issue in ck_issues:
                    sg = ", ".join(f"`{s}`" for s in issue["suggestions"]) \
                         if issue["suggestions"] else "(none)"
                    wi = f" `{issue['word']}`" if issue.get("word") else ""
                    lines.append(f"  - **{issue['rule']}**{wi}: {issue['message']}")
                    if sg != "(none)":
                        lines.append(f"    - Suggestions: {sg}")

            lines.append("- **Occurs in:**")
            for occ in entry["occurrences"]:
                lines.append(f"  - `{occ['file']}` — "
                             f"{occ['subject_short']} → "
                             f"{occ['predicate_short']}")
            lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Audit RDF literals for spelling/grammar errors. "
                    "Uses hunspell (ctypes, must be installed) for spelling, "
                    "LanguageTool for grammar (--grammar)."
    )
    parser.add_argument("repo_path",
                        help="Path to the ontology repository")
    parser.add_argument("-o", "--output",
                        help="Output file (.json or .md)")
    parser.add_argument("--lang", nargs="+", default=None,
                        help="Only check these language tags")
    parser.add_argument("--grammar", action="store_true",
                        help="Also run LanguageTool grammar check (slow)")
    parser.add_argument("--lt-max-errors", type=int, default=5,
                        help="Max LT issues per literal (default: 5)")
    parser.add_argument("--lt-min-length", type=int, default=10,
                        help="Skip LT on literals shorter than N chars (default: 10)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Parallel LT workers (default: {DEFAULT_WORKERS})")
    parser.add_argument("--dict", dest="custom_dict", default=None,
                        help="File with custom words (one per line, # comments)")
    parser.add_argument("--word", nargs="+", default=None,
                        help="Add custom words (e.g. --word pádel)")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode: spelling only, no mismatch, stricter LT")
    parser.add_argument("--dump", action="store_true",
                        help="Dump all string literals without checking")
    parser.add_argument("--no-lang", action="store_true",
                        help="Include literals without a language tag when dumping")
    parser.add_argument("--mismatch", action="store_true",
                        help="Enable lang-tag mismatch detection")
    parser.add_argument("--format", choices=["json", "markdown", "report"],
                        default="markdown",
                        help="Output format (default: markdown)")
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
