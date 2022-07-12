"""
rarbccli: RARBG command line interface for scraping the rarbg.to torrent search engine.
https://github.com/FarisHijazi/rarbgcli

Outputs a torrent information as JSON from a rarbg search.

Example usage:

    $ rarbgcli "the stranger things 3" --category movies --limit 10

The program is pipe-friendly, so you could pipe it to your favorite torrent client.

    $ rarbgcli "the stranger things 3" --category movies --limit 10 --magnet | xargs qbittorrent

"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from requests.utils import quote
from functools import partial
from pathlib import Path
from sys import platform

import requests
from bs4 import BeautifulSoup

PROGRAM_DIRECTORY = Path(__file__).parent.resolve()
real_print = print
print = print if sys.stdout.isatty() else partial(print, file=sys.stderr)
COOKIES_PATH = os.path.join(PROGRAM_DIRECTORY, '.cookies.json')

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


## Captcha solving taken from https://github.com/confident-hate/seedr-cli

def solveCaptcha(threat_defence_url):
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    import pytesseract
    from PIL import Image
    from io import BytesIO

    def img2txt():
        try:
            clk_here_button = driver.find_element_by_link_text('Click here')
            clk_here_button.click()
            time.sleep(10)
            WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, 'solve_string'))
            )
        except:
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
    options.add_argument("--headless")
    options.add_argument("--log-level=3")
    options.add_argument("--disable-logging");
    options.add_argument("--output=" + ('NUL' if sys.platform == 'win32' else '/dev/null'));

    driver = webdriver.Chrome(
        chrome_options=options,
        # chrome_profile=FFprofile,
        service_log_path=('NUL' if sys.platform == 'win32' else '/dev/null')
    )
    driver.implicitly_wait(10)
    driver.get(threat_defence_url)

    if platform == 'win32':
        pytesseract.pytesseract.tesseract_cmd = os.path.join(PROGRAM_DIRECTORY, 'Tesseract-OCR', 'tesseract')

    try:
        solution = img2txt()
    except pytesseract.TesseractNotFoundError:
        print("Tesseract not found. Downloading tesseract ...")
        import download_tesseract
        download_tesseract.main(PROGRAM_DIRECTORY)
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


def deal_with_threat_defence_manual(threat_defence_url):
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


def deal_with_threat_defence(threat_defence_url):
    try:
        return solveCaptcha(threat_defence_url)
    except Exception as e:
        print('failed to solve captcha, please solve manually', e)
        return deal_with_threat_defence_manual(threat_defence_url)


def get_page_html(target_url, cookies):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.122 Safari/537.36'
    }
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
        title = quote(anchor.get('title'))
        return f'magnet:?xt=urn:btih:{hash}&dn={title}&tr={trackers}'
    except Exception as e:
        return ''


def parse_size(size):
    size_units = {"B": 1, "KB": 10 ** 3, "MB": 10 ** 6, "GB": 10 ** 9, "TB": 10 ** 12}
    number, unit = [string.strip() for string in size.strip().split()]
    return int(float(number) * size_units[unit])


def dict_to_fname(d):
    # copy and sanitize
    args_dict = {k: str(v).replace('"', '').replace(',', '') for k, v in vars(d).items()}
    del args_dict['sort']
    del args_dict['magnet']
    del args_dict['domain']
    del args_dict['cache']
    filename = json.dumps(args_dict, indent=None, separators=(',', '='), ensure_ascii=False)[1:-1].replace('"', '')
    return filename


def open_program(program):
    if sys.platform == 'win32':
        return os.startfile(program)
    else:
        opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
        return subprocess.call([opener, program])


def get_user_input_interactive(torrent_dicts):
    header = ' '.join(["SN".ljust(4), "TORRENT NAME".ljust(80), "SEEDS".ljust(6), "LEECHES".ljust(6), "SIZE".center(12), "UPLOADER"])
    choices = []
    for i in range(len(torrent_dicts)):
        torrent_name = str(torrent_dicts[i]['title'])
        torrent_size = str(torrent_dicts[i]['size'])
        torrent_seeds = str(torrent_dicts[i]['seeders'])
        torrent_leeches = str(torrent_dicts[i]['leechers'])
        torrent_uploader = str(torrent_dicts[i]['uploader'])
        choices.append({
            'value': int(i),
            'name': ' '.join([str(i + 1).ljust(4), torrent_name.ljust(80), torrent_seeds.ljust(6), torrent_leeches.ljust(6), torrent_size.center(12),
                              torrent_uploader])
        })

    from prompt_toolkit import styles
    import questionary
    prompt_style = styles.Style([
        ('qmark', 'fg:#5F819D bold'),
        ('question', 'fg:#289c64 bold'),
        ('answer', 'fg:#48b5b5 bold'),
        ('pointer', 'fg:#48b5b5 bold'),
        ('highlighted', 'fg:#07d1e8'),
        ('selected', 'fg:#48b5b5 bold'),
        ('separator', 'fg:#6C6C6C'),
        ('instruction', 'fg:#77a371'),
        ('text', ''),
        ('disabled', 'fg:#858585 italic')
    ])
    answer = questionary.select(
        header + '\nSelect torrents',
        choices=choices,
        style=prompt_style
    ).ask()
    return [answer]


def get_args():
    orderkeys = ["data", "filename", "leechers", "seeders", "size", ""]
    sortkeys = ["title", "date", "size", "seeders", "leechers", ""]
    parser = argparse.ArgumentParser(__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('search', help='Search term')
    parser.add_argument('--category', '-c', choices=CATEGORY2CODE.keys(), default='')
    parser.add_argument('--limit', '-l', type=float, default='inf', help='Limit number of torrent magnet links')
    parser.add_argument('--domain', '-d', default='rarbgunblocked.org', help='Domain to search, you could put an alternative mirror domain here')
    parser.add_argument('--order', '-r', choices=orderkeys, default='', help='Order results (before query) by this key. empty string means no sort')
    parser.add_argument('--descending', action='store_true', help='Order in descending order (only available for --order)')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode, show menu of torrents')

    parser.add_argument('--magnet', '-m', action='store_true', help='Output magnet links')
    parser.add_argument('--sort', '-s', choices=sortkeys, default='', help='Sort results (after scraping) by this key. empty string means no sort')

    parser.add_argument('--cache', action='store_true', help='Use cached results from previous searches')
    parser.add_argument('--no_cookie', '-nk', action='store_true',
                        help='Don\'t use CAPTCHA cookie from previous runs (will need to resolve a new CAPTCHA)')
    args = parser.parse_args()
    if args.interactive and not sys.stdout.isatty():
        print('--interactive mode requires a TTY (cannot be piped)', file=sys.stderr)
        exit(1)
    if not args.limit >= 1:
        print('--limit must be greater than 1', file=sys.stderr)
        exit(1)
    if args.descending and not args.order:
        print('--descending requires --order', file=sys.stderr)
        exit(1)
    return args


def main():
    def print_results(dicts):
        if args.sort:
            dicts.sort(key=lambda x: x[args.sort], reverse=True)
        if args.limit < float('inf'):
            dicts = dicts[:int(args.limit)]

        for d in dicts:
            if not d['magnet']:
                print('fetching magnet link for', d['title'])
                html_subpage = requests.get(d['href'], cookies=cookies).text.encode('utf-8')
                parsed_html_subpage = BeautifulSoup(html_subpage, 'html.parser')
                d['magnet'] = parsed_html_subpage.select_one('a[href^="magnet:"]').get('href')
                d['torrent_file'] = parsed_html_subpage.select_one('a[href^="/download.php"]').get('href')

        if args.magnet:
            real_print('\n'.join([t['magnet'] for t in dicts]))
        else:
            real_print(json.dumps(dicts, indent=4))

    args = get_args()

    out_history_fname = dict_to_fname(args)
    os.makedirs(os.path.join(PROGRAM_DIRECTORY, '.history'), exist_ok=True)
    out_history_path = os.path.join(PROGRAM_DIRECTORY, '.history', out_history_fname + '.json')

    if args.cache and os.path.exists(out_history_path):
        with open(out_history_path, 'r') as f:
            history = json.load(f)
        print('Using cached results from', out_history_path)
        print_results(history)
        sys.exit(0)

    # make empty cookie if cookie doesn't already exist
    if not os.path.exists(COOKIES_PATH):
        with open(COOKIES_PATH, 'w') as f:
            json.dump({}, f)

    # read cookies from json file
    cookies = {}
    if not args.no_cookie:
        with open(COOKIES_PATH, 'r') as f:
            cookies = json.load(f)

    magnets = []
    torrents_all = []
    dicts_all = []
    i = 1
    while True:  # for all pages
        target_url = 'https://{domain}/torrents.php?search={search}&order={order}&category={category}&page={page}&by={by}'
        r, html, cookies = get_page_html(target_url.format(
            domain=args.domain, search=args.search, order=args.order, category=CATEGORY2CODE[args.category], page=i,
            by='DESC' if args.descending else 'ASC'
        ), cookies=cookies)

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
        torrents, magnets = zip(*[[a, m] for (a, m) in zip(torrents, magnets)])
        torrents, magnets = list(torrents), list(magnets)

        dicts_current = [{
            'title': torrent.get("title"),
            'href': f"https://{args.domain}{torrent.get('href')}",
            'date': datetime.datetime.strptime(str(torrent.findParent('tr').select_one('td:nth-child(3)').contents[0]),
                                               '%Y-%m-%d %H:%M:%S').timestamp(),
            'size': parse_size(torrent.findParent('tr').select_one('td:nth-child(4)').contents[0]),
            'seeders': int(torrent.findParent('tr').select_one('td:nth-child(5) > font').contents[0]),
            'leechers': int(torrent.findParent('tr').select_one('td:nth-child(6)').contents[0]),
            'uploader': str(torrent.findParent('tr').select_one('td:nth-child(8)').contents[0]),
            'magnet': magnet,
        } for (torrent, magnet) in zip(torrents, magnets)]

        dicts_all += dicts_current
        torrents_all += torrents

        if args.interactive:
            while True:
                os.system('cls||clear')
                user_input = get_user_input_interactive(dicts_current)
                if not user_input:  # next page
                    print("\nNo item selected\n")
                    pass
                else:  # indexes
                    input_indexes = [int(x) for x in user_input]
                    # save history to json file
                    with open(out_history_path, 'w', encoding='utf8') as f:
                        json.dump(dicts_all, f, indent=4)
                    print_results([dicts_current[idx] for idx in input_indexes])

                user_input = input("[ENTER]: continue to the next page, [b]: go (b)ack to results, [q]: to (q)uit: ")
                if user_input.lower() == 'b':
                    continue
                elif user_input.lower() == 'q':
                    exit(0)
                elif user_input == '':
                    break

        # save history to json file
        with open(out_history_path, 'w', encoding='utf8') as f:
            json.dump(dicts_all, f, indent=4)

        if len(list(filter(None, magnets))) >= args.limit:
            print(f'reached limit {args.limit}, stopping')
            break
        i += 1

    if not args.interactive:
        print_results(dicts_all)


if __name__ == '__main__':
    main()
