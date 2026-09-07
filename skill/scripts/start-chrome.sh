#!/usr/bin/env zsh
# Startar debug-Chrome med isolerad profil (cookies + BankID-sessioner ligger kvar mellan körningar).
# Chrome 136+ blockerar --remote-debugging-port på defaultprofilen — därför separat user-data-dir.
PROFILE="$HOME/github/kg-elev-info/chrome-profile"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1; then
  echo "debug-Chrome körs redan på :9222"
else
  open -na "Google Chrome" --args --user-data-dir="$PROFILE" --remote-debugging-port=9222 --no-first-run --no-default-browser-check
  for i in {1..20}; do
    curl -s --max-time 2 http://127.0.0.1:9222/json/version >/dev/null 2>&1 && { echo "uppe på :9222"; break; }
    sleep 0.5
  done
fi
