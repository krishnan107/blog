import os, json, datetime, requests, feedparser, re, base64

GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
TG_TOKEN       = os.environ['TELEGRAM_TOKEN']
TG_CHAT_ID     = os.environ['TELEGRAM_CHAT_ID']
GH_TOKEN       = os.environ['GH_TOKEN']
OWNER, REPO    = 'krishnan107', 'blog'

RSS = [
    ('sports',     'https://feeds.bbci.co.uk/sport/rss.xml'),
    ('world',      'https://feeds.bbci.co.uk/news/world/rss.xml'),
    ('technology', 'https://feeds.bbci.co.uk/news/technology/rss.xml'),
    ('science',    'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'),
]

def get_news():
    topic, url = RSS[datetime.date.today().weekday() % len(RSS)]
    feed = feedparser.parse(url)
    return topic, ['- ' + e.get('title','') + ': ' + e.get('summary','')[:200] for e in feed.entries[:5]]

def gemini(prompt):
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}'
    r = requests.post(url, json={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.8,'maxOutputTokens':2048}}, timeout=60)
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text']

def push_draft(filename, content):
    path, h = f'_drafts/{filename}', {'Authorization':f'token {GH_TOKEN}','Accept':'application/vnd.github.v3+json','Content-Type':'application/json'}
    url = f'https://api.github.com/repos/{OWNER}/{REPO}/contents/{path}'
    ex = requests.get(url, headers=h)
    body = {'message':f'Auto-draft: {filename}','content':base64.b64encode(content.encode()).decode()}
    if ex.status_code == 200: body['sha'] = ex.json()['sha']
    return requests.put(url, headers=h, json=body).status_code in (200,201)

def notify(title, filename):
    requests.post(f'https://api.telegram.org/bot{TG_TOKEN}/sendMessage', json={
        'chat_id': TG_CHAT_ID,
        'text': f'New Blog Post Ready\n\nTitle: {title}\n\nTap Publish Now to make it live.',
        'reply_markup':{'inline_keyboard':[[
            {'text':'Publish Now','callback_data':f'publish:{filename}'},
            {'text':'Reject','callback_data':f'reject:{filename}'}
        ]]}
    })

today = datetime.date.today()
topic, stories = get_news()
print(f'Topic: {topic}')

prompt = f"""Today is {today.strftime('%B %d, %Y')}. Write a 600-800 word blog post about one of these {topic} stories:
{chr(10).join(stories)}

Pick the most interesting story. Use ## headings. Engaging style. No em-dashes, no special Unicode.
Return ONLY valid JSON: {{"title":"Title Here","slug":"url-slug","content":"full markdown body"}}"""

raw = gemini(prompt).strip()
if raw.startswith('```'): raw = re.sub(r'^```[a-z]*\n?','',raw); raw = re.sub(r'\n?```$','',raw)
post = json.loads(raw)

filename = f"{today.strftime('%Y-%m-%d')}-{post['slug']}.md"
content = f"---\nlayout: post\ntitle: \"{post['title']}\"\ndate: {today}\ncategories: [{topic}]\nauthor: Anil\n---\n\n{post['content']}"

print(f'Pushing {filename}')
push_draft(filename, content)
notify(post['title'], filename)
print('Done!')
