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
    try:
        feed = feedparser.parse(url)
        stories = ['- ' + e.get('title','') + ': ' + e.get('summary','')[:200] for e in feed.entries[:5]]
    except Exception as e:
        print(f'RSS error: {e}')
        stories = ['Top news today']
    return topic, stories

def call_gemini(prompt):
    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + GEMINI_API_KEY
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.8, 'maxOutputTokens': 2048}
    }
    r = requests.post(url, json=payload, timeout=60)
    print('Gemini status:', r.status_code)
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text']

def push_draft(filename, content):
    path = '_drafts/' + filename
    url = 'https://api.github.com/repos/' + OWNER + '/' + REPO + '/contents/' + path
    headers = {
        'Authorization': 'token ' + GH_TOKEN,
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    ex = requests.get(url, headers=headers)
    body = {
        'message': 'Auto-draft: ' + filename,
        'content': base64.b64encode(content.encode('utf-8')).decode()
    }
    if ex.status_code == 200:
        body['sha'] = ex.json()['sha']
    r = requests.put(url, headers=headers, json=body)
    print('GitHub push status:', r.status_code)
    return r.status_code in (200, 201)

def send_telegram(title, filename):
    url = 'https://api.telegram.org/bot' + TG_TOKEN + '/sendMessage'
    payload = {
        'chat_id': TG_CHAT_ID,
        'text': 'New Blog Post Ready\n\nTitle: ' + title + '\n\nTap Publish Now to make it live on your blog.',
        'reply_markup': {
            'inline_keyboard': [[
                {'text': 'Publish Now', 'callback_data': 'publish:' + filename},
                {'text': 'Reject',      'callback_data': 'reject:'  + filename}
            ]]
        }
    }
    r = requests.post(url, json=payload)
    print('Telegram status:', r.status_code)
    return r.json()

def main():
    today = datetime.date.today()
    print('Date:', today)

    print('Fetching news...')
    topic, stories = get_news()
    print('Topic:', topic)

    prompt = (
        'Today is ' + today.strftime('%B %d, %Y') + '. '
        'Write a 600-800 word engaging blog post about one of these ' + topic + ' news stories:\n\n'
        + '\n'.join(stories) + '\n\n'
        'Rules: Pick the most interesting story. Use ## for headings. '
        'Conversational engaging style. No em-dashes. No special Unicode characters. Straight quotes only.\n\n'
        'Return ONLY valid JSON in this exact format (no markdown code blocks):\n'
        '{"title":"Blog Title Here","slug":"url-friendly-slug","content":"full markdown body here"}'
    )

    print('Calling Gemini...')
    raw = call_gemini(prompt).strip()

    # Strip markdown code blocks if Gemini wraps in them
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()
    print('Raw response length:', len(raw))

    post = json.loads(raw)
    print('Title:', post['title'])
    print('Slug:', post['slug'])

    filename = today.strftime('%Y-%m-%d') + '-' + post['slug'] + '.md'
    content = (
        '---\n'
        'layout: post\n'
        'title: "' + post['title'] + '"\n'
        'date: ' + str(today) + '\n'
        'categories: [' + topic + ']\n'
        'author: Anil\n'
        '---\n\n'
        + post['content']
    )

    print('Pushing draft:', filename)
    ok = push_draft(filename, content)
    if not ok:
        raise Exception('GitHub push failed')

    print('Sending Telegram notification...')
    result = send_telegram(post['title'], filename)
    print('Telegram result:', result.get('ok'))
    print('Done!')

if __name__ == '__main__':
    main()
