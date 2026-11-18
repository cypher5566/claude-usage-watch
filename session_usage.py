#!/usr/bin/env python3
"""session_usage.py — 近 N 天哪些 Claude Code session 最耗用量（只讀本機紀錄，不呼叫模型、不花錢）。

用法：python3 session_usage.py [--days 7] [--top 15] [--out 報告檔路徑]
- 一個分頁（主 session）＝它自己＋它開的所有 subagent，合併算。
- `claude -p`（紀錄裡 entrypoint=sdk-cli）另外按專案加總，因為通常一次是一整批。
- 金額＝照 Anthropic 官方 API 牌價換算的 USD（pricing.py，按模型、cache 寫入分 5 分鐘／1 小時），
  訂閱制不是這樣收費，只用來比大小、抓異常；% ＝佔這台電腦這段期間總額的比例。
- 已排除 <synthetic> 紀錄，同一則回覆只算一次。
完整報告寫進 --out（預設家目錄的 claude-session-usage.txt），畫面只印重點。
"""
import argparse, collections, datetime as dt, glob, json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pricing import usd
WATCH_TOOLS = ('Agent', 'Task', 'Workflow', 'ScheduleWakeup', 'CronCreate', 'Monitor')

ap = argparse.ArgumentParser()
ap.add_argument('--days', type=float, default=7)
ap.add_argument('--top', type=int, default=15)
ap.add_argument('--out', default=os.path.expanduser('~/claude-session-usage.txt'))
a = ap.parse_args()

