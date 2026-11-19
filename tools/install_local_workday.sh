#!/bin/bash
# Installs the tracker's Workday reader on this Mac: it runs every 30 minutes in the background
# while the Mac is awake and uploads what it finds to the project's "workday-feed" release.
#
#   Install:    curl -fsSL https://raw.githubusercontent.com/gbv229/wm-internship-tracker/main/tools/install_local_workday.sh | bash
#   Uninstall:  curl -fsSL https://raw.githubusercontent.com/gbv229/wm-internship-tracker/main/tools/install_local_workday.sh | bash -s uninstall
set -euo pipefail

REPO="gbv229/wm-internship-tracker"
LABEL="com.wm-internship-tracker.workday"
DIR="$HOME/Library/Application Support/wm-tracker"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
RAW="https://raw.githubusercontent.com/$REPO/main/tools/local_workday.py"

if [ "${1:-}" = "uninstall" ]; then
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  rm -f "$PLIST"
  rm -rf "$DIR"
  security delete-generic-password -s wm-tracker-github >/dev/null 2>&1 || true
  echo "Removed the Workday reader, its files and its GitHub key."
  exit 0
fi

PY=""
for p in /usr/bin/python3 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$p" ] && "$p" -c "import sys; assert sys.version_info >= (3, 8)" 2>/dev/null; then PY="$p"; break; fi
done
if [ -z "$PY" ]; then
  echo "Python 3 isn't installed. Run:  xcode-select --install   then run this installer again."
  exit 1
fi

mkdir -p "$DIR" "$HOME/Library/LaunchAgents"
curl -fsSL "$RAW" -o "$DIR/local_workday.py"

if ! security find-generic-password -s wm-tracker-github >/dev/null 2>&1; then
  ok=""
  for attempt in 1 2 3; do
    echo
    echo "Paste the GitHub key now (Cmd+V). Nothing will show on screen — that's normal. Then press Return:"
    read -rs TOKEN < /dev/tty
    TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
    echo
    if [ -z "$TOKEN" ]; then
      echo "Nothing was pasted. Copy the key from GitHub, then paste it here before pressing Return."
      continue
    fi
    code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "https://api.github.com/repos/$REPO")
    if [ "$code" = "200" ]; then ok=1; break; fi
    echo "That key didn't work (GitHub said $code). Check it has access to $REPO with Contents: Read and write."
  done
  if [ -z "$ok" ]; then echo "Stopping. Run the install command again when you have the key."; exit 1; fi
  security add-generic-password -U -s wm-tracker-github -a "$USER" -w "$TOKEN"
  unset TOKEN
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$DIR/local_workday.py</string></array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>LowPriorityIO</key><true/>
  <key>Nice</key><integer>10</integer>
  <key>StandardOutPath</key><string>$DIR/log.txt</string>
  <key>StandardErrorPath</key><string>$DIR/log.txt</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo
echo "Installed. It's doing its first check now and then runs every 30 minutes while your Mac is awake."
echo "Log: $DIR/log.txt"
