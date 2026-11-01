#!/usr/bin/env python3
"""Build a curated playlist from publicly listed IPTV-org streams."""
import re
import urllib.request
from pathlib import Path

SOURCES = [
    'https://iptv-org.github.io/iptv/countries/us.m3u',
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
]
PRIORITY = re.compile(r'kdka|pittsburgh|wpxi|wtae|wpgh|steelers|nfl|football|cbs|fox|nbc|abc|espn|sec network|big ten|btn|acc network|fs1|sports', re.I)
LOCAL = re.compile(r'kdka|wpxi|wtae|wpgh|pittsburgh', re.I)
SPORTS = re.compile(r'nfl|football|sports|espn|sec network|big ten|btn|acc network|fs1', re.I)

def entries(data):
    lines = data.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        extras = []
        for following in lines[i+1:]:
            following = following.strip()
            if following.startswith('#EXTINF:'):
                break
            if not following or following.startswith('#'):
                if following.startswith('#EXTVLCOPT:') or following.startswith('#KODIPROP:'):
                    extras.append(following)
                continue
            if following.startswith(('http://', 'https://')):
                yield line, extras, following
            break

def main():
    seen = set()
    result = []
    for source in SOURCES:
        try:
            req = urllib.request.Request(source, headers={'User-Agent':'Live-TV-Playlist/1.0'})
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read().decode('utf-8-sig', errors='replace')
        except Exception as exc:
            print(f'WARNING: Failed to fetch {source}: {exc}')
            continue
        count = 0
        for meta, extras, url in entries(data):
            if url in seen:
                continue
            seen.add(url)
            count += 1
            text = meta
            category = 'US TV'
            if LOCAL.search(text):
                category = 'Pittsburgh & Local'
            elif SPORTS.search(text):
                category = 'Football & Sports'
            elif 'sports.m3u' in source:
                category = 'Other Sports'
            # Replace or insert group-title so IPTV players can sort channels.
            if 'group-title="' in meta:
                meta = re.sub(r'group-title="[^"]*"', f'group-title="{category}"', meta, count=1)
            else:
                meta = re.sub(r'^(#EXTINF:[^,]*)(,)', lambda m: m.group(1) + f' group-title="{category}"' + m.group(2), meta, count=1)
            rank = (0 if category == 'Pittsburgh & Local' else 1 if category == 'Football & Sports' else 2 if category == 'US TV' else 3)
            result.append((rank, meta.lower(), meta, extras, url))
        print(f'{source}: {count} unique streams added')
    if not result:
        raise SystemExit('No streams fetched; keeping previous playlist if present.')
    result.sort(key=lambda row: (row[0], row[1]))
    output = ['#EXTM3U']
    for _, _, meta, extras, url in result:
        output.extend([meta, *extras, url])
    Path('channels.m3u').write_text('\n'.join(output)+'\n', encoding='utf-8')
    print(f'Wrote {len(result)} unique streams to channels.m3u')

if __name__ == '__main__':
    main()
