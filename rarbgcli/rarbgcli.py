"""
rarbg, rarbccli - RARBG command line interface for scraping the rarbg.to torrent search engine
                  Outputs a torrent information as JSON from a rarbg search.

Example usage:

    $ rarbgcli "the stranger things 3" --category movies --limit 10 --magnet | xargs qbittorrent

https://github.com/FarisHijazi/rarbgcli

"""
# TODO: turn this lib into an API lib (keep the CLI as a bonus)

import argparse
import asyncio
import concurrent.futures
import datetime
import json
import os
import re
import sys
import time
import traceback
import warnings
import webbrowser
import zipfile
from functools import partial
from http.cookies import SimpleCookie
from pathlib import Path
from sys import platform

import requests
import wget
from bs4 import BeautifulSoup
from requests.utils import quote
from tqdm import tqdm

real_print = print
print = print if sys.stdout.isatty() else partial(print, file=sys.stderr)

HOME_DIRECTORY = os.environ.get('RARBGCLI_HOME', str(Path.home()))
PROGRAM_HOME = os.path.join(HOME_DIRECTORY, '.rarbgcli')
os.makedirs(PROGRAM_HOME, exist_ok=True)
COOKIES_PATH = os.path.join(PROGRAM_HOME, 'cookies.json')

TORRENTGALAXY_DOMAINS = [
    'https://rargb.to',
    'https://www.rarbggo.to',
    'https://www.rarbgproxy.to',
    'https://www.rarbgo.to',
    'https://www.proxyrarbg.to',
    'https://rarbg.tw',
    'https://rarbgprx.org',
    'https://rarbgunblock.com',
    'https://rarbgmirror.com',
    'https://rarbgunblock.com',
]
TORRENTGALAXY_CATEGORY2CODE = {
    'movies': 'movies',
    'xxx': 'xxx',
    'music': 'music',
    'tvshows': 'tvshows',
    'software': 'software',
    'games': 'games',
    'nonxxx': 'nonxxx',
}
CATEGORY2CODE = {
    'movies': '48;17;44;45;47;50;51;52;42;46'.split(';'),
    'xxx': '4'.split(';'),
    'music': '23;24;25;26'.split(';'),
    'tvshows': '18;41;49'.split(';'),
    'software': '33;34;43'.split(';'),
    'games': '27;28;29;30;31;32;40;53'.split(';'),
    'nonxxx': '2;14;15;16;17;21;22;42;18;19;41;27;28;29;30;31;32;40;23;24;25;26;33;34;43;44;45;46;47;48;49;50;51;52;54'.split(';'),
    '': '',
}
CODE2CATEGORY = {}
for category, codes in CATEGORY2CODE.items():
    if category in ['movies', 'xxx', 'music', 'tvshows', 'software']:
        for code in codes:
            CODE2CATEGORY[code] = category


# Captcha solving taken from https://github.com/confident-hate/seedr-cli


def solveCaptcha(threat_defence_url):
    from io import BytesIO

    import pytesseract
    from PIL import Image
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    from webdriver_manager.chrome import ChromeDriverManager

    def img2txt():
        try:
            clk_here_button = driver.find_element_by_link_text('Click here')
            clk_here_button.click()
            time.sleep(10)
            WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, 'solve_string')))
        except Exception:
            pass
        finally:
            element = driver.find_elements_by_css_selector('img')[1]
            location = element.location
            size = element.size
            png = driver.get_screenshot_as_png()
            x = location['x']
            y = location['y']
            width = location['x'] + size['width']
            height = location['y'] + size['height']
            im = Image.open(BytesIO(png))
            im = im.crop((int(x), int(y), int(width), int(height)))
            return pytesseract.image_to_string(im)

    options = Options()
    options.add_argument('--no-sandbox')
    options.add_argument('--headless')
    options.add_argument('--log-level=3')
    options.add_argument('--disable-logging')
    options.add_argument('--output=' + ('NUL' if sys.platform == 'win32' else '/dev/null'))

    # import get_chrome_driver  # no longer needed since ChromeDriverManager exists
    # chromedriver_path = get_chrome_driver.main(PROGRAM_HOME)
    driver = webdriver.Chrome(
        ChromeDriverManager(path=PROGRAM_HOME).install(),
        chrome_options=options,
        service_log_path=('NUL' if sys.platform == 'win32' else '/dev/null'),
    )
    print('successfully loaded chrome driver')

    driver.implicitly_wait(10)
    driver.get(threat_defence_url)

    if platform == 'win32':
        pytesseract.pytesseract.tesseract_cmd = os.path.join(PROGRAM_HOME, 'Tesseract-OCR', 'tesseract')

    try:
        solution = img2txt()
    except pytesseract.TesseractNotFoundError:
        print('Tesseract not found. Downloading tesseract ...')
        download_tesseract(PROGRAM_HOME)
        solution = img2txt()

    text_field = driver.find_element_by_id('solve_string')
    text_field.send_keys(solution)
    try:
        text_field.send_keys(Keys.RETURN)
    except Exception as e:
        print(e)

    time.sleep(3)
    cookies = {c['name']: c['value'] for c in (driver.get_cookies())}
    driver.close()
    return cookies


