#!/usr/bin/env python3
"""
grammar_audit.py — Audit string literals for spelling/grammar errors.

Spell checker: Hunspell via ctypes (compiled from source or system).
Auto-downloads dictionaries from LibreOffice based on the project's
language tags. If no lang tags found, defaults to English.

Grammar checker: LanguageTool (optional --grammar).

Usage:
    python grammar_audit.py <repo-path> [-o report.md]

Requires:
    pip install rdflib
    libhunspell — run scripts/build_hunspell.sh if not on system
    Optional: pip install language-tool-python (for --grammar)
"""
import argparse
import ctypes
import ctypes.util
import glob
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rdflib import Graph, Literal

from rdf_utils import find_rdf_files, compact_uri


# ---------------------------------------------------------------------------
# LibreOffice dictionary download map
# dict_name → LO repo subdirectory
# ---------------------------------------------------------------------------

DICT_DOWNLOAD_MAP = {
    "af_ZA": "af_ZA",
    "an_ES": "an_ES",
    "ar": "ar",
    "as_IN": "as_IN",
    "be_BY": "be-official",
    "bg_BG": "bg_BG",
    "bn_BD": "bn_BD",
    "bo": "bo",
    "br_FR": "br_FR",
    "bs_BA": "bs_BA",
    "ca": "ca",
    "cs_CZ": "cs_CZ",
    "da_DK": "da_DK",
    "de_AT_frami": "de",
    "de_CH_frami": "de",
    "de_DE_frami": "de",
    "el_GR": "el_GR",
    "en_AU": "en",
    "en_CA": "en",
    "en_GB": "en",
    "en_US": "en",
    "en_ZA": "en",
    "eo": "eo",
    "es_AR": "es",
    "es_BO": "es",
    "es_CL": "es",
    "es_CO": "es",
    "es_CR": "es",
    "es_CU": "es",
    "es_DO": "es",
    "es_EC": "es",
    "es_ES": "es",
    "es_GQ": "es",
    "es_GT": "es",
    "es_HN": "es",
    "es_MX": "es",
    "es_NI": "es",
    "es_PA": "es",
    "es_PE": "es",
    "es_PH": "es",
    "es_PR": "es",
    "es_PY": "es",
    "es_SV": "es",
    "es_US": "es",
    "es_UY": "es",
    "es_VE": "es",
    "et_EE": "et_EE",
    "fa_IR": "fa-IR",
    "fr": "fr_FR",
    "gd_GB": "gd_GB",
    "gl_ES": "gl",
    "gu_IN": "gu_IN",
    "gug": "gug",
    "he_IL": "he_IL",
    "hi_IN": "hi_IN",
    "hr_HR": "hr_HR",
    "hu_HU": "hu_HU",
    "id_ID": "id",
    "is": "is",
    "it_IT": "it_IT",
    "kmr_Latn": "kmr_Latn",
    "kn_IN": "kn_IN",
    "ko_KR": "ko_KR",
    "lo_LA": "lo_LA",
    "lt_LT": "lt",
    "lv_LV": "lv_LV",
    "mn_MN": "mn_MN",
    "mr_IN": "mr_IN",
    "ne_NP": "ne_NP",
    "nl_NL": "nl_NL",
    "nb_NO": "no",
    "nn_NO": "no",
    "oc_FR": "oc_FR",
    "or_IN": "or_IN",
    "pa_IN": "pa_IN",
    "pl_PL": "pl_PL",
    "pt_BR": "pt_BR",
    "pt_PT": "pt_PT",
    "ro_RO": "ro",
    "ru_RU": "ru_RU",
    "sa_IN": "sa_IN",
    "si_LK": "si_LK",
    "sk_SK": "sk_SK",
    "sl_SI": "sl_SI",
    "sq_AL": "sq_AL",
    "sr": "sr",
    "sv_SE": "sv_SE",
    "sw_TZ": "sw_TZ",
    "ta_IN": "ta_IN",
    "te_IN": "te_IN",
    "th_TH": "th_TH",
    "tr_TR": "tr_TR",
    "uk_UA": "uk_UA",
    "vi_VN": "vi",
    "zu_ZA": "zu_ZA",
}

