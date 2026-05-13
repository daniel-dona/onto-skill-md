# Spanish False Positives in codespell

When auditing bilingual (EN/ES) ontology repositories, `codespell` flags many
Spanish words as misspellings. This document lists common false positives and
how to handle them.

## Why This Happens

codespell's dictionary is English-only. Spanish words like `ser`, `fase`, or
`carga` happen to match English typo patterns (e.g. `fase` → `phase`).

## Approach

1. **First pass:** Run codespell with no ignore list. Capture all output.
2. **Review:** Manually separate genuine typos from Spanish false positives.
3. **Build ignore list:** Add confirmed Spanish words to `spell_ignore.txt`.
4. **Second pass:** Re-run with the ignore list for a clean report.

## Common Spanish False Positives by Category

### Verbs & Function Words
`ser`, `te`, `fase`, `historial`, `valide`, `considere`, `momento`

### City/Place Names
`CALLE`, `USERA`, `Flor`, `Soler`, `Carrer`

### Ontology/Domain Terms (Spanish)
`carga`, `composición`, `ocupación`, `intensidad`, `velocidad`, `recurrencia`,
`urbano`, `validada`, `municipio`, `distrito`, `barrio`, `provincia`, `autonomía`

### Infrastructure Terms
`tejidos`, `soterrados`, `compostaje`, `potabilización`, `depuración`,
`desalación`, `descalcificación`, `reciclaje`, `residuos`, `sumideros`,
`desagües`, `rejillas`, `drenaje`, `arquetas`, `señalizaciones`, `pilonas`,
`bolardos`, `marquesinas`, `quioscos`, `jardineras`, `papeleras`,
`ceniceros`, `contenedores`, `cubos`, `balizas`, `toboganes`, `columpios`,
`aparcabicicletas`

### Acronyms & Abbreviations (Not Typos)
`DUM` — Distribución Urbana de Mercancías
`CAF` — Centro de Apoyo a las Familias
`LPR` — License Plate Recognition

### Words in URIs (Not Typos)
Words appearing as part of RDF URI fragments (e.g. `trafico#EquipoTrafico`)
are typically from a reused external namespace and should not be modified.
Only flag them if they appear in `rdfs:label` or `rdfs:comment` text.