def download_tesseract(chdir='.'):
    os.chdir(chdir)

    # download for each platform if statement
    if platform == 'win32':
        tesseract_zip = wget.download('https://github.com/FarisHijazi/rarbgcli/releases/download/v0.0.7/Tesseract-OCR.zip', 'Tesseract-OCR.zip')
        # extract the zip file
        with zipfile.ZipFile(tesseract_zip, 'r') as zip_ref:
            zip_ref.extractall()  # you can specify the destination folder path here
        # delete the zip file downloaded above
        os.remove(tesseract_zip)
    elif platform in ['linux', 'linux2']:
        os.system('sudo apt-get install tesseract-ocr')
    else:
        raise Exception('Unsupported platform')


def cookies_txt_to_dict(cookies_txt: str) -> dict:
    # SimpleCookie.load = lambda self, data: self.__init__(data.split(';'))
    cookie = SimpleCookie()
    cookie.load(cookies_txt)
    return {k: v.value for k, v in cookie.items()}


def cookies_dict_to_txt(cookies_dict: dict) -> str:
    return '; '.join(f'{k}={v}' for k, v in cookies_dict.items())


def deal_with_threat_defence_manual(threat_defence_url):
    real_print(
        f"""
    rarbg CAPTCHA must be solved, please follow the instructions bellow (only needs to be done once in a while):

    1. On any PC, open the link in a web browser: "{threat_defence_url}"
    2. solve and submit the CAPTCHA you should be redirected to a torrent page
    3. open the console (press F12 -> Console) and paste the following code:

        console.log(document.cookie)

    4. copy the output. it will look something like: "tcc; gaDts48g=q8hppt; gaDts48g=q85p9t; ...."
    5. paste the output in the terminal here

    >>>
    """,
        file=sys.stderr,
    )
    cookies = input().strip().strip("'").strip('"')
    cookies = cookies_txt_to_dict(cookies)

    return cookies


def deal_with_threat_defence(threat_defence_url):
    try:
        return solveCaptcha(threat_defence_url)
    except Exception as e:
        if not sys.stdout.isatty():
            raise Exception(
                'Failed to solve captcha automatically, please rerun this command (without a pipe `|`) and solve it manually. This process only needs to be done once'
            ) from e

        print('Failed to solve captcha, please solve manually', e)
        return deal_with_threat_defence_manual(threat_defence_url)


def get_page_html(target_url, cookies):
    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.122 Safari/537.36'}
    while True:
        r = requests.get(target_url, headers=headers, cookies=cookies)
        print('going to page', r.url, end=' ')
        if 'threat_defence.php' not in r.url:
            break
        print('\ndefence detected')
        cookies = deal_with_threat_defence(r.url)
        # save cookies to json file
        with open(COOKIES_PATH, 'w') as f:
            json.dump(cookies, f)

    data = r.text.encode('utf-8')
    return r, data, cookies


def extract_torrent_file(anchor, domain='rarbgunblocked.org'):
    return (
        'https://'
        + domain
        + anchor.get('href').replace('torrent/', 'download.php?id=')
        + '&f='
        + quote(anchor.contents[0] + '-[rarbg.to].torrent')
        + '&tpageurl='
        + quote(anchor.get('href').strip())
    )


def tryint(x):
    try:
        return int(x)
    except ValueError as e:
        print('[W]:' + e)


