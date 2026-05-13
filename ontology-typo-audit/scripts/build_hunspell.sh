#!/usr/bin/env bash
# build_hunspell.sh — Compile hunspell from source + download dictionaries
#
# Compiles libhunspell as a shared library. Downloads dictionaries from
# the LibreOffice repository based on:
#   --repo <path>  : auto-detect langs from the ontology repo (recommended)
#   --langs xx,yy  : explicit language list
#   (default)      : english only
#
# Install to local prefix (no root needed).
#
# Dependencies: g++ make autoconf automake autopoint libtool
#
set -euo pipefail

PREFIX="${HUNSPELL_PREFIX:-$HOME/.local/share/hunspell-built}"
HUNSPELL_VERSION="1.7.3"
HUNSPELL_REPO="https://github.com/hunspell/hunspell.git"
DICT_BASE="https://raw.githubusercontent.com/LibreOffice/dictionaries/master"

# Map short lang codes to (LO_dir/dict_name)
declare -A LANG_MAP
LANG_MAP[en]="en/en_US"
LANG_MAP[es]="es/es_ES"
LANG_MAP[fr]="fr_FR/fr"
LANG_MAP[de]="de/de_DE_frami"
LANG_MAP[it]="it_IT/it_IT"
LANG_MAP[pt]="pt_BR/pt_BR"
LANG_MAP[nl]="nl_NL/nl_NL"
LANG_MAP[ru]="ru_RU/ru_RU"
LANG_MAP[ar]="ar/ar"
LANG_MAP[ca]="ca/ca"
LANG_MAP[gl]="gl/gl_ES"
LANG_MAP[ro]="ro/ro_RO"
LANG_MAP[sv]="sv_SE/sv_SE"
LANG_MAP[cs]="cs_CZ/cs_CZ"
LANG_MAP[da]="da_DK/da_DK"
LANG_MAP[el]="el_GR/el_GR"
LANG_MAP[fi]="fi_FI/fi_FI"
LANG_MAP[hu]="hu_HU/hu_HU"
LANG_MAP[ko]="ko_KR/ko_KR"
LANG_MAP[no]="no/nb_NO"
LANG_MAP[nb]="no/nb_NO"
LANG_MAP[pl]="pl_PL/pl_PL"
LANG_MAP[sk]="sk_SK/sk_SK"
LANG_MAP[sl]="sl_SI/sl_SI"
LANG_MAP[tr]="tr_TR/tr_TR"
LANG_MAP[uk]="uk_UA/uk_UA"
LANG_MAP[he]="he_IL/he_IL"
LANG_MAP[id]="id/id_ID"
LANG_MAP[vi]="vi/vi_VN"
LANG_MAP[bg]="bg_BG/bg_BG"
LANG_MAP[hr]="hr_HR/hr_HR"
LANG_MAP[et]="et_EE/et_EE"
LANG_MAP[lt]="lt/lt_LT"
LANG_MAP[lv]="lv_LV/lv_LV"
LANG_MAP[fa]="fa-IR/fa_IR"
LANG_MAP[hi]="hi_IN/hi_IN"
LANG_MAP[th]="th_TH/th_TH"
LANG_MAP[eo]="eo/eo"
LANG_MAP[af]="af_ZA/af_ZA"

# Parse args
REPO_PATH=""
LANGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --repo)
            shift
            REPO_PATH="$1"
            ;;
        --langs)
            shift
            IFS=',' read -ra LANGS <<< "$1"
            ;;
        --prefix)
            shift
            PREFIX="$1"
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Compile hunspell from source and download dictionaries."
            echo ""
            echo "Options:"
            echo "  --repo <path>   Auto-detect languages from ontology repo"
            echo "  --langs xx,yy   Explicit language codes (e.g. es,en,de)"
            echo "  --prefix <dir>  Install prefix (default: ~/.local/share/hunspell-built)"
            echo ""
            echo "If neither --repo nor --langs is given, defaults to English."
            echo ""
            echo "Available --langs codes:"
            echo "  en es fr de it pt nl ru ar ca gl ro sv cs da el fi hu ko"
            echo "  no pl sk sl tr uk he id vi bg hr et lt lv fa hi th eo af"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

