#!/bin/bash
# Claude Code 用量監看：安裝或更新。重跑一次就是更新。只讀本機紀錄，不呼叫模型、不花錢。
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CFG/usage-watch"
LABEL="local.claude-watchdog"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3 || true)"
[ -n "$PY" ] || { echo "找不到 python3。請先在終端機執行 xcode-select --install，裝好後再跑一次。"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' || { echo "python3 版本太舊（需要 3.8 以上）"; exit 1; }
[ -d "$CFG/projects" ] || { echo "找不到 $CFG/projects，這台電腦好像還沒用過 Claude Code。"; exit 1; }

mkdir -p "$DEST" "$HOME/Library/LaunchAgents"
cp "$SRC"/pricing.py "$SRC"/session_usage.py "$SRC"/watchdog.py "$SRC"/statusline.py "$DEST"/
echo "✓ 程式放到 $DEST"

# 1) 狀態列：寫進 settings.json，其他設定不動；原本有別的狀態列會先備份
"$PY" - "$CFG/settings.json" "$PY $DEST/statusline.py" <<'EOF'
import json, os, sys, time, shutil
p, cmd = sys.argv[1], sys.argv[2]
s = {}
if os.path.exists(p):
    try: s = json.load(open(p))
    except Exception: sys.exit(f'{p} 不是合法 JSON，沒有改它；請手動把 statusLine 設成：{cmd}')
old = (s.get('statusLine') or {}).get('command', '')
if old and 'usage-watch/statusline.py' not in old:
    b = p + time.strftime('.bak-%Y%m%d-%H%M%S'); shutil.copy(p, b)
    print(f'  原本的狀態列（{old}）已備份到 {b}')
s['statusLine'] = {'type': 'command', 'command': cmd, 'refreshInterval': 30}
tmp = p + '.tmp'
with open(tmp, 'w') as f: json.dump(s, f, indent=2, ensure_ascii=False); f.write('\n')
os.replace(tmp, p)
EOF
echo "✓ 狀態列已設定（下次開 Claude Code 生效）"

# 2) 背景監看：開機自動啟動，每 30 秒更新一次
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DEST/watchdog.py</string></array>
  <key>EnvironmentVariables</key><dict><key>CLAUDE_CONFIG_DIR</key><string>$CFG</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>Nice</key><integer>10</integer>
  <key>StandardErrorPath</key><string>$DEST/watchdog.err</string>
  <key>StandardOutPath</key><string>/dev/null</string>
</dict></plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
for _ in $(seq 1 60); do [ -f "$DEST/usage-now.json" ] && break; sleep 1; done
[ -f "$DEST/usage-now.json" ] && echo "✓ 背景監看已啟動" || echo "⚠ 背景監看 60 秒內沒有產出，請看 $DEST/watchdog.err"

# 3) 馬上看一次近 7 天
echo
"$PY" "$DEST/session_usage.py" --days 7 --top 5 2>/dev/null
echo
echo "之後隨時重看：python3 $DEST/session_usage.py"