def open_url(url):
    webbrowser.open(url)


async def open_torrentfiles(urls):
    for url in tqdm(urls, 'downloading', total=len(urls)):
        open_url(url)
        if len(urls) > 5:
            await asyncio.sleep(0.5)


def extract_magnet(anchor):
    # real:
    #     https://rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    #     https://rarbgaccess.org/download.php?id=...&      f=...-[rarbg.com].torrent
    # https://www.rarbgaccess.org/download.php?id=...&h=120&f=...-[rarbg.to].torrent
    # matches anything containing "over/*.jpg" *: anything
    regex = r'over\/(.*)\.jpg\\'
    trackers = 'http%3A%2F%2Ftracker.trackerfix.com%3A80%2Fannounce&tr=udp%3A%2F%2F9.rarbg.me%3A2710&tr=udp%3A%2F%2F9.rarbg.to%3A2710'
    try:
        hash = re.search(regex, str(anchor))[1]
        title = quote(anchor.get('title'))
        return f'magnet:?xt=urn:btih:{hash}&dn={title}&tr={trackers}'
    except Exception:
        return ''


size_units = {
    'B': 1,
    'KB': 10**3,
    'MB': 10**6,
    'GB': 10**9,
    'TB': 10**12,
    'PB': 10**15,
    'EB': 10**18,
    'ZB': 10**21,
    'YB': 10**24,
}


def parse_size(size: str):
    number, unit = [string.strip() for string in size.strip().split()]
    return int(float(number) * size_units[unit])


def format_size(size: int, block_size=None):
    """automatically format the size to the most appropriate unit"""
    if block_size is None:
        for unit in reversed(list(size_units.keys())):
            if size >= size_units[unit]:
                return f'{size / size_units[unit]:.2f} {unit}'
    else:
        return f'{size / size_units[block_size]:.2f} {block_size}'


def dict_to_fname(d):
    # copy and sanitize
    white_list = {'limit', 'category', 'order', 'search', 'descending'}
    args_dict = {k: str(v).replace('"', '').replace(',', '') for k, v in sorted(vars(d).items()) if k in white_list}
    filename = json.dumps(args_dict, indent=None, separators=(',', '='), ensure_ascii=False)[1:-1].replace('"', '')
    return filename


def unique(dicts):
    seen = set()
    deduped = []
    for d in dicts:
        t = tuple(d.items())
        if t not in seen:
            seen.add(t)
            deduped.append(d)
    return deduped


def get_user_input_interactive(torrent_dicts, start_index=0, current_page=None, total_pages=None):
    header = ' '.join(['SN'.ljust(4), 'TORRENT NAME'.ljust(80), 'SEEDS'.ljust(6), 'LEECHES'.ljust(6), 'SIZE'.center(12), 'UPLOADER'])
    choices = []
    for i in range(len(torrent_dicts)):
        torrent_name = str(torrent_dicts[i]['title'])
        torrent_size = str(torrent_dicts[i]['size'])
        torrent_seeds = str(torrent_dicts[i]['seeders'])
        torrent_leeches = str(torrent_dicts[i]['leechers'])
        torrent_uploader = str(torrent_dicts[i]['uploader'])
        choices.append(
            {
                'value': int(i),
                'name': ' '.join(
                    [
                        str(start_index + i + 1).ljust(4),
                        torrent_name.ljust(80),
                        torrent_seeds.ljust(6),
                        torrent_leeches.ljust(6),
                        torrent_size.center(12),
                        torrent_uploader,
                    ]
                ),
            }
        )
    choices.append({'value': 'all', 'name': '[download all ⏬]'})
    choices.append({'value': 'next', 'name': f'[{current_page}/{total_pages}] next page >>'})

    import questionary
    from prompt_toolkit import styles

    prompt_style = styles.Style(
        [
            ('qmark', 'fg:#5F819D bold'),
            ('question', 'fg:#289c64 bold'),
            ('answer', 'fg:#48b5b5 bold'),
            ('pointer', 'fg:#48b5b5 bold'),
            ('highlighted', 'fg:#07d1e8'),
            ('selected', 'fg:#48b5b5 bold'),
            ('separator', 'fg:#6C6C6C'),
            ('instruction', 'fg:#77a371'),
            ('text', ''),
            ('disabled', 'fg:#858585 italic'),
        ]
    )
    answer = questionary.select(header + '\nSelect torrents', choices=choices, style=prompt_style).ask()
    return answer


