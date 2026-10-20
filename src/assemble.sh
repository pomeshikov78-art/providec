#!/bin/sh
# Сборка ais_providets.html из src/shell.html + src/app.js + src/server.js + src/tail.html
cd "$(dirname "$0")/.." || exit 1
OUT="${1:-ais_providets.html}"
node --check src/app.js || { echo "SYNTAX FAIL app.js"; exit 1; }
node --check src/server.js || { echo "SYNTAX FAIL server.js"; exit 1; }
cat src/shell.html > "$OUT"
printf '<script>' >> "$OUT"
cat src/app.js >> "$OUT"
printf '\n' >> "$OUT"
cat src/server.js >> "$OUT"
cat src/tail.html >> "$OUT"
wc -c "$OUT"
