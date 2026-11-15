"""VOD services a widget movie streams on in Poland (skin setting "VOD service icons").

Data: TMDb /movie/{id}/watch/providers (provided by JustWatch), country PL,
only subscription and free offers (no rent / buy). Needs the user's own TMDb
API key (v3 key or v4 read access token) in the skin setting sc_tmdb_key.

Network runs only in the service (update); widgets only read providers.json.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

try:  # inside Kodi
    from . import store
    DATA_FILE = os.path.join(store.DATA_DIR, "providers.json")
    log = store.log
except ImportError:  # offline tests
    store = None
    DATA_FILE = os.environ.get("SC_PROVIDERS_FILE", "providers.json")
    log = print

TMDB_API = "https://api.themoviedb.org/3"
LOGO_URL = "https://image.tmdb.org/t/p/w154{}"
COUNTRY = "PL"
OFFER_TYPES = ("flatrate", "free", "ads")  # subscription, free; not rent / buy
MAX_ICONS = 3
TTL = 3 * 24 * 3600        # offers change: re-check every 3 days
NO_ID_TTL = 30 * 24 * 3600  # IMDb id unknown to TMDb: retry after a month
REQUEST_GAP = 0.25         # seconds between TMDb requests
MAX_LOOKUPS = 150          # movies per background run
_last_request = [0.0]


def load():
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data.setdefault("movies", {})
    return data


def save(data):
    os.makedirs(os.path.dirname(DATA_FILE) or ".", exist_ok=True)
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, DATA_FILE)


def for_movie(data, key):
    """[(service name, logo URL), ...] for a movie key ("imdb:tt..." / "tmdb:123")."""
    known = data["movies"].get(key) or {}
    return [(p["name"], LOGO_URL.format(p["logo"])) for p in known.get("providers") or []]


def _fresh(known, now):
    return known is not None and now - known.get("time", 0) <= (TTL if known.get("tmdb") else NO_ID_TTL)


def missing(data, keys):
    now = time.time()
    return any(not _fresh(data["movies"].get(k), now) for k in keys)


def update(movies, api_key, abort=lambda: False):
    """movies: {key: tmdb id or None}. Returns the keys whose services changed."""
    data = load()
    changed = set()
    error = None
    now = time.time()
    lookups = 0
    for key, tmdb in movies.items():
        if abort() or lookups >= MAX_LOOKUPS:
            break
        known = data["movies"].get(key)
        if _fresh(known, now):
            continue
        lookups += 1
        try:
            tmdb = tmdb or (known or {}).get("tmdb") or find_tmdb(key, api_key)
            entry = {"tmdb": tmdb, "time": now, "providers": watch_providers(tmdb, api_key) if tmdb else []}
        except urllib.error.HTTPError as e:
            if e.code == 404:
                entry = {"tmdb": None, "time": now, "providers": []}
            else:
                error = f"HTTP {e.code} {e.reason}" + (" (wrong TMDb API key?)" if e.code == 401 else "")
                break  # bad key or rate limit: try again next run
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            break  # likely offline
        if (known or {}).get("providers") != entry["providers"]:
            changed.add(key)
        data["movies"][key] = entry
    if error:
        log(f"TMDb lookup failed: {error}")
    if lookups or error != data.get("error"):
        data["error"] = error
        data["error_time"] = now if error else None
        save(data)
    return changed, error


def tmdb_get(path, api_key, **params):
    wait = REQUEST_GAP - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.time()
    headers = {"Accept": "application/json", "User-Agent": "Kodi SC Widgets"}
    if len(api_key) > 40:  # v4 read access token
        headers["Authorization"] = "Bearer " + api_key
    else:
        params["api_key"] = api_key
    url = f"{TMDB_API}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as resp:
        return json.loads(resp.read() or b"{}")


def find_tmdb(key, api_key):
    """TMDb movie id for "tmdb:123" or "imdb:tt..." keys, else None."""
    if key.startswith("tmdb:"):
        return key[5:]
    if not key.startswith("imdb:"):
        return None
    found = tmdb_get(f"/find/{key[5:]}", api_key, external_source="imdb_id").get("movie_results") or []
    return str(found[0]["id"]) if found else None


def credits(key, tmdb, api_key):
    """Cast from TMDb as [{"name", "role", "order", "thumbnail"}]."""
    tmdb = tmdb or find_tmdb(key, api_key)
    if not tmdb:
        return []
    cast = tmdb_get(f"/movie/{tmdb}/credits", api_key, language="pl-PL").get("cast") or []
    return [{"name": c.get("name") or "", "role": c.get("character") or "", "order": c.get("order", i),
             "thumbnail": "https://image.tmdb.org/t/p/w185" + c["profile_path"] if c.get("profile_path") else ""}
            for i, c in enumerate(cast[:25]) if c.get("name")]


def watch_providers(tmdb, api_key):
    """[{"name", "logo"}] streaming the movie in COUNTRY, best known first."""
    offers = (tmdb_get(f"/movie/{tmdb}/watch/providers", api_key).get("results") or {}).get(COUNTRY) or {}
    seen, result = set(), []
    for kind in OFFER_TYPES:
        for p in sorted(offers.get(kind) or [], key=lambda p: p.get("display_priority", 999)):
            if p.get("provider_id") in seen or not p.get("logo_path"):
                continue
            seen.add(p.get("provider_id"))
            result.append({"name": p.get("provider_name") or "", "logo": p["logo_path"]})
    return result[:MAX_ICONS]
