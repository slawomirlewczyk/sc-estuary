"""Filmweb and IMDb ratings for widget movies (skin setting "Filmweb ratings").

Order on the tile: Filmweb -> IMDb -> the source add-on's own rating (TMDb).

- Filmweb has no public API; the website's JSON endpoints are used, slowly
  (1 request/s), only in the background, and results are cached:
  IMDb id -> Filmweb id forever, ratings for RATING_TTL.
- IMDb ratings come from the official dataset title.ratings.tsv.gz (free for
  personal use), streamed once a week; only the movies we need are kept.

Everything network-related runs in the service; widgets only read ratings.json.
"""
import gzip
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

try:  # inside Kodi
    from . import store
    DATA_FILE = os.path.join(store.DATA_DIR, "ratings.json")
    log = store.log
except ImportError:  # offline tests
    store = None
    DATA_FILE = os.environ.get("SC_RATINGS_FILE", "ratings.json")
    log = print

FILMWEB_API = "https://www.filmweb.pl/api/v1"
IMDB_DATASET = "https://datasets.imdbws.com/title.ratings.tsv.gz"
HEADERS = {"User-Agent": "Mozilla/5.0 (Kodi; SC Widgets)", "x-locale": "pl_PL"}
RATING_TTL = 7 * 24 * 3600       # refresh Filmweb ratings weekly
NO_MATCH_TTL = 30 * 24 * 3600    # retry movies Filmweb did not match after a month
IMDB_TTL = 7 * 24 * 3600         # re-read the IMDb dataset weekly
REQUEST_GAP = 1.0                # seconds between Filmweb requests
MAX_LOOKUPS = 40                 # Filmweb movies per background run
_last_request = [0.0]


# ---------- storage ----------

def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("filmweb", {})
    data.setdefault("imdb", {})
    data.setdefault("imdb_time", 0)
    return data


def save(data):
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


def for_movie(data, imdb):
    """{'filmweb': (rate, votes), 'imdb': (rate, votes)} with what is known."""
    result = {}
    fw = data["filmweb"].get(imdb)
    if fw and fw.get("rate"):
        result["filmweb"] = (round(float(fw["rate"]), 1), int(fw.get("count") or 0))
    im = data["imdb"].get(imdb)
    if im:
        result["imdb"] = (float(im[0]), int(im[1]))
    return result


def missing(data, movies):
    """True if some movie has no Filmweb answer yet or no IMDb rating checked."""
    now = time.time()
    for imdb in movies:
        fw = data["filmweb"].get(imdb)
        if fw is None or now - fw.get("time", 0) > (RATING_TTL if fw.get("id") else NO_MATCH_TTL):
            return True
        if imdb not in data["imdb"] and now - data["imdb_time"] > 24 * 3600:
            return True
    return False


# ---------- update (service only) ----------

def update(movies, abort=lambda: False):
    """movies: {imdb_id: {"title", "originaltitle", "year"}}. Returns True if anything changed."""
    data = load()
    changed = False
    now = time.time()

    need_imdb = {i for i in movies if i not in data["imdb"]}
    if need_imdb and (now - data["imdb_time"] > 24 * 3600) or now - data["imdb_time"] > IMDB_TTL:
        try:
            found = imdb_ratings(set(movies), abort)
            data["imdb"].update(found)
            data["imdb_time"] = now
            changed = changed or bool(found)
            log(f"IMDb dataset: {len(found)} of {len(movies)} movies rated")
        except Exception as e:  # network / format problems: keep old values
            log(f"IMDb dataset failed: {e}")

    lookups = 0
    for imdb, movie in movies.items():
        if abort() or lookups >= MAX_LOOKUPS:
            break
        fw = data["filmweb"].get(imdb)
        if fw is not None and now - fw.get("time", 0) <= (RATING_TTL if fw.get("id") else NO_MATCH_TTL):
            continue
        lookups += 1
        try:
            fw_id = fw.get("id") if fw else None
            if not fw_id:
                fw_id = filmweb_find(movie.get("originaltitle"), movie.get("title"), movie.get("year"))
            entry = {"id": fw_id, "time": now}
            if fw_id:
                rating = filmweb_get(f"/film/{fw_id}/rating") or {}
                entry.update(rate=rating.get("rate"), count=rating.get("count"))
            data["filmweb"][imdb] = entry
            changed = True
        except Exception as e:
            log(f"Filmweb lookup failed for {imdb}: {e}")
            break  # likely blocked or offline; try again next run

    if changed:
        save(data)
    return changed


def imdb_ratings(wanted, abort=lambda: False):
    """Stream the IMDb dataset and keep only the wanted ids: {imdb: [rating, votes]}."""
    found = {}
    req = urllib.request.Request(IMDB_DATASET, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=60) as resp, gzip.GzipFile(fileobj=resp) as gz:
        wanted_bytes = {w.encode() for w in wanted}
        for line_no, raw in enumerate(gz):
            if line_no % 20000 == 0:
                if abort():
                    break
                time.sleep(0.02)  # Kodi add-ons share one Python lock: let the others run
            tconst = raw[:raw.find(b"\t")]
            if tconst in wanted_bytes:
                tconst = tconst.decode()
                _, rate, votes = raw.decode().rstrip("\n").split("\t")
                found[tconst] = [float(rate), int(votes)]
                if len(found) == len(wanted):
                    break
    return found


def filmweb_get(path):
    wait = REQUEST_GAP - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()
    req = urllib.request.Request(FILMWEB_API + path, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        if resp.status == 204:
            return None
        body = resp.read()
    return json.loads(body) if body else None


def filmweb_find(originaltitle, title, year):
    """Filmweb film id for the movie, or None when no candidate matches title and year."""
    try:
        year = int(year or 0)
    except ValueError:
        year = 0
    wanted = {normalize(t) for t in (originaltitle, title) if t}
    if not wanted:
        return None
    tried = set()
    for query in [t for t in (originaltitle, title) if t]:
        found = filmweb_get("/live/search?query=" + urllib.parse.quote(query)) or {}
        candidates = [h["id"] for h in found.get("searchHits", []) if h.get("type") == "film"]
        for fw_id in candidates[:5]:
            if fw_id in tried:
                continue
            tried.add(fw_id)
            info = filmweb_get(f"/film/{fw_id}/info") or {}
            titles = {normalize(info.get("title")), normalize(info.get("originalTitle"))}
            year_ok = not year or not info.get("year") or abs(int(info["year"]) - year) <= 1
            if year_ok and titles & wanted:
                return fw_id
    return None


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"^(the|a|an)\s+", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)
