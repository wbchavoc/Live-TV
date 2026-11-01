#!/usr/bin/env python3
"""Build a categorized M3U from publicly listed IPTV-org US and sports streams.

This reorganizes existing sources; it does not bypass subscription or geo restrictions.
"""
import re
import sys
import time
import urllib.request
from collections import OrderedDict
from pathlib import Path

SOURCES = [
    'https://iptv-org.github.io/iptv/countries/us.m3u',
    'https://iptv-org.github.io/iptv/categories/sports.m3u',
]
METADATA = 'https://iptv-org.github.io/api/channels.json'
OUTPUT = Path(__file__).with_name('channels.m3u')

SPORTS = [
    ('ESPN', [r'^ESPN(?:\s|$|\()'], [r'ESPN2', r'ESPNU', r'Deportes', r'ESPN\+']),
    ('ESPN2', [r'ESPN\s*2'], []),
    ('ESPNU', [r'ESPNU'], []),
    ('NFL Network', [r'NFL Network'], []),
    ('FS1', [r'\bFS\s*1\b', r'FOX Sports 1'], []),
    ('FS2', [r'\bFS\s*2\b', r'FOX Sports 2'], []),
    ('CBS Sports', [r'CBS Sports'], []),
    ('NBC Sports', [r'NBC Sports'], []),
    ('SEC Network', [r'SEC Network'], []),
    ('ACC Network', [r'ACC Network'], []),
    ('Big Ten Network', [r'Big Ten Network', r'\bBTN\b'], []),
    ('Big 12', [r'Big 12'], []),
    ('TBS', [r'^TBS(?:\s|$|\()'], []),
    ('TNT', [r'^TNT(?:\s|$|\()'], []),
    ('truTV', [r'\btruTV\b'], []),
    ('NBA TV', [r'NBA TV'], []),
    ('MLB Network', [r'MLB Network'], []),
    ('NHL Network', [r'NHL Network'], []),
    ('Golf Channel', [r'Golf Channel'], []),
    ('USA Network', [r'USA Network'], []),
    ('NFL RedZone', [r'NFL Red\s*Zone', r'NFL RedZone'], []),
]
CASUAL = [
    ('HBO', [r'^HBO(?:\s|$|\()'], [r'HBO Family', r'HBO Latino', r'HBO Comedy', r'HBO Signature']),
    ('Starz', [r'^Starz(?:\s|$|\()'], [r'Starz Kids', r'Starz Encore']),
    ('TCM', [r'^TCM(?:\s|$|\()', r'Turner Classic Movies'], []),
    ('AMC', [r'^AMC(?:\s|$|\()'], []),
    ('Lifetime Movies', [r'Lifetime Movie', r'\bLMN\b'], []),
    ('Nosey', [r'\bNosey\b'], []),
    ('Game Show Network', [r'Game Show Network', r'\bGSN\b'], []),
    ('Nickelodeon', [r'^Nickelodeon(?:\s|$|\()'], []),
    ('Disney Jr.', [r'Disney Junior', r'Disney Jr'], []),
    ('Disney XD', [r'Disney XD'], []),
    ('Boomerang', [r'\bBoomerang\b'], []),
    ('Nicktoons', [r'\bNicktoons\b'], []),
    ('TeenNick', [r'\bTeenNick\b'], []),
    ('PBS Kids', [r'PBS Kids'], []),
]
PITTSBURGH = [
    ('KDKA-TV 2 (CBS)', r'\bKDKA(?:-TV)?\b'),
    ('WPXI 11 (NBC)', r'\bWPXI\b'),
    ('WTAE-TV 4 (ABC)', r'\bWTAE(?:-TV)?\b'),
    ('WPGH-TV 53 (FOX)', r'\bWPGH(?:-TV)?\b'),
]
GROUP_SPORTS = 'Sports'
GROUP_CASUAL = 'Casual'
GROUP_LOCAL = 'PGH'
GROUP_GENERAL = 'TV'


def get(url, retries=3):
    last = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Live-TV-Playlist-Builder/1.0'})
            with urllib.request.urlopen(request, timeout=35) as response:
                return response.read().decode('utf-8-sig', errors='replace')
        except Exception as exc:
            last = exc
            time.sleep(attempt + 1)
    raise RuntimeError(f'Unable to download {url}: {last}')


def attrs(line):
    return dict(re.findall(r'([\w-]+)="([^"]*)"', line))


def split_extinf(line):
    """Split on the EXTINF name separator, ignoring commas in quoted attributes."""
    quoted = False
    for index, char in enumerate(line):
        if char == '"':
            quoted = not quoted
        elif char == ',' and not quoted:
            return line[:index], line[index + 1:]
    raise ValueError('Invalid EXTINF entry: missing name separator')


def parse_playlist(text):
    if not text.lstrip().startswith('#EXTM3U'):
        raise ValueError('Downloaded data is not an M3U playlist')
    result = []
    pending = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('#EXTINF:'):
            pending = [line]
        elif pending and line.startswith('#'):
            pending.append(line)
        elif pending and line and not line.startswith('#'):
            meta = attrs(pending[0])
            name = split_extinf(pending[0])[1].strip()
            result.append({'name': name, 'id': meta.get('tvg-id', ''),
                           'url': line, 'lines': pending[:]})
            pending = []
    return result