def get_args(argv=None):
    orderkeys = ['data', 'filename', 'leechers', 'seeders', 'size', '']
    sortkeys = ['title', 'date', 'size', 'seeders', 'leechers', '']
    parser = argparse.ArgumentParser(__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    # parser = parser.add_argument_group("Query")
    parser.add_argument('search', help='Search term')
    parser.add_argument('--category', '-c', choices=CATEGORY2CODE.keys(), default='nonxxx')
    parser.add_argument(
        '--domain',
        default='rargb.to/',
        help='Domain to search, you could put an alternative mirror domain here',
    )
    parser.add_argument(
        '--order',
        '-r',
        choices=orderkeys,
        default='',
        help='Order results (before query) by this key. empty string means no sort',
    )
    parser.add_argument(
        '--sort_order',
        '-o',
        choices=['asc', 'desc'],
        default=None,
        help='Sort order ascending or descending (only availeble with --order)',
    )
    parser.add_argument(
        '--show_empty',
        action='store_true',
        default=None,
        help='Force show torrents without download or magnet links.',
    )

    output_group = parser.add_argument_group('Output options')
    output_group.add_argument('--magnet', '-m', action='store_true', help='Output magnet links')
    output_group.add_argument(
        '--sort',
        '-s',
        choices=sortkeys,
        default='',
        help='Sort results (after scraping) by this key. empty string means no sort',
    )
    output_group.add_argument('--limit', '-l', type=float, default='inf', help='Limit number of torrent magnet links')
    output_group.add_argument(
        '--interactive',
        '-i',
        action='store_true',
        default=None,
        help='Force interactive mode, show interctive menu of torrents',
    )
    output_group.add_argument(
        '--download_torrents',
        '-d',
        action='store_true',
        default=None,
        help='Open torrent files in browser (which will download them)',
    )
    output_group.add_argument(
        '--block_size',
        '-B',
        type=lambda x: x.upper(),
        metavar='SIZE',
        default=None,
        choices=list(size_units.keys()),
        help='Display torrent sizes in SIZE unit. Choices are: ' + str(set(list(size_units.keys()))),
    )

    misc_group = parser.add_argument_group('Miscilaneous')
    misc_group.add_argument('--no_cache', '-nc', action='store_true', help="Don't use cached results from previous searches")
    misc_group.add_argument(
        '--no_cookie',
        '-nk',
        action='store_true',
        help="Don't use CAPTCHA cookie from previous runs (will need to resolve a new CAPTCHA)",
    )
    args = parser.parse_args(argv)

    if args.interactive is None:
        args.interactive = sys.stdout.isatty()  # automatically decide based on if tty

    if not args.limit >= 1:
        print('--limit must be greater than 1', file=sys.stderr)
        exit(1)
    if args.sort_order is not None and not args.order:
        print('--sort_order requires --order', file=sys.stderr)
        exit(1)
    return args


def load_cookies(no_cookie):
    # read cookies from json file
    cookies = {}
    # make empty cookie if cookie doesn't already exist
    if not os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH, 'w') as f:
            json.dump({}, f)

    if not no_cookie:
        with open(COOKIES_PATH, 'r') as f:
            cookies = json.load(f)
    return cookies


def cli(argv=None):
    args = get_args(argv)
    print(vars(args))
    return main(**vars(args), _session_name=dict_to_fname(args))


def build_url(search, page, category, domain, order, sort_order, torrentgalaxy_mode=False):
    if not torrentgalaxy_mode:
        target_url = 'https://{domain}/torrents.php?search={search}&page={page}'
        target_url_formatted = target_url.format(
            domain=domain.strip(),
            search=quote(search),
            page=page,
        )
        if sort_order:
            target_url_formatted += '&by=' + sort_order.upper().strip()
        if order:
            target_url_formatted += '&order=' + order.strip()
        if category:
            target_url_formatted += '&category=' + ';'.join(CATEGORY2CODE[category])
        return target_url_formatted
    else:
        target_url = 'https://{domain}/{category}/{page}?search={search}'
        target_url_formatted = target_url.format(
            domain=domain.strip().rstrip('/'),
            search=quote(search),
            page=page,
            category='search' if len(search) else TORRENTGALAXY_CATEGORY2CODE.get(category, ''),
        )
        if sort_order:
            target_url_formatted += '&by=' + sort_order.upper().strip()
        if order:
            target_url_formatted += '&order=' + order.strip()
        return target_url_formatted


