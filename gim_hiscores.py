import argparse
from bs4 import BeautifulSoup
import requests
from multiprocessing import Pool
import json
import sys
import os

# Filenames for storing local copies of hiscores
cache_files = [
    "local_hs_2.json",
    "local_hs_hc_2.json",
    "local_hs_3.json",
    "local_hs_hc_3.json",
    "local_hs_4.json",
    "local_hs_hc_4.json",
    "local_hs_5.json",
    "local_hs_hc_5.json",
    "local_groups.json",
    "players.json"
]

# Error message for IP block
scrape_err = "your IP was blocked while scraping, but some results were cached - continue by re-running later"

def die(msg):
    print("gim_hiscores.py: error: {}".format(msg))
    exit(1)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("pages", type=int, help="How many pages of groups to include from the hiscores")
    p.add_argument("activity", help="Name of boss or activity as it appears on hiscores")
    p.add_argument("-size", type=int, default=2, help="Group size (default: 2)")
    p.add_argument("-hardcore", action="store_true", default=False, help="Filter to only living hardcore groups")
    p.add_argument("-prestige", action="store_true", default=False, help="Filter to only prestiged groups")
    p.add_argument("-pool", type=int, default=20, help="Number of threads to make requests to hiscores (default: 20)")
    p.add_argument("-delete-cache", action="store_true", default=False, help="Refresh local copy of hiscores (you will be IP blocked as the cache regenerates)")
    args = p.parse_args()
    if args.hardcore and args.prestige:
        die("'-hardcore' and '-prestige' cannot both be set, as the hardcore hiscores don't track prestige")
    if args.pool < 1:
        die("number of threads for '-pool' must be >= 1")
    return args

# Wrapper for making a request and printing some progress
# (response may be an IP block or connection error)
def request(url, params=None):
    try:
        r = requests.get(url, params=params)
        print("*", end='') # indicates progress
        sys.stdout.flush()
        return r.text
    except ConnectionError:
        return ""

# Request a page of the group ironman hiscores
def page_request(hc, size, page):
    url_base = 'https://secure.runescape.com/m=hiscore_oldschool{}_ironman/group-ironman/?groupSize={}&page={}'
    url = url_base.format("_hardcore" if hc else "", size, page)
    return request(url)

# Request the page for a particular group, in order to get its members
def group_request(g):
    url = 'https://secure.runescape.com/m=hiscore_oldschool_ironman/group-ironman/view-group'
    params = { 'name': g.replace(chr(160), ' ') }
    return request(url, params=params)

# Request the JSON index of a set of players' hiscores
def kc_request(ms):
    responses = []
    url = 'https://services.runescape.com/m=hiscore_oldschool/index_lite.json'
    for m in ms:
        params = { 'player': m.replace(chr(160), ' ') }
        r = request(url, params=params)
        responses.append(r)
    return responses

def fetch_groups(size, hc, prestige, pages, threads):
    gs = []

    # Retrieve pages from local cache
    cache_file = "gim_hiscores_cache/local_hs{}_{}.json".format("_hc" if hc else "", size)
    with open(cache_file, 'r') as f: cache = json.load(f)
    for page in cache[:pages]:
        for row in page:
            if not ((prestige and not row['prestiged']) or (hc and row['dead'])):
                gs.append(row['name'])
    start = len(cache) + 1
    print("Retrieved first {} pages from cache.".format(min(len(cache), pages)))
    if start <= pages: print("Scraping uncached pages {}-{} from hiscores... ".format(start, pages), end='')
    else:              print("No pages scraped from hiscores.", end='')

    # Scrape any pages which were not found in the cache
    # Multi-thread requests to speed things up
    with Pool(threads) as p:
        page_responses = p.starmap(page_request, list(zip([hc] * pages, [size] * pages, range(start, pages + 1))))
    print("")

    # Parse each html response with beautifulsoup
    for pr in page_responses:
        soup = BeautifulSoup(pr, features="html.parser")
        isprestige = lambda e: bool(e.find_previous_sibling('img', title='Group Prestiged'))
        isdead = lambda e: 'uc-scroll__table-row--type-death' in e.parent.parent['class']
        invalid = lambda e: (prestige and not isprestige(e)) or (hc and isdead(e))
        candidates = soup.find_all('a', attrs={'class': 'uc-scroll__link'})

        # Less than 20 results indicates we were IP blocked
        if len(candidates) != 20:
            with open(cache_file, 'w') as f: json.dump(cache, f)
            die(scrape_err)

        # If a valid page was scraped, update the set of groups and the cache
        gs.extend([str(e.string) for e in candidates if not invalid(e)])
        cache.append([{'name': str(e.string), 'dead': isdead(e), 'prestiged': isprestige(e)} for e in candidates])
    
    # Write to cache before returning
    with open(cache_file, 'w') as f: json.dump(cache, f)
    print("Total: {} groups.".format(len(gs)))
    return gs

