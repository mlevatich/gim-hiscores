# OSRS Group Ironman boss hiscores

This is a Python script to scrape the Old School Runescape Group Ironman hiscores, in order to generate custom boss hiscores that the OSRS website does not provide.

Features:
- Rank group ironmen groups by boss killcounts!
- Filter ranking to a certain group size
- Filter ranking to only prestiged groups
- Filter ranking to only hardcore groups
- Cache a copy of hiscores locally

Example: Ranking Theatre of Blood completions by prestiged duo group ironmen
```
# As of 12/31/24
> python gim_hiscores.py 25 "Theatre of Blood" -size 2 -prestige

Retrieved first 0 pages from cache.
Scraping uncached pages 1-25 from hiscores... *************************
Total: 234 groups.
Retrieved members of 0 groups from cache.
Scraping group members for 234 uncached groups...
Total: 468 players.
Retrieved scores for 0 players from cache.
Scraping killcount for 468 uncached players...


Prestige Group Ironman Hiscores (group size: 2)
Theatre of Blood

Group           Killcount

zulufanclub1    52
iron berg       50
```

# Why is this difficult?

Jagex does not provide a hiscores API and the web-based group ironmen hiscores are very limited. In order to determine a ranking of group boss killcounts, several web requests must be made:
- One per page of the group ironman hiscores to find group names for the desired size.
- One per group name to find the members of the group.
- One per group member to tally up their killcounts.

This can add up to thousands of requests, which is a) very slow and b) results in your IP address being blocked by Jagex's servers. This imposes some limitations on the tool and requires some creative design:
- Web requests are multi-threaded with a default pool size of 20 for speed.
- A local cache of the hiscores is built as the tool runs, so that when your IP address is inevitably blocked, you can resume later by reading from the cache (over time, the cache will become out-of-date as the hiscores change, and should be deleted).
- BeautifulSoup is used to parse the raw html output.
- Some amount of browser impersonation is used via `curl_cffi`, though whether this has any effect is debateable.

# Installation

```
# you need python and git
git clone git@github.com:mlevatich/gim-hiscores.git
cd gim-hiscores
pip install beautifulsoup4
pip install curl-cffi --upgrade
```

# Usage guide

```
usage: gim_hiscores.py [-h] [-size SIZE] [-hardcore] [-prestige] [-pool POOL] [-delete-cache] pages activity

positional arguments:
  pages          How many pages of groups to include from the hiscores
  activity       Name of boss or activity as it appears on hiscores

optional arguments:
  -h, --help     show this help message and exit
  -size SIZE     Group size (default: 2)
  -hardcore      Filter to only living hardcore groups
  -prestige      Filter to only prestiged groups
  -pool POOL     Number of threads to make requests to hiscores (default: 20)
  -delete-cache  Refresh local copy of hiscores (you will be IP blocked as the cache regenerates)
```

For large requests or when making many repeat requests, **your IP address WILL be blocked by Jagex's servers**. I don't know a way around this in pure Python. All of the results you received before the IP block are cached locally. Simply wait for awhile (15 minutes to an hour in my experience), and then re-run your command to make progress - the program will use the cached results to avoid duplicating old requests.