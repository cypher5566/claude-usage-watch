# watchdog.py: machine-wide, model-free usage watchdog (runs as a launchd agent, see install.sh).
# Every 30 s: writes ~/.claude/tools/usage-now.json (read by statusline.py under the prompt) and,
# on a NEW threshold breach, appends to watchdog.log and shows a macOS notification.
# Alerts (context length is handled by autoCompactWindow in settings.json): >3 `claude -p` running; load1 > 20;
# > US$20 (API price estimate, pricing.py) in a rolling 30 min machine-wide; a non-lean `claude -p`.
import glob, json, os, re, subprocess, sys, time, collections, datetime
TOOLS = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, TOOLS)
from pricing import usd
CFG = os.environ.get('CLAUDE_CONFIG_DIR') or os.path.expanduser('~/.claude')
ROOT = os.path.join(CFG, 'projects')
LOG = os.path.join(TOOLS, 'watchdog.log')
SNAP = os.path.join(TOOLS, 'usage-now.json')
OVER_USD = 20  # rolling 30 min, whole machine; 7-day check 11/18: over this ~6% of the time
HOME_DIR = os.path.expanduser('~').replace('/', '-')  # how Claude Code names project folders: /Users/a/x -> -Users-a-x
alerted, offs, last_ctx, labels, seen = set(), {}, {}, {}, {}
titles, prompts, cwds = {}, collections.defaultdict(lambda: collections.deque(maxlen=3)), {}
events = collections.deque()  # (epoch, transcript path, usd)
last_err, last_ok = {}, {}  # per transcript: (epoch, kind, text) of the latest API error / epoch of the latest real reply
QUIET = True

def alert(msg):
    if QUIET: return
    line = time.strftime('%m-%d %H:%M ') + msg
    print(line, flush=True)
    with open(LOG, 'a') as f: f.write(line + '\n')
    subprocess.run(['osascript', '-e', f'display notification "{msg[:180]}" with title "Claude 用量警示"'], capture_output=True)

def doing(p):  # the terminal tab name: Claude Code titles the tab with the session's latest ai-title
    if '/subagents/' in p: return tab(os.path.dirname(os.path.dirname(p)) + '.jsonl')
    return tab(p)
def tab(p):
    pr = prompts.get(p)
    return titles.get(p) or (pr[-1][:40] if pr else '') or labels.get(p, '')

def projname(p):  # the folder the session runs in; falls back to the transcript folder name minus the home prefix
    main = os.path.dirname(os.path.dirname(p)) + '.jsonl' if '/subagents/' in p else p
    c = cwds.get(main) or cwds.get(p)
    if c: return os.path.basename(c.rstrip('/')) or c
    proj = p[len(ROOT)+1:].split('/')[0]
    return proj[len(HOME_DIR):].lstrip('-') or proj if proj.startswith(HOME_DIR) else proj

def label(p):
    short = projname(p)
    if '/subagents/' in p:
        a = re.sub(r'^agent-a?', '', os.path.basename(p)[:-6])
        a = re.sub(r'-[0-9a-f]{12,}$', '', a)
        return a[:22]
    return short[:18] + '·' + os.path.basename(p)[:4]

def ts(s):
    try: return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()
    except Exception: return None