def main(
    search,
    category='',
    download_torrents=None,
    limit=float('inf'),
    domain='rarbgunblocked.org',
    order='',
    sort_order=None,
    interactive=False,
    magnet=False,
    sort='',
    no_cache=False,
    no_cookie=False,
    block_size='auto',
    _session_name='untitled',  # unique name based on args, used for caching
    torrentgalaxy_mode=None,
    show_empty=False,  # will show torrents that have no magnet link
):

    if torrentgalaxy_mode is None:
        torrentgalaxy_mode = 'https://' + domain.lstrip('https://').lstrip('http://').rstrip('/') in TORRENTGALAXY_DOMAINS

    cookies = load_cookies(no_cookie)

    # TODO: make this parallel
    def process_dict(d):
        if not d['magnet']:
            print('fetching magnet link for', d['title'])
            try:
                html_subpage = requests.get(d['href'], cookies=cookies).text.encode('utf-8')
                parsed_html_subpage = BeautifulSoup(html_subpage, 'html.parser')
                d['magnet'] = parsed_html_subpage.select_one('a[href^="magnet:"]').get('href')
                d['torrent_file'] = parsed_html_subpage.select_one('a[href^="/download.php"]').get('href')
            except Exception:
                pass

    def print_results(dicts):
        if sort:
            dicts.sort(key=lambda x: x[sort], reverse=True)
        if limit < float('inf'):
            dicts = dicts[: int(limit)]

        with concurrent.futures.ThreadPoolExecutor() as executor:
            concurrent.futures.wait([executor.submit(process_dict, d) for d in dicts])

        # pretty print unique(dicts) as yaml
        # print('torrents:', yaml.dump(unique(dicts), default_flow_style=False))

        # reads file then merges with new dicts
        with open(cache_file, 'w', encoding='utf8') as f:
            json.dump(unique(dicts), f, indent=4)

        # open torrent urls in browser in the background (with delay between each one)
        if download_torrents is True or interactive and input(f'Open {len(dicts)} torrent files in browser for downloading? (Y/n) ').lower() != 'n':
            torrent_urls = [d['torrent'] for d in dicts]
            magnet_urls = [d['magnet'] for d in dicts]
            if torrentgalaxy_mode:
                urls = magnet_urls
            else:
                urls = torrent_urls + magnet_urls
            asyncio.run(open_torrentfiles(urls))

        if magnet:
            real_print('\n'.join([t['magnet'] for t in dicts]))
        else:
            real_print(json.dumps(dicts, indent=4))

    def interactive_loop(dicts, current_page=None, total_pages=None):
        while interactive:
            os.system('cls||clear')
            user_input = get_user_input_interactive(
                dicts, start_index=len(dicts_all) - len(dicts_current), current_page=current_page, total_pages=total_pages
            )
            print('user_input', user_input)
            if user_input is None:  # next page
                print('\nNo item selected\n')
            elif user_input == 'next':
                break
            elif user_input == 'all':
                print_results(dicts_all)
            else:  # indexes
                input_index = int(user_input)
                print_results([dicts[input_index]])
            try:
                user_input = input('[ENTER]: back to results, [q or ctrl+C]: (q)uit')
            except KeyboardInterrupt:
                print('\nUser exit')
                exit(0)

            if user_input.lower() == 'q':
                exit(0)
            elif user_input == '':
                continue

    # == dealing with cache and history ==
    cache_file = os.path.join(PROGRAM_HOME, 'history', _session_name + '.json')
    os.makedirs(os.path.dirname(cache_file), exist_ok=True)
    if os.path.exists(cache_file) and not no_cache:
        try:
            with open(cache_file, 'r') as f:
                cache = json.load(f)
        except Exception as e:
            print('Error:', e)
            traceback.print_exc()
            os.remove(cache_file)
            cache = []
    else:
        cache = []

    dicts_all = []
    i = 1

    warnings.warn(
        'You are using one of the torrentgalaxy mirrors. These are not fully supported yet.\n'
        'But it\'s the best we can do since the official rarbg.to was shutdown.\n'
        'Please raise any issues in https://github.com/FarisHijazi/rarbgcli/issues',
    )

    while True:  # for all pages
        target_url_formatted = build_url(search, i, category, domain, order, sort_order, torrentgalaxy_mode=torrentgalaxy_mode)
        r, html, cookies = get_page_html(target_url_formatted, cookies=cookies)

        with open(os.path.join(os.path.dirname(cache_file), _session_name + f'_torrents_{i}.html'), 'w', encoding='utf8') as f:
            f.write(r.text)
        parsed_html = BeautifulSoup(html, 'html.parser')
        torrents = parsed_html.select('tr.lista2 a[href^="/torrent/"][title]')

        total_pages = '1?'
        try:
            pagelinks = parsed_html.select('#pager_links > a')
            total_pages = tryint(pagelinks[-1].text)
            if total_pages is None:
                total_pages = tryint(pagelinks[-3].text)
        except Exception:
            # print('[W] failed to get total pages')
            pass

        if r.status_code != 200:
            print('error', r.status_code)
            break

        print(f'{len(torrents)} torrents found in page')
        if len(torrents) == 0:
            break
        magnets = list(map(extract_magnet, torrents))
        torrentfiles = list(map(partial(extract_torrent_file, domain=domain), torrents))

        # removed torrents and magnet links that have empty magnets, but maintained order
        torrents, magnets, torrentfiles = zip(*[[a, m, d] for (a, m, d) in zip(torrents, magnets, torrentfiles)])
        torrents, magnets, torrentfiles = list(torrents), list(magnets), list(torrentfiles)

        table_offset = 1 if torrentgalaxy_mode else 0

        dicts_current = [
            {
                'title': torrent.get('title'),
                'torrent': torrentfile,
                'href': f"https://{domain}{torrent.get('href')}",
                'date': datetime.datetime.strptime(
                    str(torrent.findParent('tr').select_one(f'td:nth-child({3+table_offset})').contents[0]), '%Y-%m-%d %H:%M:%S'
                ).timestamp(),
                'category': CODE2CATEGORY.get(
                    torrent.findParent('tr')
                    .select_one(f'td:nth-child({1+table_offset}) img')
                    .get('src')
                    .split('/')[-1]
                    .replace('cat_new', '')
                    .replace('.gif', ''),
                    'UNKOWN',
                ),
                'size': format_size(parse_size(torrent.findParent('tr').select_one(f'td:nth-child({4+table_offset})').contents[0]), block_size),
                'seeders': int(torrent.findParent('tr').select_one(f'td:nth-child({5+table_offset}) > font').contents[0]),
                'leechers': int(torrent.findParent('tr').select_one(f'td:nth-child({6+table_offset})').contents[0]),
                'uploader': str(torrent.findParent('tr').select_one(f'td:last-child').contents[0]),
                'magnet': magnet,
            }
            for (torrent, magnet, torrentfile) in zip(torrents, magnets, torrentfiles)
        ]

        # drop those that aren't matching the category
        if category and category != 'nonxxx':
            dicts_current = list(filter(lambda d: d['category'] == category, dicts_current))
        if category == 'nonxxx':
            dicts_current = list(filter(lambda d: d['category'] != 'xxx', dicts_current))

        with concurrent.futures.ThreadPoolExecutor() as executor:
            concurrent.futures.wait([executor.submit(process_dict, d) for d in dicts_current])
        # remove torrents with empty magnet links
        if not show_empty:
            dicts_current = list(filter(lambda d: not not d['magnet'], dicts_current))

        dicts_all += dicts_current

        cache = list(unique(dicts_all + cache))

        if interactive and len(dicts_current) > 0:
            interactive_loop(dicts_current, current_page=i, total_pages=total_pages)

        if len(list(filter(None, torrents))) >= limit:
            print(f'reached limit {limit}, stopping')
            break
        i += 1

    print(f'total torrents found: {len(dicts_all)}')
    if not interactive:
        dicts_all = list(unique(dicts_all + cache))
        print_results(dicts_all)


if __name__ == '__main__':
    exit(cli())
