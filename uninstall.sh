#!/bin/bash
# 移除 Claude Code 用量監看：停掉背景程式、拿掉狀態列設定、刪掉程式資料夾。
set -uo pipefail
CFG="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
LABEL="local.claude-watchdog"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
python3 - "$CFG/settings.json" <<'EOF'
import json, os, sys
p = sys.argv[1]
if os.path.exists(p):
    s = json.load(open(p))
    if 'usage-watch/statusline.py' in (s.get('statusLine') or {}).get('command', ''):
        del s['statusLine']
        with open(p, 'w') as f: json.dump(s, f, indent=2, ensure_ascii=False); f.write('\n')
EOF
rm -rf "$CFG/usage-watch"
echo "✓ 已移除（若之前有備份的舊狀態列，在 $CFG/settings.json.bak-* 裡）"