# ── Detect languages from repo ─────────────────────────────────────
if [[ -n "$REPO_PATH" ]]; then
    echo "[INFO] Detecting languages from $REPO_PATH..."
    DETECTED=$(python3 -c "
import sys; sys.path.insert(0, '$(dirname \"$0\")')
from grammar_audit import extract_literals, detect_languages
lits = extract_literals('$REPO_PATH', include_no_lang=False)
langs = detect_languages(lits)
if not langs:
    langs = {'en'}
print(','.join(sorted(langs)))
" 2>/dev/null)
    if [[ -n "$DETECTED" ]]; then
        IFS=',' read -ra LANGS <<< "$DETECTED"
        echo "  Detected: ${LANGS[*]}"
    else
        echo "  No languages detected — defaulting to English"
        LANGS=("en")
    fi
fi

# Default: English only
if [[ ${#LANGS[@]} -eq 0 ]]; then
    LANGS=("en")
    echo "[INFO] No --repo or --langs specified — defaulting to English"
fi

echo "============================================================"
echo "  Hunspell Build Script"
echo "  Prefix:  $PREFIX"
echo "  Langs:   ${LANGS[*]}"
echo "============================================================"

# ── Step 1: Compile hunspell ────────────────────────────────────────
echo ""
echo "[1/2] Compiling hunspell $HUNSPELL_VERSION..."

BUILD_DIR=$(mktemp -d)
trap 'rm -rf "$BUILD_DIR"' EXIT

if ! command -v g++ &>/dev/null; then
    echo "[ERROR] g++ not found. Install build dependencies:" >&2
    echo "  Debian/Ubuntu: sudo apt install g++ make autoconf automake autopoint libtool" >&2
    echo "  Fedora:        sudo dnf install gcc-c++ make autoconf automake libtool gettext-devel" >&2
    echo "  macOS:         xcode-select --install && brew install autoconf automake libtool gettext" >&2
    exit 1
fi

for tool in make autoconf automake libtool; do
    if ! command -v "$tool" &>/dev/null; then
        echo "[ERROR] $tool not found. Install build dependencies (see above)." >&2
        exit 1
    fi
done

git clone --depth 1 --branch "v$HUNSPELL_VERSION" "$HUNSPELL_REPO" "$BUILD_DIR/hunspell" 2>&1 | tail -1

cd "$BUILD_DIR/hunspell"
autoreconf -vfi 2>&1 | tail -1
./configure --prefix="$PREFIX" --without-ui --without-readline 2>&1 | tail -1
make -j"$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 2)" 2>&1 | tail -1
make install 2>&1 | tail -1

if [[ -f "$PREFIX/lib/libhunspell-1.7.so" ]] || [[ -f "$PREFIX/lib/libhunspell-1.7.dylib" ]]; then
    echo "  ✓ libhunspell compiled and installed"
else
    echo "[ERROR] libhunspell not found after build!" >&2
    exit 1
fi

# ── Step 2: Download dictionaries ──────────────────────────────────
echo ""
echo "[2/2] Downloading dictionaries for: ${LANGS[*]}..."

DICT_DIR="$PREFIX/share/hunspell"
mkdir -p "$DICT_DIR"

DOWNLOADED=0
SKIPPED=0
for lang in "${LANGS[@]}"; do
    mapping="${LANG_MAP[$lang]:-}"
    if [[ -z "$mapping" ]]; then
        echo "  ✗ $lang: unknown language code (skipping)" >&2
        ((SKIPPED++))
        continue
    fi

    lo_dir="${mapping%%/*}"
    dict_name="${mapping##*/}"

    # Skip if already downloaded
    if [[ -f "$DICT_DIR/$dict_name.aff" ]] && [[ -f "$DICT_DIR/$dict_name.dic" ]]; then
        echo "  ✓ $lang ($dict_name) — already present"
        ((DOWNLOADED++))
        continue
    fi

    echo "  Downloading $lang ($dict_name)..."
    curl -sL "$DICT_BASE/$lo_dir/$dict_name.aff" -o "$DICT_DIR/$dict_name.aff"
    curl -sL "$DICT_BASE/$lo_dir/$dict_name.dic" -o "$DICT_DIR/$dict_name.dic"

    if [[ -f "$DICT_DIR/$dict_name.aff" ]] && [[ -f "$DICT_DIR/$dict_name.dic" ]]; then
        aff_size=$(stat -f%z "$DICT_DIR/$dict_name.aff" 2>/dev/null || stat -c%s "$DICT_DIR/$dict_name.aff" 2>/dev/null || echo 0)
        dic_size=$(stat -f%z "$DICT_DIR/$dict_name.dic" 2>/dev/null || stat -c%s "$DICT_DIR/$dict_name.dic" 2>/dev/null || echo 0)
        echo "    ✓ $dict_name.aff ($(( aff_size / 1024 )) KB) + $dict_name.dic ($(( dic_size / 1024 )) KB)"
        ((DOWNLOADED++))
    else
        echo "    ✗ Failed to download $dict_name" >&2
        ((SKIPPED++))
    fi
done

# ── Summary ────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Done!"
echo "  Library:      $PREFIX/lib/"
echo "  Dictionaries: $DICT_DIR/"
echo "  Downloaded:   $DOWNLOADED ok, $SKIPPED skipped"
echo ""
echo "To use with grammar_audit.py:"
echo "  export HUNSPELL_PREFIX=$PREFIX"
echo "  python scripts/grammar_audit.py <repo-path>"
echo ""
echo "Or just run grammar_audit.py — it auto-downloads missing dicts."
echo "============================================================"