def fetch_members(gs, size, threads):
    all_members = {}

    # Retrieve group members from local cache
    cache_file = "gim_hiscores_cache/local_groups.json"
    with open(cache_file, 'r') as f: cache = json.load(f)
    uncached_gs = []
    for g in gs:
        if g not in cache:          uncached_gs.append(g)
        elif len(cache[g]) == size: all_members[g] = cache[g]
    print("Retrieved members of {} groups from cache.".format(len(all_members)))
    if len(uncached_gs) > 0: print("Scraping group members for {} uncached groups... ".format(len(uncached_gs)), end='')
    else:                    print("No groups scraped.", end='')

    # Scrape for members of any groups which were not found in the cache
    # Multi-thread requests to speed things up
    with Pool(threads) as p:
        group_responses = p.map(group_request, uncached_gs)
    print("")

    # Parse each html response with beautifulsoup
    for (g, gr) in zip(uncached_gs, group_responses):
        soup = BeautifulSoup(gr, features="html.parser")
        members = [str(e.string) for e in soup.find_all('a', attrs={'class': 'uc-scroll__link'})]

        # If the number of members scraped is less than the group size, we got IP blocked
        # (or the group can't be indexed by name because it was never set, 
        # which is rare but possible in the top groups. We just exclude those.)
        if len(members) != size:
            if g == "Group name not set":
                cache[g] = []
                continue
            with open(cache_file, 'w') as f: json.dump(cache, f)
            die(scrape_err)

        # Otherwise update the group-to-members mapping and the cache
        all_members[g] = members
        cache[g] = members

    # Write to cache before returning
    with open(cache_file, 'w') as f: json.dump(cache, f)
    print("Total: {} players.".format(size * len(gs)))
    return all_members

def fetch_ranks(all_members, boss, threads):
    scores = []
    all_members_list = all_members.items()

    # Pull from cache, and separate out what goes to pool
    # Only take cache values where all players in a group were cached, to make
    # things easy
    cache_file = "gim_hiscores_cache/players.json"
    with open(cache_file, 'r') as f: cache = json.load(f)
    uncached_members = []
    found = 0
    left = 0
    for (g, ms) in all_members_list:
        if all([m in cache for m in ms]):
            scores.append((g, sum([max(0, int(cache[m][boss])) for m in ms if boss in cache[m]])))
            found += len(ms)
        else:
            uncached_members.append((g, ms))
            left += len(ms)
    print("Retrieved scores for {} players from cache.".format(found))

    # Scrape boss kcs for each group and group member using the JSON API
    # Multi-thread requests to speed things up
    if left > 0:
        print("Scraping killcount for {} uncached players... ".format(left), end='')
    else:
        print("No player scores scraped.", end='')
    with Pool(threads) as p:
        kc_responses = p.map(kc_request, [e[1] for e in uncached_members])
    print("")

    # For each group, load JSON for each group member
    # and sum the kc ('score') for the requested activity
    for g, kcrs in zip([e[0] for e in uncached_members], kc_responses):
        kc = 0
        for m, kcr in zip(all_members[g], kcrs):

            # If the json load fails, we got IP blocked (or the player is missing)
            try:
                js = json.loads(kcr)
            except:  
                if '<title>404 - Page not found</title>' in kcr:
                    print("WARNING: player not found on hiscores: {}".format(m))
                    cache[m] = {}
                    continue
                else:
                    with open(cache_file, 'w') as f: json.dump(cache, f)
                    die(scrape_err)

            # Increment activity kc for this member
            score_mb = [x['score'] for x in js['activities'] if x['name'] == boss]
            if len(score_mb) == 0:
                die("the provided activity '{}' does not exist on the hiscores".format(boss))
            kc += max(0, int(score_mb[0]))

            # Update cache
            cache[m] = {}
            for a in js['activities']: cache[m][a['name']] = a['score']
        scores.append((g, kc))
    with open(cache_file, 'w') as f: json.dump(cache, f)
    print("\n")

    # Sort groups by group kc, filtering out 0kc groups
    ranking = sorted(scores, key = lambda s: s[1], reverse = True)
    ranking = [ (r, kc) for (r, kc) in ranking if kc > 0 ]
    return ranking

# Pretty print the rankings when we're all done
def dump_ranking(args, ranking):
    ps = "Prestige " if args.prestige else ""
    hs = "Hardcore " if args.hardcore else ""
    header = "{}{}Group Ironman Hiscores (group size: {})".format(ps, hs, args.size)
    ranks = "\n".join(["{}{}".format(g.ljust(16), kc) for (g, kc) in ranking])
    cols = "Group           Killcount"
    print(header + "\n" + args.activity + "\n\n" + cols + "\n\n" + ranks)

# Delete all locally saved hiscores and groups and regenerate files
def new_cache():
    if not os.path.exists('gim_hiscores_cache'):
        os.mkdir('gim_hiscores_cache')
    for cf in cache_files:
        with open('gim_hiscores_cache/' + cf, 'w') as f:
            if cf == "local_groups.json" or cf == "players.json":
                json.dump({}, f)
            else:
                json.dump([], f)

# Entry point
def main():
    args = parse_args()
    if args.delete_cache or not os.path.exists('gim_hiscores_cache'): new_cache()
    gs = fetch_groups(args.size, args.hardcore, args.prestige, args.pages, args.pool)
    members = fetch_members(gs, args.size, args.pool)
    ranking = fetch_ranks(members, args.activity, args.pool)
    dump_ranking(args, ranking)

if __name__ == "__main__":
    main()