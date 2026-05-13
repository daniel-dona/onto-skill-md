#!/usr/bin/env bash
# build_hunspell.sh — Compile hunspell from source + download dictionaries
#
# This script builds libhunspell as a shared library and downloads
# spell-checking dictionaries from the LibreOffice repository.
# Everything is installed into a local prefix (no root needed).
#
# Dependencies: g++ make autoconf automake autopoint libtool
#
# Usage:
#   bash scripts/build_hunspell.sh                    # default languages
#   bash scripts/build_hunspell.sh --langs es en de   # specific languages
#   bash scripts/build_hunspell.sh --prefix /opt/hunspell  # custom prefix
#
set -euo pipefail

PREFIX="${HUNSPELL_PREFIX:-$HOME/.local/share/hunspell-built}"
HUNSPELL_VERSION="1.7.3"
HUNSPELL_REPO="https://github.com/hunspell/hunspell.git"
DICT_REPO="https://raw.githubusercontent.com/LibreOffice/dictionaries/master"
BUILD_DIR=""

# Default languages to download dictionaries for
# Format: "directory/dict_name" — directory is the LO repo folder,
#         dict_name is the .aff/.dic base name
DEFAULT_DICTS=(
    "en/en_US"
    "es/es_ES"
    "fr_FR/fr"
    "de/de_DE_frami"
    "it_IT/it_IT"
    "pt_BR/pt_BR"
    "nl_NL/nl_NL"
    "ru_RU/ru_RU"
)

# Parse args
LANGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --langs)
            shift
            IFS=',' read -ra LANGS <<< "$1"
            ;;
        --prefix)
            shift
            PREFIX="$1"
            ;;
        --help|-h)
            echo "Usage: $0 [--langs es,en,de] [--prefix /path]"
            echo ""
            echo "Compiles hunspell from source and downloads dictionaries."
            echo "Installs to PREFIX (default: ~/.local/share/hunspell-built)"
            echo ""
            echo "Available language codes for --langs:"
            echo "  en  es  fr  de  it  pt  nl  ru  ar  ca  gl  ro  sv  cs"
            echo "  da  el  fi  hu  ko  no  pl  sk  sl  tr  uk  he  id  vi"
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
    shift
done

# Map short lang codes to dictionary paths
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
LANG_MAP[gl]="gl/gl"
LANG_MAP[ro]="ro/ro"
LANG_MAP[sv]="sv_SE/sv_SE"
LANG_MAP[cs]="cs_CZ/cs_CZ"
LANG_MAP[da]="da_DK/da_DK"
LANG_MAP[el]="el_GR/el_GR"
LANG_MAP[fi]="fi_FI/fi_FI"
LANG_MAP[hu]="hu_HU/hu_HU"
LANG_MAP[ko]="ko_KR/ko_KR"
LANG_MAP[no]="no/no"
LANG_MAP[pl]="pl_PL/pl_PL"
LANG_MAP[sk]="sk_SK/sk_SK"
LANG_MAP[sl]="sl_SI/sl_SI"
LANG_MAP[tr]="tr_TR/tr_TR"
LANG_MAP[uk]="uk_UA/uk_UA"
LANG_MAP[he]="he_IL/he_IL"
LANG_MAP[id]="id/id_ID"
LANG_MAP[vi]="vi/vi_VN"

# Build the dict list
DICTS=()
if [[ ${#LANGS[@]} -gt 0 ]]; then
    for lang in "${LANGS[@]}"; do
        if [[ -n "${LANG_MAP[$lang]:-}" ]]; then
            DICTS+=("${LANG_MAP[$lang]}")
        else
            echo "[WARN] Unknown language code: $lang (skipping)" >&2
        fi
    done
else
    DICTS=("${DEFAULT_DICTS[@]}")
fi

echo "============================================================"
echo "  Hunspell Build Script"
echo "  Prefix:  $PREFIX"
echo "  Dicts:   ${#DICTS[@]} languages"
echo "============================================================"

# ── Step 1: Compile hunspell ────────────────────────────────────────
echo ""
echo "[1/3] Compiling hunspell $HUNSPELL_VERSION from source..."

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

if [[ -f "$PREFIX/lib/libhunspell-1.7.so" ]] || [[ -f "$PREFIX/lib/libhunspell-1.7.dylib" ]] || [[ -f "$PREFIX/lib/libhunspell-1.7.dll" ]]; then
    echo "  ✓ libhunspell compiled and installed"
else
    echo "[ERROR] libhunspell not found after build!" >&2
    find "$PREFIX" -name "*.so*" -o -name "*.dylib" -o -name "*.dll" 2>/dev/null
    exit 1
fi

# ── Step 2: Download dictionaries ──────────────────────────────────
echo ""
echo "[2/3] Downloading ${#DICTS[@]} dictionaries from LibreOffice..."

DICT_DIR="$PREFIX/share/hunspell"
mkdir -p "$DICT_DIR"

for dict_path in "${DICTS[@]}"; do
    dir="${dict_path%%/*}"
    name="${dict_path##*/}"

    echo "  Downloading $name (.aff + .dic)..."
    curl -sL "$DICT_REPO/$dir/$name.aff" -o "$DICT_DIR/$name.aff"
    curl -sL "$DICT_REPO/$dir/$name.dic" -o "$DICT_DIR/$name.dic"

    # Verify
    if [[ -f "$DICT_DIR/$name.aff" ]] && [[ -f "$DICT_DIR/$name.dic" ]]; then
        aff_size=$(stat -f%z "$DICT_DIR/$name.aff" 2>/dev/null || stat -c%s "$DICT_DIR/$name.aff" 2>/dev/null || echo 0)
        dic_size=$(stat -f%z "$DICT_DIR/$name.dic" 2>/dev/null || stat -c%s "$DICT_DIR/$name.dic" 2>/dev/null || echo 0)
        echo "    ✓ $name.aff ($(( aff_size / 1024 )) KB) + $name.dic ($(( dic_size / 1024 )) KB)"
    else
        echo "    ✗ Failed to download $name" >&2
    fi
done

# ── Step 3: Summary ────────────────────────────────────────────────
echo ""
echo "[3/3] Installation complete!"
echo ""
echo "  Library:  $PREFIX/lib/"
echo "  Dicts:    $DICT_DIR/"
echo ""
ls -1 "$DICT_DIR"/*.aff 2>/dev/null | sed 's/.*\//  /; s/\.aff$//' | sort
echo ""
echo "Available dictionaries: $(ls -1 "$DICT_DIR"/*.aff 2>/dev/null | wc -l)"
echo ""
echo "To use with grammar_audit.py:"
echo "  export HUNSPELL_PREFIX=$PREFIX"
echo "  python scripts/grammar_audit.py ."
