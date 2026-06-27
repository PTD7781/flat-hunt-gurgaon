"""
Daily scrape + HTML generation script.
Runs in GitHub Actions — reads APIFY_TOKEN from environment.
Loads all_posts.json, fetches new posts, prepends them, rebuilds index.html.
"""

import urllib.request, json, time, ssl, re, os, base64
from datetime import datetime
from pathlib import Path

SSL_CTX = ssl.create_default_context()
TOKEN = os.environ['APIFY_TOKEN']
HEADERS = {'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'}

SEARCHES = [
    "female flatmate gurgaon",
    "female replacement flat gurgaon",
]

# ── Apify helpers ─────────────────────────────────────────────────────────────

def apify_post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(f'https://api.apify.com/v2{path}', data=data, headers=HEADERS, method='POST')
    with urllib.request.urlopen(req, context=SSL_CTX) as r:
        return json.loads(r.read())

def apify_get(path):
    req = urllib.request.Request(f'https://api.apify.com/v2{path}', headers=HEADERS)
    with urllib.request.urlopen(req, context=SSL_CTX) as r:
        return json.loads(r.read())

# ── Load existing posts ───────────────────────────────────────────────────────

all_posts_file = Path('all_posts.json')
existing = json.loads(all_posts_file.read_text()) if all_posts_file.exists() else []
existing_ids = {p.get('post_id') for p in existing}
print(f'Existing posts: {len(existing)}')

# ── Scrape ────────────────────────────────────────────────────────────────────

new_posts = []

for query in SEARCHES:
    print(f'\nSearching: "{query}"')
    result = apify_post('/acts/l6CUZt8H0214D3I0N/runs', {
        "query": query,
        "max_posts": 25,
        "recent_posts": True,
        "search_type": "posts",
        "proxyConfiguration": {
            "useApifyProxy": True,
            "apifyProxyGroups": ["RESIDENTIAL"]
        }
    })
    RUN_ID = result['data']['id']
    print(f'Run ID: {RUN_ID}')

    for i in range(36):
        time.sleep(10)
        status = apify_get(f'/actor-runs/{RUN_ID}')['data']['status']
        print(f'  [{i*10}s] {status}')
        if status in ('SUCCEEDED', 'FAILED', 'ABORTED', 'TIMED-OUT'):
            break

    items = apify_get(f'/actor-runs/{RUN_ID}/dataset/items?limit=50')
    fresh = [p for p in items if p.get('post_id') and not p.get('error') and p['post_id'] not in existing_ids]
    print(f'  {len(fresh)} new posts')
    new_posts.extend(fresh)
    existing_ids.update(p['post_id'] for p in fresh)

# Deduplicate new posts
seen, deduped_new = set(), []
for p in new_posts:
    if p['post_id'] not in seen:
        seen.add(p['post_id'])
        deduped_new.append(p)

print(f'\n{len(deduped_new)} unique new posts')

# Merge: new first, then existing, sort by timestamp desc
all_posts = deduped_new + existing
all_posts.sort(key=lambda p: int(p.get('timestamp') or 0), reverse=True)
all_posts_file.write_text(json.dumps(all_posts, indent=2))
print(f'Total posts: {len(all_posts)}')

# ── HTML generation ───────────────────────────────────────────────────────────

def summarize(text, max_chars=300):
    if not text: return 'No text content.'
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text if len(text) <= max_chars else text[:max_chars].rsplit(' ', 1)[0] + '…'

def format_ts(ts):
    if not ts: return ''
    try:
        return datetime.fromtimestamp(int(ts)).strftime('%b %d, %Y')
    except Exception:
        return str(ts)[:10]

def build_card(p):
    img_url = p.get('image')
    if not img_url:
        album = p.get('album_preview') or []
        if album and isinstance(album[0], dict):
            img_url = album[0].get('image_file_uri')

    img = '<img src="{}" alt="" loading="lazy"/>'.format(img_url) if img_url else ''
    author = p.get('author')
    if isinstance(author, dict): author = author.get('name', 'Anonymous')
    author = author or 'Anonymous'
    group = p.get('associated_group') or {}
    group_name = group.get('name', '') if isinstance(group, dict) else ''
    ts_fmt = format_ts(p.get('timestamp'))

    return '''    <div class="card">
      {img}
      <div class="card-body">
        <div class="author">{author}</div>
        <p class="summary">{summary}</p>
        <div class="meta">
          <span>&#128077; {reactions}</span>
          <span>&#128172; {comments}</span>
          {group}
          {ts}
        </div>
        <a class="btn" href="{url}" target="_blank" rel="noopener">View Post &#8594;</a>
      </div>
    </div>'''.format(
        img=img, author=author,
        summary=summarize(p.get('message') or ''),
        reactions=p.get('reactions_count', 0),
        comments=p.get('comments_count', 0),
        group='<span class="group">{}</span>'.format(group_name) if group_name else '',
        ts='<span class="date">{}</span>'.format(ts_fmt) if ts_fmt else '',
        url=p.get('url', '#'),
    )

cards = '\n'.join(build_card(p) for p in all_posts)
date_str = datetime.now().strftime('%B %d, %Y')

html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Flat Hunt Gurgaon (Female)</title>
  <style>
    *,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f0f2f5;color:#1c1e21;padding:32px 16px}}
    h1{{text-align:center;font-size:1.6rem;margin-bottom:4px;color:#1877f2}}
    .sub{{text-align:center;color:#65676b;font-size:.85rem;margin-bottom:28px}}
    .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:18px;max-width:1140px;margin:0 auto}}
    .card{{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.1);overflow:hidden;display:flex;flex-direction:column;transition:transform .15s,box-shadow .15s}}
    .card:hover{{transform:translateY(-3px);box-shadow:0 6px 20px rgba(0,0,0,.13)}}
    .card img{{width:100%;height:180px;object-fit:cover}}
    .card-body{{padding:14px;display:flex;flex-direction:column;gap:8px;flex:1}}
    .author{{font-size:.8rem;font-weight:600;color:#1877f2;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .summary{{font-size:.88rem;line-height:1.6;flex:1;white-space:pre-wrap}}
    .meta{{display:flex;gap:8px;font-size:.75rem;color:#65676b;flex-wrap:wrap;align-items:center}}
    .group{{background:#e7f3ff;color:#1877f2;padding:2px 8px;border-radius:20px;font-size:.72rem;font-weight:500;max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
    .date{{color:#aaa;font-size:.72rem}}
    .btn{{display:block;background:#1877f2;color:#fff;text-decoration:none;padding:9px 0;border-radius:8px;font-size:.85rem;font-weight:600;text-align:center;margin-top:4px}}
    .btn:hover{{background:#166fe5}}
  </style>
</head>
<body>
  <h1>&#127968; Flat Hunt &mdash; Gurgaon (Female)</h1>
  <p class="sub">{count} posts &middot; Last updated {date}</p>
  <div class="grid">
{cards}
  </div>
</body>
</html>""".format(count=len(all_posts), date=date_str, cards=cards)

Path('index.html').write_text(html, encoding='utf-8')
print('index.html rebuilt.')
