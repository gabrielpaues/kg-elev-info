#!/usr/bin/env zsh
# Skickar text via iMessage till mottagare i elev.local. Användning: imessage.sh "<text>"
# elev.local (gitignored): MOTTAGARE=<nr1>,<nr2>  (kommaseparerad lista, inget mellanrum)
set -euo pipefail
TEXT="${1:?användning: imessage.sh '<text>'}"
CFG="$HOME/github/kg-elev-info/data/elev.local"
[ -f "$CFG" ] || { echo "Saknar $CFG — skapas av skillen vid första körningen (MOTTAGARE=<nr>[,<nr2>...])" >&2; exit 3; }
TO_LIST=$(grep "^MOTTAGARE=" "$CFG" | head -1 | cut -d= -f2- | tr -d " -")
[ -n "$TO_LIST" ] || { echo "MOTTAGARE ej satt i $CFG" >&2; exit 3; }

osascript - "$TEXT" "$TO_LIST" <<'OSA'
on run {msg, targets}
  set AppleScript's text item delimiters to ","
  set toList to text items of targets
  set AppleScript's text item delimiters to ""
  set results to ""
  tell application "Messages"
    set imsgSvc to missing value
    repeat with s in services
      try
        if (service type of s) as text is "iMessage" then set imsgSvc to s
      end try
    end repeat
    if imsgSvc is missing value then error "ingen iMessage-tjänst hittades"
    repeat with target in toList
      try
        set pal to participant (target as text) of imsgSvc
        send msg to pal
        set results to results & "[OK] " & (target as text) & linefeed
      on error errm
        set results to results & "[FEL] " & (target as text) & " — " & errm & linefeed
      end try
    end repeat
  end tell
  return results
end run
OSA