DICT_BASE_URL = "https://raw.githubusercontent.com/LibreOffice/dictionaries/master"

# BCP47 → preferred hunspell dict name
BCP47_TO_DICT = {
    "en": "en_US", "en-us": "en_US", "en-gb": "en_GB",
    "es": "es_ES", "es-es": "es_ES", "es-419": "es_ANY", "es-ar": "es_AR",
    "fr": "fr", "fr-fr": "fr",
    "de": "de_DE_frami", "de-de": "de_DE_frami",
    "de-at": "de_AT_frami", "de-ch": "de_CH_frami",
    "pt": "pt_PT", "pt-pt": "pt_PT", "pt-br": "pt_BR",
    "it": "it_IT", "it-it": "it_IT",
    "nl": "nl_NL", "ru": "ru_RU", "ar": "ar",
    "ca": "ca", "gl": "gl_ES", "ro": "ro_RO", "sv": "sv_SE",
    "cs": "cs_CZ", "da": "da_DK", "el": "el_GR",
    "fi": "fi_FI", "hu": "hu_HU", "ko": "ko_KR",
    "no": "nb_NO", "nb": "nb_NO", "nn": "nn_NO",
    "pl": "pl_PL", "sk": "sk_SK", "sl": "sl_SI",
    "tr": "tr_TR", "uk": "uk_UA", "he": "he_IL",
    "id": "id_ID", "vi": "vi_VN",
    "bg": "bg_BG", "hr": "hr_HR", "et": "et_EE",
    "lt": "lt_LT", "lv": "lv_LV", "fa": "fa_IR",
    "hi": "hi_IN", "th": "th_TH", "eo": "eo",
    "af": "af_ZA", "bn": "bn_BD", "gu": "gu_IN",
    "kn": "kn_IN", "ml": None, "mr": "mr_IN",
    "pa": "pa_IN", "si": "si_LK", "sw": "sw_TZ",
    "ta": "ta_IN", "te": "te_IN", "zu": "zu_ZA",
    "bs": "bs_BA", "br": "br_FR", "cy": None,
    "ga": None, "gd": "gd_GB", "is": "is",
    "km": None, "lo": "lo_LA", "mn": "mn_MN",
    "ne": "ne_NP", "oc": "oc_FR", "or": "or_IN",
    "sa": "sa_IN", "sq": "sq_AL", "sr": "sr",
    "as": "as_IN", "bo": "bo", "ku": "kmr_Latn",
}

