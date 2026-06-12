import os, json, datetime, requests, feedparser, re, base64, time

GEMINI_API_KEY = os.environ['GEMINI_API_KEY']
TG_TOKEN       = os.environ['TELEGRAM_TOKEN']
TG_CHAT_ID     = os.environ['TELEGRAM_CHAT_ID']
GH_TOKEN       = os.environ['GH_TOKEN']
OWNER, REPO    = 'krishnan107', 'blog'

RSS = [
    ('world',      'https://feeds.bbci.co.uk/news/world/rss.xml'),
    ('technology', 'https://feeds.bbci.co.uk/news/technology/rss.xml'),
    ('science',    'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'),
    ('sports',     'https://feeds.bbci.co.uk/sport/rss.xml'),
]

def get_news():
    topic, url = RSS[datetime.date.today().weekday() % len(RSS)]
    try:
        feed = feedparser.parse(url)
        stories = []
        for e in feed.entries[:5]:
            t = e.get('title', '').strip()
            s = e.get('summary', '')[:300].strip()
            if t:
                stories.append({'title': t, 'summary': s})
    except Exception as e:
        print(f'RSS error: {e}')
        stories = [{'title': 'Top news today', 'summary': ''}]
    return topic, stories

def call_gemini(prompt):
    url = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key=' + GEMINI_API_KEY
    payload = {
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.8, 'maxOutputTokens': 1500}
    }
    r = requests.post(url, json=payload, timeout=60)
    print('Gemini status:', r.status_code)
    r.raise_for_status()
    return r.json()['candidates'][0]['content']['parts'][0]['text']

def push_draft(filename, content):
    path = '_drafts/' + filename
    url  = 'https://api.github.com/repos/' + OWNER + '/' + REPO + '/contents/' + path
    headers = {
        'Authorization': 'token ' + GH_TOKEN,
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'BlogWriter/1.0'
    }
    existing = requests.get(url, headers=headers)
    body = {
        'message': 'Add draft: ' + filename,
        'content': base64.b64encode(content.encode()).decode()
    }
    if existing.status_code == 200:
        body['sha'] = existing.json()['sha']
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

def write_post_for_story(story, topic, today, index):
    prompt = (
        'Today is ' + today.strftime('%B %d, %Y') + '. '
        'Write a 400-600 word engaging blog post about this news story:\n\n'
        'Headline: ' + story['title'] + '\n'
        'Summary: ' + story['summary'] + '\n\n'
        'Rules:\n'
        '- Use ## for section headings\n'
        '- Engaging, conversational style\n'
        '- No em-dashes. No special Unicode characters. Straight quotes only.\n'
        '- End with a brief conclusion paragraph\n\n'
        'Return ONLY valid JSON (no markdown code blocks):\n'
        '{"title":"Blog title here","slug":"url-friendly-slug","content":"full markdown body here"}'
    )
    raw = call_gemini(prompt).strip()
    if raw.startswith('```'):
        raw = re.sub(r'^```[a-z]*\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)
    raw = raw.strip()
    return json.loads(raw)

def main():
    today = datetime.date.today()
    print('Date:', today)

    print('Fetching news...')
    topic, stories = get_news()
    print('Topic:', topic, '| Stories found:', len(stories))

    for i, story in enumerate(stories):
        print(f'\n--- Story {i+1}/{len(stories)}: {story["title"]} ---')
        try:
            post = write_post_for_story(story, topic, today, i)
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
                print('GitHub push failed for:', filename)
                continue

            print('Sending Telegram notification...')
            result = send_telegram(post['title'], filename)
            print('Telegram result:', result.get('ok'))

            # Small delay between stories to avoid rate limits
            if i < len(stories) - 1:
                time.sleep(3)

        except Exception as e:
            print(f'Error on story {i+1}: {e}')
            continue

    print('\nDone! All 5 stories processed.')

if __name__ == '__main__':
    main()