def scan():
    now = time.time()
    for p in set(glob.glob(ROOT + '/*/**/*.jsonl', recursive=True)):
        try: st = os.stat(p)
        except OSError: continue
        if now - st.st_mtime > 1800: continue
        o = offs.get(p)
        if o is None: o = max(0, st.st_size - 3_000_000)
        if o > st.st_size: o = 0
        with open(p, 'rb') as f:
            f.seek(o); data = f.read()
        data = data[:data.rfind(b'\n')+1]; offs[p] = o + len(data)
        labels[p] = label(p)
        for l in data.split(b'\n'):
            if b'"ai-title"' in l or b'"custom-title"' in l or (b'"type":"user"' in l and b'tool_result' not in l):
                try: d = json.loads(l)
                except Exception: continue
                if d.get('cwd'): cwds[p] = cwds[os.path.dirname(os.path.dirname(p)) + '.jsonl' if '/subagents/' in p else p] = d['cwd']
                if d.get('type') in ('ai-title', 'custom-title'): titles[p] = d.get('customTitle') or d.get('aiTitle') or titles.get(p, '')
                elif d.get('type') == 'user' and not d.get('isMeta'):
                    c = (d.get('message') or {}).get('content')
                    if isinstance(c, list): c = ' '.join(x.get('text', '') for x in c if isinstance(x, dict) and x.get('type') == 'text')
                    c = (c or '').strip()
                    if len(c) >= 8 and not c.startswith('<'): prompts[p].append(' '.join(c.split())[:200])
                continue
            if b'"isApiErrorMessage":true' in l:
                try: d = json.loads(l)
                except Exception: continue
                c = (d.get('message') or {}).get('content'); e = d.get('error')
                c = ' '.join(x.get('text', '') for x in c if isinstance(x, dict)) if isinstance(c, list) else str(c or '')
                kind = ('login' if e == 'authentication_failed' else 'limit' if e == 'rate_limit'
                        else 'offline' if 'ENOTFOUND' in c or "Can't reach" in c else None)
                t = ts(d.get('timestamp', ''))
                if kind and t: last_err[p] = (t, kind, c[:90])
                continue
            if b'"usage"' not in l: continue
            try:
                d = json.loads(l); m = d['message']; u = m['usage']
            except Exception: continue
            if m.get('model') == '<synthetic>': continue
            if d.get('cwd') and p not in cwds: cwds[p] = d['cwd']
            ctx = u.get('input_tokens', 0) + u.get('cache_creation_input_tokens', 0) + u.get('cache_read_input_tokens', 0)
            last_ctx[p] = ctx
            t = ts(d.get('timestamp', ''))
            if t: last_ok[p] = max(last_ok.get(p, 0), t)
            k = (m.get('id'), d.get('requestId'))
            if t is None or now - t > 1800 or (k[0] and k in seen): continue
            if k[0]: seen[k] = t
            events.append((t, p, usd(m.get('model'), u)))
    while events and now - events[0][0] > 1800: events.popleft()
    for k in [k for k, t in seen.items() if now - t > 2400]: del seen[k]
    for p in [p for p in last_ctx if p not in offs or now - os.path.getmtime(p) > 1800]:
        last_ctx.pop(p, None)
    # alerts
    s = sum(v for _, _, v in events)
    key = ('spend', int(now // 1800))
    if s > OVER_USD and key not in alerted:
        alerted.add(key); alert(f'全機近 30 分鐘 US${s:.0f}（API 價估算，門檻 US${OVER_USD}）')
    ps = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True).stdout.splitlines()
    cp = [l for l in ps if ' -p ' in l + ' ' and l.split(None, 1)[-1].split()[0].endswith('claude')]
    n = len(cp); load = os.getloadavg()[0]
    k2 = ('proc', int(now // 600))
    if (n > 3 or load > 20) and k2 not in alerted:
        alerted.add(k2); alert(f'claude -p 同時 {n} 個、負載 {load:.1f}')
    for l in cp:
        pid = l.split()[0]
        if ('--setting-sources' not in l or '--strict-mcp-config' not in l) and ('lean', pid) not in alerted:
            alerted.add(('lean', pid)); alert(f'claude -p 沒加精簡旗標（每次多約 45k token）pid={pid}: {l.split(None,1)[1][:90]}')
    # snapshot for the status line
    buckets = [0.0]*30; by = collections.Counter()
    for t, pp, v in events:
        i = int((now - t) // 60)
        if 0 <= i < 30: buckets[29 - i] += v
        by[pp] += v
    big = max(last_ctx.items(), key=lambda x: x[1], default=(None, 0))
    tabs_by = collections.Counter()  # a tab's main session + all its agents, keyed by the main transcript
    for pp, v in by.items(): tabs_by[os.path.dirname(os.path.dirname(pp)) + '.jsonl' if '/subagents/' in pp else pp] += v
    def who(pp):
        proj = projname(pp)
        sid = pp[len(ROOT)+1:].split('/')[1][:36]
        return dict(doing=doing(pp), agent_name=labels.get(pp, '') if '/subagents/' in pp else '', proj=proj, sid=sid, agent='/subagents/' in pp, ctx=last_ctx.get(pp, 0))
    snap = dict(t=now, unit='usd', over_usd=OVER_USD, total30=round(s, 3), last5=round(sum(buckets[-5:]), 3), buckets=[round(b, 3) for b in buckets],
                top=[dict(who(k), usd=round(v, 2)) for k, v in by.most_common(3)],
                tabs=[dict(who(k), usd=round(v, 2)) for k, v in tabs_by.most_common(3)],
                maxctx=(who(big[0]) if big[0] else None), claude_p=n, load=round(load, 1))
    # sessions stuck on something only a person can fix (login, spend limit, no internet)
    blocked = {}
    for pp, (t, kind, txt) in last_err.items():
        if now - t < 900 and t > last_ok.get(pp, 0):
            blocked.setdefault(kind, dict(text=txt, who=[]))['who'].append(who(pp)['doing'] or labels.get(pp, ''))
    snap['blocked'] = blocked
    tmp = SNAP + '.tmp'
    with open(tmp, 'w') as f: json.dump(snap, f)
    os.replace(tmp, SNAP)

scan()          # baseline: fills the 30-min window, records known breaches without alerting
QUIET = False
while True:
    time.sleep(30)
    try: scan()
    except Exception as e:
        with open(LOG, 'a') as f: f.write(time.strftime('%m-%d %H:%M ') + f'scan error: {e!r}\n')
