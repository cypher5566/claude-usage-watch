# pricing.py: one Claude API call's cost in USD, at Anthropic's published API list prices.
# Shared by session_usage.py, watchdog.py, usage.py. Subscriptions don't bill per call, so treat this
# as an "API price estimate" for comparing sizes, not as a charge. Prices: claude-api skill, 2026-11-03.
# Per 1M tokens: (input, output, cache read, cache write 5-minute, cache write 1-hour).
PRICES = [  # first substring match wins, so more specific names go first
    ('opus-5-5',   (4.0, 20.0, 0.20, 5.0, 8.0)),
    ('sonnet-5-5', (2.0, 10.0, 0.10, 2.5, 4.0)),
    ('haiku-5-5',  (0.10, 0.50, 0.01, 0.125, 0.20)),   # prompt <= 100K tokens; above that x5 (see usd)
    ('fable-5-2',  (8.0, 40.0, 0.20, 10.0, 16.0)),
    ('mythos-5-2', (8.0, 40.0, 0.20, 10.0, 16.0)),
    ('fable-5-1',  (10.0, 50.0, 0.25, 12.5, 20.0)),
    ('mythos-5-1', (10.0, 50.0, 0.25, 12.5, 20.0)),
    ('opus',       (5.0, 25.0, 0.50, 6.25, 10.0)),     # Opus 5 / 4.x
    ('sonnet-5',   (2.0, 10.0, 0.20, 2.5, 4.0)),
    ('sonnet',     (3.0, 15.0, 0.30, 3.75, 6.0)),      # Sonnet 4.x
    ('haiku',      (1.0, 5.0, 0.10, 1.25, 2.0)),       # Haiku 4.5
    ('fable',      (10.0, 50.0, 0.25, 12.5, 20.0)),
]
DEFAULT = PRICES[0][1]  # unknown model: price it like Opus 5.5 rather than drop it

def rates(model):
    m = model or ''
    return next((r for k, r in PRICES if k in m), DEFAULT)

def usd(model, u):
    """USD for one API reply's `usage` dict."""
    g = lambda k: u.get(k, 0) or 0
    i, o, cr, cw = g('input_tokens'), g('output_tokens'), g('cache_read_input_tokens'), g('cache_creation_input_tokens')
    w1 = min(cw, (u.get('cache_creation') or {}).get('ephemeral_1h_input_tokens', 0) or 0)
    pi, po, pr, p5, p1 = rates(model)
    v = (i * pi + o * po + cr * pr + (cw - w1) * p5 + w1 * p1) / 1e6
    if 'haiku-5-5' in (model or '') and i + cr + cw > 100_000: v *= 5
    return v