cfg = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
ROOT = os.path.join(cfg, 'projects')
since = time.time() - a.days * 86400
since_iso = dt.datetime.fromtimestamp(since, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S')

def ts(s):
    try: return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except Exception: return None

def new():
    return dict(usd=0.0, calls=0, tok=collections.Counter(), agents=set(), entry='', cwd='', start=None, end=None,
                prompts=0, first='', tools=collections.Counter(), skills=collections.Counter(), peak=0, models=collections.Counter())

S = collections.defaultdict(new)
seen = set()
files = [p for p in glob.glob(ROOT + '/*/**/*.jsonl', recursive=True) if os.path.getmtime(p) >= since]
t0 = time.time()
for n, p in enumerate(files, 1):
    rel = p[len(ROOT) + 1:].split('/')
    proj = rel[0]
    if '/subagents/' in p: key, agent = os.path.join(ROOT, proj, rel[1] + '.jsonl'), True
    else: key, agent = p, False
    s = S[key]
    if agent: s['agents'].add(os.path.basename(p))
    try: fh = open(p, encoding='utf-8', errors='replace')
    except OSError: continue
    with fh:
        for l in fh:
            u_line = '"usage"' in l
            usr = '"type":"user"' in l
            if not (u_line or usr or '"tool_use"' in l): continue
            if l[l.find('"timestamp":"') + 13:][:19] < since_iso and '"timestamp":"' in l: continue
            try: d = json.loads(l)
            except Exception: continue
            t = ts(d.get('timestamp', ''))
            if t is None or t < since: continue
            if not agent:
                if not s['entry'] and d.get('entrypoint'): s['entry'] = d['entrypoint']
                if not s['cwd'] and d.get('cwd'): s['cwd'] = d['cwd']
            s['start'] = t if s['start'] is None else min(s['start'], t)
            s['end'] = t if s['end'] is None else max(s['end'], t)
            m = d.get('message') or {}
            c = m.get('content')
            if d.get('type') == 'user' and not agent and not d.get('isMeta'):
                txt = c if isinstance(c, str) else ' '.join(x.get('text', '') for x in (c or []) if isinstance(x, dict) and x.get('type') == 'text')
                txt = ' '.join((txt or '').split())
                if txt and not txt.startswith('<') and not any(isinstance(x, dict) and x.get('type') == 'tool_result' for x in (c if isinstance(c, list) else [])):
                    s['prompts'] += 1
                    if not s['first']: s['first'] = txt[:70]
            if isinstance(c, list):
                for x in c:
                    if isinstance(x, dict) and x.get('type') == 'tool_use':
                        name = x.get('name', '')
                        if name in WATCH_TOOLS: s['tools'][name] += 1
                        if name == 'Skill': s['skills'][str((x.get('input') or {}).get('skill', ''))[:30]] += 1
            u = m.get('usage')
            if not u or m.get('model') == '<synthetic>': continue
            k = (m.get('id'), d.get('requestId'))
            if k[0]:
                if k in seen: continue
                seen.add(k)
            model = m.get('model', '')
            i, cw, cr, o = (u.get('input_tokens', 0) or 0, u.get('cache_creation_input_tokens', 0) or 0,
                            u.get('cache_read_input_tokens', 0) or 0, u.get('output_tokens', 0) or 0)
            s['usd'] += usd(model, u)
            s['calls'] += 1
            s['tok'].update(i=i, cw=cw, cr=cr, o=o)
            s['peak'] = max(s['peak'], i + cw + cr)
            s['models'][model.replace('claude-', '')[:16]] += 1
    if n % 300 == 0: print(f'  掃描中 {n}/{len(files)} 檔…', file=sys.stderr)

S = {k: v for k, v in S.items() if v['calls']}
total = sum(v['usd'] for v in S.values()) or 1
loc = lambda t: dt.datetime.fromtimestamp(t).strftime('%m/%d %H:%M') if t else '?'
def projname(k, s):
    return os.path.basename(s['cwd']) if s['cwd'] else k[len(ROOT) + 1:].split('/')[0][-24:]
def flags(s):
    out = []
    dur = (s['end'] - s['start']) / 3600 if s['start'] else 0
    if len(s['agents']) >= 20: out.append(f'開了 {len(s["agents"])} 個 agent')
    if s['tools'].get('Workflow'): out.append('跑了 Workflow')
    if s['tools'].get('ScheduleWakeup') or s['tools'].get('CronCreate'): out.append('有排程／loop')
    if s['tools'].get('Monitor'): out.append('有 Monitor')
    if s['peak'] >= 300_000: out.append(f'context 最高 {s["peak"] // 1000}k')
    if s['prompts'] and s['calls'] / s['prompts'] >= 150: out.append(f'每句指令平均 {s["calls"] // s["prompts"]} 次呼叫')
    if dur >= 12: out.append(f'持續 {dur:.0f} 小時')
    return out

main = sorted(((k, v) for k, v in S.items() if v['entry'] != 'sdk-cli'), key=lambda x: -x[1]['usd'])
batch = collections.defaultdict(lambda: [0, 0.0, 0])
for k, v in S.items():
    if v['entry'] == 'sdk-cli':
        b = batch[projname(k, v)]; b[0] += 1; b[1] += v['usd']; b[2] += v['calls']
p_units = sum(b[1] for b in batch.values())

L = []
L.append(f'近 {a.days:g} 天 Claude Code 用量排行（本機，{loc(since)} 起）')
L.append(f'合計 US${total:,.0f}（照官方 API 牌價換算，訂閱制不這樣收費，只用來比大小）；% ＝佔合計的比例')
L.append(f'互動分頁 {len(main)} 個　claude -p {sum(b[0] for b in batch.values())} 次（共佔 {100 * p_units / total:.0f}%）')
L.append('')
L.append('【最耗的分頁（含它開的 agent）】')
for r, (k, v) in enumerate(main, 1):
    if r > max(a.top, 40): break
    sk = ', '.join(f'{n}×{c}' for n, c in v['skills'].most_common(3))
    L.append(f'{r:2}. US${v["usd"]:7,.0f} {100 * v["usd"] / total:5.1f}%  {projname(k, v)}  {loc(v["start"])}–{loc(v["end"])}  '
             f'呼叫 {v["calls"]}、agent {len(v["agents"])}、你打的指令 {v["prompts"]}')
    L.append(f'      第一句：{v["first"] or "（無）"}')
    if sk: L.append(f'      skill：{sk}')
    fl = flags(v)
    if fl: L.append(f'      ⚠ {"；".join(fl)}')
    L.append(f'      session：{os.path.basename(k)[:-6]}')
L.append('')
L.append('【claude -p 按專案加總】')
for name, (cnt, u, calls) in sorted(batch.items(), key=lambda x: -x[1][1])[:15]:
    L.append(f'  US${u:7,.0f} {100 * u / total:5.1f}%  {name}  {cnt} 次、呼叫 {calls}')
L.append('')
L.append(f'（掃描 {len(files)} 個檔、{time.time() - t0:.0f} 秒）')
L.append('看法：前幾名若有 ⚠，多半就是背景燒掉的那個。分頁還開著且不需要就關掉；想知道它在做什麼，用 claude --resume <session> 打開看。')

open(a.out, 'w').write('\n'.join(L) + '\n')
short = L[:5]
cnt = 0
for line in L[5:]:
    if line.startswith('【claude -p'): break
    if line[:3].strip().rstrip('.').isdigit():
        cnt += 1
        if cnt > a.top: break
    short.append(line)
print('\n'.join(short).rstrip())
print(f'\n完整報告：{a.out}')