# Technical terms whitelist
TECHNICAL_WORDS = frozenset({
    "rdf", "rdfs", "owl", "skos", "xsd", "shacl", "sh", "sosa", "ssn",
    "qudt", "geosparql", "voaf", "void", "dcat", "foaf", "schema", "dc",
    "dcterms", "bibo", "frbr", "prov", "org", "time", "hydra", "ldp",
    "owl2", "owlrl", "n3", "turtle", "ttl", "nt", "nquads", "nq", "trig",
    "jsonld", "rdfa", "sparql",
    "hcho", "nox", "sox", "pm10", "pm25", "co2", "ch4", "n2o", "o3",
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


# ---------------------------------------------------------------------------
# Literal extraction + lang detection
# ---------------------------------------------------------------------------

def extract_literals(repo_path: str, include_no_lang: bool = False) -> list[dict]:
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


def detect_languages(literals: list[dict]) -> set[str]:
    """Extract unique BCP47 language tags from literals."""
    langs = set()
    for lit in literals:
        if lit["lang"]:
            langs.add(lit["lang"].lower())
    return langs


# ---------------------------------------------------------------------------
# Dictionary downloading
# ---------------------------------------------------------------------------

def get_dict_dir() -> str:
    """Get the dictionary storage directory."""
    prefix = os.environ.get(
        "HUNSPELL_PREFIX",
        os.path.expanduser("~/.local/share/hunspell-built"),
    )
    return os.path.join(prefix, "share", "hunspell")


def download_dict(dict_name: str, dict_dir: str) -> bool:
    """Download a .aff + .dic pair from LibreOffice. Returns True on success."""
    lo_dir = DICT_DOWNLOAD_MAP.get(dict_name)
    if not lo_dir:
        return False

    aff_url = f"{DICT_BASE_URL}/{lo_dir}/{dict_name}.aff"
    dic_url = f"{DICT_BASE_URL}/{lo_dir}/{dict_name}.dic"
    aff_path = os.path.join(dict_dir, f"{dict_name}.aff")
    dic_path = os.path.join(dict_dir, f"{dict_name}.dic")

    try:
        os.makedirs(dict_dir, exist_ok=True)

        # Download .aff
        urllib.request.urlretrieve(aff_url, aff_path + ".tmp")
        os.rename(aff_path + ".tmp", aff_path)

        # Download .dic
        urllib.request.urlretrieve(dic_url, dic_path + ".tmp")
        os.rename(dic_path + ".tmp", dic_path)

        aff_size = os.path.getsize(aff_path)
        dic_size = os.path.getsize(dic_path)
        print(f"  ✓ {dict_name} (.aff {aff_size // 1024}KB + .dic {dic_size // 1024}KB)",
              file=sys.stderr)
        return True
    except Exception as e:
        # Clean up partial files
        for p in (aff_path + ".tmp", aff_path, dic_path + ".tmp", dic_path):
            try:
                os.unlink(p)
            except OSError:
                pass
        print(f"  ✗ {dict_name}: {e}", file=sys.stderr)
        return False


def ensure_dicts(langs: set[str], dict_dir: str) -> set[str]:
    """
    Ensure dictionaries exist for the given BCP47 language tags.
    Downloads missing ones from LibreOffice.
    Returns the set of BCP47 tags that now have dictionaries.
    """
    os.makedirs(dict_dir, exist_ok=True)
    available = set()  # BCP47 tags that have dicts
    to_download = []

    for lang in sorted(langs):
        dict_name = BCP47_TO_DICT.get(lang)
        if dict_name is None:
            continue

        aff_path = os.path.join(dict_dir, f"{dict_name}.aff")
        dic_path = os.path.join(dict_dir, f"{dict_name}.dic")

        if os.path.isfile(aff_path) and os.path.isfile(dic_path):
            available.add(lang)
        elif dict_name in DICT_DOWNLOAD_MAP:
            to_download.append((lang, dict_name))

    if to_download:
        print(f"[INFO] Downloading {len(to_download)} dictionaries from "
              f"LibreOffice...", file=sys.stderr)
        for lang, dict_name in to_download:
            if download_dict(dict_name, dict_dir):
                available.add(lang)

    return available


# ---------------------------------------------------------------------------
# Hunspell via ctypes
# ---------------------------------------------------------------------------

_LIB_SEARCH_PATTERNS = [
    "{prefix}/lib/libhunspell-1.7.so",
    "{prefix}/lib/libhunspell-1.7.so.0",
    "{prefix}/lib/libhunspell-1.7.so.0.1.0",
    "{prefix}/lib/libhunspell-1.7.dylib",
    "{prefix}/lib/libhunspell-1.7.dll",
    "/usr/lib/x86_64-linux-gnu/libhunspell-1.7.so*",
    "/usr/lib/x86_64-linux-gnu/libhunspell-1.6.so*",
    "/usr/lib/aarch64-linux-gnu/libhunspell-*.so*",
    "/usr/lib/libhunspell-*.so*",
    "/usr/local/lib/libhunspell*.so*",
    "/opt/homebrew/lib/libhunspell*.dylib",
    "/usr/local/lib/libhunspell*.dylib",
    "/mingw64/lib/libhunspell*.dll",
    "/mingw64/bin/libhunspell*.dll",
]


class Hunspell:
    """Hunspell spell checker via ctypes."""

    def __init__(self, dict_dir: str):
        self._lib = None
        self._handles: dict[str, int] = {}
        self._available = False
        self._dict_dir = dict_dir
        self._prefix = os.environ.get(
            "HUNSPELL_PREFIX",
            os.path.expanduser("~/.local/share/hunspell-built"),
        )
        self._try_load()

    def _try_load(self):
        patterns = []
        for p in _LIB_SEARCH_PATTERNS:
            if "{prefix}" in p:
                patterns.append(p.format(prefix=self._prefix))
            else:
                patterns.append(p)

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
                self._lib = lib
                self._available = True
                return
            except OSError:
                continue

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
    def dict_dir(self) -> str:
        return self._dict_dir

    def available_dicts(self) -> set[str]:
        """Return dict names that have .aff + .dic in dict_dir."""
        if not os.path.isdir(self._dict_dir):
            return set()
        dicts = set()
        for f in os.listdir(self._dict_dir):
            if f.endswith(".aff"):
                base = f[:-4]
                dic = os.path.join(self._dict_dir, base + ".dic")
                if os.path.isfile(dic):
                    dicts.add(base)
        return dicts

    def supported_languages(self) -> set[str]:
        """Return BCP47 tags for which we have dictionaries."""
        avail = self.available_dicts()
        return {
            bcp47 for bcp47, dict_name in BCP47_TO_DICT.items()
            if dict_name and dict_name in avail
        }

    def _get_handle(self, lang: str) -> int | None:
        lang_lower = lang.lower()
        if lang_lower in self._handles:
            return self._handles[lang_lower]

        dict_name = BCP47_TO_DICT.get(lang_lower)
        if not dict_name:
            self._handles[lang_lower] = None
            return None

        aff_path = os.path.join(self._dict_dir, dict_name + ".aff")
        dic_path = os.path.join(self._dict_dir, dict_name + ".dic")

        if not os.path.isfile(aff_path) or not os.path.isfile(dic_path):
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
        handle = self._get_handle(lang)
        if not handle:
            return
        encoded = word.encode("utf-8")
        if example:
            self._lib.Hunspell_add_with_affix(
                handle, encoded, example.encode("utf-8"))
        else:
            self._lib.Hunspell_add(handle, encoded)

    def check(self, words: list[str], lang: str) -> list[dict]:
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


# ---------------------------------------------------------------------------
# LanguageTool (optional, for grammar)
# ---------------------------------------------------------------------------

def _get_lt_tool(lang_code: str):
    lt_lang = LT_LANG_MAP.get(lang_code.lower(), lang_code)
    if lt_lang not in _lt_cache:
        try:
            import language_tool_python
            tool = language_tool_python.LanguageTool(lt_lang)
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

def detect_lang_mismatch(value: str, lang: str, all_langs: set[str],
                         hs: Hunspell) -> list[str]:
    if len(value.strip()) < 20:
        return []

    words = re.findall(r"[\w']+", value)
    issues_declared = hs.check(words, lang)
    error_count = len(issues_declared)
    if error_count < 3:
        return []

    other_langs = all_langs - {lang} - {lang.lower()}
    best_alt, best_errors = None, error_count

    for alt in other_langs:
        if alt not in hs.supported_languages():
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

    # Step 1: Extract literals and detect languages
    print(f"[INFO] Extracting literals from {repo_path}...", file=sys.stderr)
    literals = extract_literals(repo_path, include_no_lang=False)

    if not literals:
        print("[WARN] No literals with lang tags found.", file=sys.stderr)
        return []

    all_langs = detect_languages(literals)
    if not all_langs:
        print("[INFO] No language tags found — defaulting to English (@en)",
              file=sys.stderr)
        all_langs = {"en"}

    if filter_langs:
        lang_set = set(l.lower() for l in filter_langs)
        literals = [l for l in literals if l["lang"] and l["lang"].lower() in lang_set]
        all_langs = all_langs & lang_set
        if not all_langs:
            print(f"[WARN] No literals found for languages: {filter_langs}",
                  file=sys.stderr)
            return []

    print(f"[INFO] Languages in project: {', '.join(sorted(all_langs))}",
          file=sys.stderr)

    # Step 2: Ensure dictionaries are available
    dict_dir = get_dict_dir()
    available_langs = ensure_dicts(all_langs, dict_dir)

    # Also scan system dict dirs for pre-installed dicts
    system_dict_dirs = [
        "/usr/share/hunspell",
        "/usr/share/myspell/dicts",
        "/usr/local/share/hunspell",
        "/opt/homebrew/share/hunspell",
    ]
    for sd in system_dict_dirs:
        if os.path.isdir(sd):
            for lang in all_langs - available_langs:
                dict_name = BCP47_TO_DICT.get(lang)
                if dict_name:
                    aff = os.path.join(sd, dict_name + ".aff")
                    dic = os.path.join(sd, dict_name + ".dic")
                    if os.path.isfile(aff) and os.path.isfile(dic):
                        # Symlink or copy into our dict_dir
                        dst_aff = os.path.join(dict_dir, dict_name + ".aff")
                        dst_dic = os.path.join(dict_dir, dict_name + ".dic")
                        if not os.path.isfile(dst_aff):
                            try:
                                os.symlink(aff, dst_aff)
                                os.symlink(dic, dst_dic)
                                available_langs.add(lang)
                            except OSError:
                                pass

    # Step 3: Initialize hunspell
    hs = Hunspell(dict_dir)
    if not hs.available:
        print("[ERROR] libhunspell not found!", file=sys.stderr)
        print("", file=sys.stderr)
        print("Install hunspell:", file=sys.stderr)
        print("  bash scripts/build_hunspell.sh    # Build from source (no root)",
              file=sys.stderr)
        print("  sudo apt install libhunspell-dev   # Debian/Ubuntu", file=sys.stderr)
        print("  brew install hunspell              # macOS", file=sys.stderr)
        sys.exit(1)

    supported = hs.supported_languages()
    unsupported = all_langs - supported
    if unsupported:
        print(f"[INFO] No dictionaries available for: "
              f"{', '.join(sorted(unsupported))}", file=sys.stderr)
        if not use_grammar:
            print(f"[INFO] Use --grammar to check these with LanguageTool.",
                  file=sys.stderr)

    # Reload after downloading dicts
    hs = Hunspell(dict_dir)

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
            print(f"[INFO] Loaded custom words from {custom_dict_file}",
                  file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Cannot read {custom_dict_file}: {e}", file=sys.stderr)

    if custom:
        for lang in supported:
            for word in custom:
                hs.add_word(word, lang)
        print(f"[INFO] Added {len(custom)} custom words to runtime dictionaries",
              file=sys.stderr)

    # Spell check
    unique_count = len(seen)
    print(f"[INFO] Checking {unique_count} unique literal+lang combinations "
          f"({len(literals)} total)...", file=sys.stderr)
    if check_mismatch:
        print(f"[INFO] Lang-mismatch detection: ON", file=sys.stderr)

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
            warnings = detect_lang_mismatch(value, lang, all_langs, hs)
            if warnings:
                entry["lang_warnings"] = warnings

        if issues or entry.get("lang_warnings"):
            report.append(entry)

    # Grammar check (optional)
    if use_grammar:
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
                    "Uses hunspell (ctypes) for spelling — auto-downloads "
                    "dictionaries based on the project's language tags. "
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
