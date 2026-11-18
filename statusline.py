#!/usr/bin/env python3
# statusline.py: Claude Code status line (under the prompt). Model-free: costs no tokens.
# Rule: show only what a person must act on. Normal = one dim line; each problem adds one red line
# that says what to do. Data: ~/.claude/tools/usage-now.json, rewritten every 30 s by watchdog.py.
# Money is USD at API list prices (pricing.py): a size estimate for spotting runaway sessions, not a subscription charge.
import glob, json, os, sys, time, unicodedata
TOOLS = os.path.dirname(os.path.abspath(__file__))
R, Y, D, B, X = '\033[31m', '\033[33m', '\033[2m', '\033[1m', '\033[0m'
def cut(s, w):  # truncate to w terminal columns (CJK = 2)
    out, n = '', 0
    for ch in s:
        c = 2 if unicodedata.east_asian_width(ch) in 'WF' else 1
        if n + c > w: return out + '…'
        out += ch; n += c
    return out
try: me = json.load(sys.stdin).get('session_id', '')
except Exception: me = ''
try:
    s = json.load(open(os.path.join(TOOLS, 'usage-now.json'))); age = time.time() - s['t']
except Exception:
    s, age = None, 1e9
if not s or age > 180:
    pl = glob.glob(os.path.expanduser('~/Library/LaunchAgents/*claude-watchdog*.plist'))
    fix = f'launchctl kickstart -k gui/$(id -u)/{os.path.basename(pl[0])[:-6]}' if pl else f'python3 {TOOLS}/watchdog.py &'
    print(f'{R}用量監看停了 → 執行：{fix}{X}'); sys.exit()
usd = s.get('unit') == 'usd'  # older snapshots were in units; ~3.3 USD per unit
k = 1 if usd else 3.3
OVER = s.get('over_usd', 20)
bk = [v * k for v in s['buckets']]; top = max(max(bk), 0.15)
spark = ''.join('▁▂▃▄▅▆▇█'[min(7, int(v / top * 7.99))] if v > 0 else '·' for v in bk)
tot, last5 = s['total30'] * k, s['last5'] * k
spike = last5 > 1.5 and last5 / 5 > 3 * max(tot / 30, 0.03)
over = spike or tot > OVER
c = R if over else (Y if tot >= OVER / 2 else D)
lines = [f'{c}{"暴增" if spike else "偏高" if tot > OVER else "正常"} · 全機近 30 分 {spark} US${tot:.1f}（門檻 ${OVER:g}，API 價估算）{X}']
if over and s.get('tabs'):
    t = s['tabs'][0]  # the tab to go to: its own session plus all the agents it started
    v = t['usd'] if 'usd' in t else t.get('units', 0) * 3.3
    lines.append(f'{R}{B}最耗的分頁{X}{R} →「{cut(t["doing"] or t["proj"], 24)}」{"（就是這個視窗）" if t["sid"] == me else ""} US${v:.1f} {D}含它開的 agent · {t["proj"]}{X}{R}；用不到就停掉{X}')
todo = {'login': '執行 /login', 'limit': '到 claude.ai/settings/usage 提高上限', 'offline': '檢查網路'}
kname = {'login': '登入失效', 'limit': '用量到上限', 'offline': '連不上網'}
for kind, b in (s.get('blocked') or {}).items():
    names = ', '.join(cut(n, 14) for n in b['who'][:3]) + (f' +{len(b["who"]) - 3}' if len(b['who']) > 3 else '')
    lines.append(f'{R}{B}{kname.get(kind, kind)}{X}{R} → {todo.get(kind, "檢查一下")}  {D}（{names}）{X}')
if s.get('claude_p', 0) > 3:
    lines.append(f'{R}{B}claude -p 同時 {s["claude_p"]} 個{X}{R} → 上限 3 個，停掉多的{X}')
print('\n'.join(lines))
