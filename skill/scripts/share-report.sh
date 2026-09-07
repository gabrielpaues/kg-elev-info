#!/usr/bin/env zsh
# Delar veckorapporten: MD → HTML → PDF (debug-Chrome) → Dropbox (beständig delbar länk).
#   share-report.sh <rapport.md> [utfil-länk.txt]
# Kräver:
#   - Dropbox-app-token i nyckelringen:  security add-generic-password -a $USER -s skola-dropbox -w <TOKEN>
#     (dropbox.com/developers/apps → Create app, scoped: files.content.write + sharing.write)
#   - Debug-Chrome på :9222 (starta med skillens start-chrome.sh om ej körs)

set -euo pipefail
RAPPORT="${1:?användning: share-report.sh <rapport.md>}"
SKILL="$HOME/github/kg-elev-info/skill"
DATA="$HOME/github/kg-elev-info/data"
DROPBOX_PATH="/Skola-Rapporter/rapport-senaste.pdf"
TMP=$(mktemp -d)

# Dropbox: auto-refresh av access-token (refresh-token + app key/secret ligger i nyckelringen)
REFRESH=$(security find-generic-password -s skola-dropbox-refresh -w 2>/dev/null) || {
  echo "INGEN REFRESH-TOKEN i nyckelringen. Gör engångs-OAuth enligt SKILL.md §8."; exit 3; }
KEY=$(security find-generic-password -s skola-dropbox-key -w)
SECRET=$(security find-generic-password -s skola-dropbox-secret -w)
TOKEN_JSON=$(curl -s -X POST https://api.dropboxapi.com/oauth2/token \
  -u "$KEY:$SECRET" -d grant_type=refresh_token -d refresh_token="$REFRESH")
TOKEN=$(echo "$TOKEN_JSON" | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
[ -n "${TOKEN:-}" ] || { echo "REFRESH-FEL: $TOKEN_JSON"; exit 3; }

VECKA=$(python3 - "$RAPPORT" <<'PY'
import re, sys, datetime
t = open(sys.argv[1]).read()
m = re.search(r'Vecka (\d+)', t)
print(m.group(1) if m else datetime.date.today().isocalendar()[1])
PY
)

# 1. HTML
HTML="$TMP/rapport.html"
python3 "$SKILL/scripts/md2html.py" "$RAPPORT" "$HTML" >/dev/null

# 2. PDF via debug-Chrome
if ! curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  "$SKILL/scripts/start-chrome.sh" >/dev/null
fi
IDX=$(node "$SKILL/scripts/cdp.mjs" new "file://$HTML")
sleep 8
node "$SKILL/scripts/cdp.mjs" pdf "$IDX" "$TMP/rapport.pdf" >/dev/null
node "$SKILL/scripts/cdp.mjs" close "$IDX" >/dev/null
[ -s "$TMP/rapport.pdf" ] || { echo "PDF blev tom — se cdp.mjs-pdf-logik"; exit 6; }

# 3. Ladda upp (mode=overwrite → länken består mellan veckor)
UP=$(curl -s -X POST "https://content.dropboxapi.com/2/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Dropbox-API-Arg: {\"path\": \"$DROPBOX_PATH\", \"mode\": \"overwrite\", \"autorename\": false, \"mute\": true}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary "@$TMP/rapport.pdf")
echo "$UP" | grep -q '"size"' || { echo "UPLOAD-FEL: $UP"; exit 4; }

# 4. Delbar länk (skapa; om finns — återanvänd)
LINK=$(curl -s -X POST "https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"path\": \"$DROPBOX_PATH\", \"settings\": {\"requested_visibility\": \"public\"}}")
if echo "$LINK" | grep -q "shared_link_already_exists"; then
  LINK=$(curl -s -X POST "https://api.dropboxapi.com/2/sharing/list_shared_links" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{\"path\": \"$DROPBOX_PATH\", \"direct_only\": true}")
  LURL=$(echo "$LINK" | python3 -c "import json,sys; print(json.load(sys.stdin)['links'][0]['url'])")
else
  LURL=$(echo "$LINK" | python3 -c "import json,sys; print(json.load(sys.stdin)['url'])")
fi
echo "$LURL" | grep -q '^https://' || { echo "LÄNK-FEL: $LINK"; exit 5; }

DL="${LURL//www.dropbox.com/dl.dropboxusercontent.com}"

# 5. Arkivera per vecka (utan länk)
curl -s -X POST "https://content.dropboxapi.com/2/files/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Dropbox-API-Arg: {\"path\": \"/Skola-Rapporter/arkiv/vecka-$VECKA.pdf\", \"mode\": \"overwrite\", \"mute\": true}" \
  -H "Content-Type: application/octet-stream" --data-binary "@$TMP/rapport.pdf" > /dev/null

echo "$LURL" | tee "${2:-$DATA/last-delad-lank.txt}"
echo "direktlänk (renderad): $DL" >&2