def match(name, patterns, excludes=()):
    return (any(re.search(p, name, re.I) for p in patterns)
            and not any(re.search(p, name, re.I) for p in excludes))


def add(groups, group, entry, display=None):
    key = entry['url']
    if key not in groups[group]:
        groups[group][key] = (entry, display)


def is_us_local(meta):
    """Require a US broadcast area and local affiliate rather than a national network feed."""
    areas = meta.get('broadcast_area') or []
    return any(isinstance(area, str) and (area.startswith('s/US-') or area.startswith('c/US-')) for area in areas)


def main():
    entries = OrderedDict()
    for source in SOURCES:
        found = parse_playlist(get(source))
        if not found:
            raise RuntimeError(f'Source contained no channels: {source}')
        print(f'{source}: {len(found)} entries')
        for item in found:
            item['source'] = 'US' if '/countries/us.m3u' in source else 'Sports'
            entries.setdefault(item['url'], item)

    # Channel metadata is needed for safe language and country filtering.
    metadata = {}
    try:
        import json
        data = json.loads(get(METADATA))
        metadata = {item['id']: item for item in data if item.get('id')}
    except Exception as exc:
        raise RuntimeError(f'Metadata unavailable; existing playlist preserved: {exc}')

    groups = OrderedDict((name, OrderedDict()) for name in [
        GROUP_SPORTS, GROUP_CASUAL, GROUP_LOCAL,
        'ABC', 'CBS', 'FOX', 'NBC', GROUP_GENERAL,
    ])
    excluded_language = re.compile(
        r'\b(?:español|espanol|latino|latina|deportes|portugu[eê]s|brasil|'
        r'fran[cç]ais|french|arabic|hindi|tamil|telugu|punjabi|urdu|'
        r'korean|japanese|chinese|mandarin|russian|turkish)\b', re.I)
    excluded_codes = {'es', 'pt', 'fr', 'ar', 'hi', 'ta', 'te', 'pa', 'ur',
                      'ko', 'ja', 'zh', 'ru', 'tr', 'de', 'it'}
    retained = 0
    for item in entries.values():
        name = item['name']
        meta = metadata.get(item['id'], {})
        langs = meta.get('languages') or []
        if isinstance(langs, str):
            langs = [langs]
        langs = {str(lang).lower().split('-')[0] for lang in langs}
        countries = meta.get('countries') or []
        if isinstance(countries, str):
            countries = [countries]
        countries = {str(c).upper() for c in countries}
        # Keep English/unspecified US-list entries, and English US/Canadian
        # entries from the worldwide sports source. Never filter by stream host.
        if excluded_language.search(name):
            continue
        if langs and ('en' not in langs or bool(langs & excluded_codes) and 'en' not in langs):
            continue
        if item['source'] == 'Sports':
            if not meta or not countries.intersection({'US', 'CA'}) or 'en' not in langs:
                continue
        elif countries and not countries.intersection({'US', 'CA'}):
            continue
        retained += 1
        assigned = False
        for label, includes, excludes in SPORTS:
            if match(name, includes, excludes):
                add(groups, GROUP_SPORTS, item, label)
                assigned = True
                break
        for label, includes, excludes in CASUAL:
            if match(name, includes, excludes):
                add(groups, GROUP_CASUAL, item, label)
                assigned = True
                break
        for label, pattern in PITTSBURGH:
            if re.search(pattern, name, re.I) or re.search(pattern, item['id'], re.I):
                add(groups, GROUP_LOCAL, item, label)
                assigned = True
                break
        network = (meta.get('network') or '').strip().upper()
        if network in ('ABC', 'CBS', 'FOX', 'NBC') and is_us_local(meta):
            add(groups, network, item)
            assigned = True
        if not assigned:
            add(groups, GROUP_GENERAL, item)

    if retained < 10:
        raise RuntimeError('Too few English US/Canadian channels; existing playlist preserved')

        output = ['#EXTM3U']
    for group, items in groups.items():
        for item, display in items.values():
            first, *extras = item['lines']
            header, original = split_extinf(first)
            header = re.sub(r'\s+group-title="[^"]*"', '', header)
            header += f' group-title="{group}"'
            if display:
                original = original.strip()
                name = display if original.lower() == display.lower() else f'{display} | {original}'
            else:
                name = original
            first = header + ',' + name
            output.extend([first, *extras, item['url']])
    temp = OUTPUT.with_suffix('.m3u.tmp')
    temp.write_text('\n'.join(output) + '\n', encoding='utf-8')
    temp.replace(OUTPUT)
    for group, items in groups.items():
        print(f'{group}: {len(items)}')
    print(f'Retained {retained} English-language US/Canadian entries')
    print(f'Wrote {OUTPUT}')


if __name__ == '__main__':
    main()
