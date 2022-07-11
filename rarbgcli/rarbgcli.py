#!/home/e/anaconda3/bin/python
"""
rarbccli: RARBG command line interface for scraping the rarbg.to torrent search engine.

prints a list of magnets from a rarbg search.

example usage:

    $ rarbgcli "the stranger things 3" --category movies --limit 10 --magnets

The program is pipe-friendly, so you could use this tool in conjunction with the [jq](https://stedolan.github.io/jq/) command to filter the JSON output, and then pipe it to your favorite torrent client.

The --magnet option is a convenience option instead of filtering it every time with `jq`, the bellow 2 lines are equivalent:

The --magnet option is a convenience option instead of filtering it every time with `jq`, the bellow 2 lines are equivalent:

    $ rarbgcli "the stranger things 3" --category movies --limit 10 | jq .[].magnet | qbittorrent
    $ rarbgcli "the stranger things 3" --category movies --limit 10 --magnet | qbittorrent

"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROGRAM_DIRECTORY = Path(__file__).parent.resolve()
real_print = print
print = print if sys.stdout.isatty() else lambda *a, **k: None
COOKIES_PATH = os.path.join(PROGRAM_DIRECTORY, '.cookies.json')


def deal_with_threat_defence(threat_defence_url):
    # if sys.stdout.isatty():
    #     real_print("Please avoid using a pipe for CAPTCHA setup, you may need to rerun the command",
    #     file=sys.stderr, flush=True)
    open_program(threat_defence_url)
    real_print(f'''
    rarbg CAPTCHA must be solved, please follow the instructions bellow (only needs to be done once in a while):

    1. On any PC, open the link in a web browser: "{threat_defence_url}"
    2. solve and submit the CAPTCHA you should be redirected to a torrent page
    3. open the console (press F12 -> Console) and paste the following code:
    
        console.log(document.cookie)

    4. copy the output. it will look something like: "tcc; gaDts48g=q8hppt; gaDts48g=q85p9t; ...."
    5. paste the output in the terminal here

    >>>
    ''', file=sys.stderr)
    cookies = input().strip()

    cookies = dict([x.split('=') for x in cookies.split('; ') if len(x.split('=')) == 2])

    return cookies


def get_page_html(target_url, cookies):
    while True:
        r = requests.get(target_url, headers=headers, cookies=cookies)
        print('going to page', r.url)
        if 'threat_defence.php' not in r.url:
            break
        print('defence detected')
        cookies = deal_with_threat_defence(r.url)
        # save cookies to json file
        with open(COOKIES_PATH, 'w') as f:
            json.dump(cookies, f)

    data = r.text.encode('utf-8')
    return r, data, cookies


def extract_magnet(anchor):
    # real:
    #     https://rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    #     https://rarbgaccess.org/download.php?id=...&      f=...-[rarbg.com].torrent
    # https://www.rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    # matches anything containing "over/*.jpg" *: anything
    regex = r"over\/(.*)\.jpg\\"
    trackers = 'http%3A%2F%2Ftracker.trackerfix.com%3A80%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2710&tr=udp%3A%2F%2F9.rarbg.to%3A2710';
    try:
        hash = re.search(regex, str(anchor))[1]
        title = anchor.get('title')
        return f'magnet:?xt=urn:btih:{hash}&dn={title}&tr={trackers}'
    except Exception as e:
        return ''


def parse_size(size):
    size_units = {"B": 1, "KB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}
    number, unit = [string.strip() for string in size.strip().split()]
    return int(float(number) * size_units[unit])


def dict_to_fname(d):
    # copy and santitize
    args_dict = {k: str(v).replace('"', '').replace(',', '') for k, v in vars(d).items()}
    del args_dict['sort']
    del args_dict['magnet']
    del args_dict['domain']
    del args_dict['no_cache']
    filename = json.dumps(args_dict, indent=None, separators=(',', '='), ensure_ascii=False)[1:-1].replace('"', '')
    return filename


def open_program(program):
    if sys.platform == 'win32':
        return os.startfile(program)
    else:
        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
        return subprocess.call([opener, program])


cat_code_dict = {
    'movies': '48;17;44;45;47;50;51;52;42;46'.split(';'),
    'xxx': '4'.split(';'),
    'music': '23;24;25;26'.split(';'),
    'tvshows': '18;41;49'.split(';'),
    'software': '33;34;43'.split(';'),
    'games': '27;28;29;30;31;32;40;53'.split(';'),
    'nonxxx': '2;14;15;16;17;21;22;42;18;19;41;27;28;29;30;31;32;40;23;24;25;26;33;34;43;44;45;46;47;48;49;50;51;52;54'.split(';'),
    '': '',
}

headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
    "cache-control": "max-age=0",
    "sec-ch-ua-mobile": "?0",
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1"
}

target_url = 'https://{domain}/torrents.php?search={search}&order={order}&category={category}&page={page}&by={by}'

def main():
    global cookies
    orderkeys = ["data", "filename", "leechers", "seeders", "size", ""]
    sortkeys = ["title", "date", "size", "seeders", "leechers", ""]

    parser = argparse.ArgumentParser(__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('search', help='search term')
    parser.add_argument('--category', '-c', choices=cat_code_dict.keys(), default='')
    parser.add_argument('--limit', '-l', type=float, default='inf', help='limit number of torrent magnet links')
    parser.add_argument('--domain', '-d', default='rarbgunblocked.org', help='domain to search, you could put an alternative mirror domain here')
    parser.add_argument('--order', '-r', choices=orderkeys, default='', help='order results (before query) by this key. empty string means no sort')
    parser.add_argument('--descending', action='store_true', help='order in descending order (only available for --order)')
    parser.add_argument('--magnet', '-m', action='store_true', help='output magnet links')
    parser.add_argument('--sort', '-s', choices=sortkeys, default='', help='sort results (after scraping) by this key. empty string means no sort')
    parser.add_argument('--no_cache', '-nc', action='store_true', help='don\'t use cached results from previous searches')
    args = parser.parse_args()
    assert args.limit >= 1, '--limit must be greater than 1'
    if args.descending:
        assert args.order, '--descending requires --order'

    out_history_fname = dict_to_fname(args)
    os.makedirs(os.path.join(PROGRAM_DIRECTORY, '.history'), exist_ok=True)

    out_history_path = os.path.join(PROGRAM_DIRECTORY, '.history', out_history_fname + '.json')
    if not args.no_cache:
        if os.path.exists(out_history_path):
            with open(out_history_path, 'r') as f:
                history = json.load(f)
            print('using cached results from', out_history_path)
            dicts_all = history
            if args.magnet:
                real_print('\n'.join([t['magnet'] for t in dicts_all]))
            else:
                real_print(json.dumps(dicts_all))
            sys.exit(0)

    # read cookies from json file
    if not os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH, 'w') as f:
            json.dump({}, f)
    with open(COOKIES_PATH, 'r') as f:
        cookies = json.load(f)

    magnets = []
    torrents_all = []
    dicts_all = []
    i = 1
    while True:
        print('scraping page', i)
        r, html, cookies = get_page_html(
            target_url.format(domain=args.domain, search=args.search, order=args.order, category=cat_code_dict[args.category], page=i,
                              by='DESC' if args.descending else 'ASC'),
                              cookies=cookies)

        with open(os.path.join(PROGRAM_DIRECTORY, '.history', out_history_fname + f'_torrents_{i}.html'), 'w', encoding='utf8') as f:
            f.write(r.text)
        parsed_html = BeautifulSoup(html, 'html.parser')
        torrents = parsed_html.select('tr.lista2 a[href^="/torrent/"][title]')
        torrents = [torrent for torrent in torrents if torrent not in torrents_all]

        if r.status_code != 200:
            print('error', r.status_code)
            break

        print(f'{len(torrents)} torrents found')
        if len(torrents) == 0:
            break
        magnets += list(map(extract_magnet, torrents))
        # removed torrents and magnet links that have empty magnets, but maintained order
        torrents, magnets = zip(*[[a, m] for (a, m) in zip(torrents, magnets) if m])
        torrents, magnets = list(torrents), list(magnets)

        dicts_all += [{
            'title': torrent.get('title'),
            'href': torrent.get('href'),
            'date': datetime.datetime.strptime(str(torrent.findParent('tr').select_one('td:nth-child(3)').contents[0]),
                                               '%Y-%m-%d %H:%M:%S').timestamp(),
            'size': parse_size(torrent.findParent('tr').select_one('td:nth-child(4)').contents[0]),
            'seeders': int(torrent.findParent('tr').select_one('td:nth-child(5) > font').contents[0]),
            'leechers': int(torrent.findParent('tr').select_one('td:nth-child(6)').contents[0]),
            'magnet': magnet,
        } for (torrent, magnet) in zip(torrents, magnets)]

        torrents_all += torrents
        if len(list(filter(None, magnets))) >= args.limit:
            print(f'reached limit {args.limit}, stopping')
            break
        i += 1

    if args.sort:
        dicts_all.sort(key=lambda x: x[args.sort], reverse=True)
    if args.limit < float('inf'):
        dicts_all = dicts_all[:int(args.limit)]

    if args.magnet:
        real_print('\n'.join([t['magnet'] for t in dicts_all]))
    else:
        real_print(json.dumps(dicts_all))

    # save history to json file
    with open(out_history_path, 'w', encoding='utf8') as f:
        json.dump(dicts_all, f, indent=4)


if __name__ == '__main__':
    main()
