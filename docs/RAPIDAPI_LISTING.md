# RapidAPI Listing Copy: Toronto Rental Finder API

> Agent-drafted marketing copy for the RapidAPI listing page. The user reviews
> and publishes this. No secrets here; the `demo-free-key` is an intentionally
> public free-tier test key.

## API name

**TorontoRentalFinder** (Toronto Rental Finder API)

## Tagline

Scored Toronto rental listings from 9 sources, with TTC transit proximity and LLM quality signals.

## Description

Finding a rental in Toronto means checking Kijiji, Zumper, Rentals.ca, Padmapper, Craigslist, liv.rent, ViewIt, and Condos.ca separately, with no way to compare listings on a single quality scale. TorontoRentalFinder aggregates all of them and scores every listing on a single 0-10 composite so you can stop scrolling and start shortlisting.

The API scrapes nine Toronto rental sources, geocodes each listing, measures walking distance to the nearest of 76 TTC subway stations (Lines 1, 2, and 4), and runs an LLM classification pass that estimates private-room status, occupant count, cleanliness, landlord professionalism, scam risk, and lease flexibility. The composite score blends price value, transit proximity, and the LLM quality signals, so a $1300 room 200m from a subway station with a professional landlord ranks above a $1100 room 2km from transit with scam signals. All rents are in CAD.

You can filter the top listings by rent limit, max walking distance to transit, and minimum cleanliness / landlord-vibe / scam-safety thresholds, and you can send any listing dict to the `/classify` endpoint to get a generic quality assessment without storing it. A Pro-tier endpoint triggers a fresh scrape cycle on demand.

Target audience: renters relocating to Toronto, rental agents and brokers who want a ranked feed, relocation services supporting inbound employees, and comparison sites that need a single scored Toronto rental data source. There is no clean single source for scored Toronto rentals with transit proximity -- each listing site is a walled garden, and none score quality or measure TTC access. That gap is what this API fills.

## Use cases

- **Relocation concierge**: poll `/listings/top?rent_limit=1500&max_walking_m=1000` daily for a client moving to Toronto; push the top 5 with scores and transit info to a Slack or email digest.
- **Comparison site backend**: embed the ranked listings in a "best Toronto rentals right now" page so visitors see scored results rather than raw chronologically-sorted feeds.
- **Agent dashboard**: a rental broker calls `/listings/top` filtered by the client's budget and transit tolerance, then `/listings/{id}` for full detail on a shortlisted unit.
- **Quality pre-screening**: before showing a client a listing, POST its text to `/classify` to get an instant scam-risk and landlord-vibe read without scraping or storing it.
- **Transit-aware search**: use `/stations?lat=..&lon=..&radius_m=800` to find which subway stations are within walking distance of a neighbourhood a renter is considering.

## Endpoints

| Method | Path | Auth | Key params | Sample response |
|---|---|---|---|---|
| GET | `/health` | none | -- | `{"status":"ok","db":{"listings":42,"last_scrape_at":"2026-07-15T03:00:00"},"version":"1.0"}` |
| GET | `/listings/top` | counted | `n` (1-500), `rent_limit`, `max_walking_m`, `min_cleanliness` (1-5), `min_landlord_vibe` (1-5), `max_scam_risk` (1-5) | `{"count":3,"listings":[{...}],"tier":"free","used":1,"limit":100}` |
| GET | `/listings/{id}` | counted | `id` | `{"listing":{...},"tier":"free","used":2}` or `404 not_found` |
| POST | `/classify` | counted | body: `{title, price, address, description}` | `{"classification":{...},"tier":"free","used":3}` |
| GET | `/stations` | counted | `lat`, `lon`, `radius_m` (50-10000) | `{"count":2,"stations":[{...}],"tier":"free","used":4}` |
| POST | `/scrape/refresh` | counted + Pro+ | -- | `{"status":"refreshed","db":{...}}` or `403 tier_required` or `503 scrape_failed` |

Auth: send `X-RapidAPI-Proxy-Secret` (RapidAPI injects this automatically) or
`X-API-Key` for direct/own customers. Missing or unknown key returns `401`.
Over the daily limit returns `429` with `limit`, `used`, `tier`, and `resets_at`
(the next midnight UTC). `/health` is not auth-gated and not counted.

If the listings DB is empty (no scrape run yet), `/listings/top` returns
`{"count":0,"listings":[]}` with a 200 -- it is not an error.

## Pricing tiers

| Tier | Daily requests | RapidAPI suggested price | Notes |
|---|---|---|---|
| Free | 100 / day | $0 | Demo + evaluation. Public key `demo-free-key` works for testing. |
| Basic | 5,000 / day | $12 / month | Personal bots, light relocation feeds, comparison-site dev. |
| Pro | 50,000 / day | $39 / month | Includes `/scrape/refresh` (on-demand scrape). Agent dashboards, relocation services. |
| Ultra | Unlimited | $129 / month | Unlimited + refresh. High-volume comparison platforms. |

> Suggested prices are a starting point; adjust to your market. The free tier
> is intentionally generous (100/day) so developers can build and demo against
> it.

## Sample code

### Python (requests)

```python
import requests

BASE = "https://your-rapidapi-host.p.rapidapi.com"   # RapidAPI
# or BASE = "http://your-server:8101" for direct/customers

HEADERS = {
    "X-RapidAPI-Proxy-Secret": "YOUR_RAPIDAPI_KEY",   # RapidAPI injects this
    # "X-API-Key": "your-direct-key",                 # ...or use this for direct
}

# Top 5 rentals under $1400 within 1000m of a subway station
r = requests.get(
    f"{BASE}/listings/top",
    params={
        "n": 5,
        "rent_limit": 1400,
        "max_walking_m": 1000,
        "min_cleanliness": 3,
        "min_landlord_vibe": 3,
    },
    headers=HEADERS,
    timeout=15,
)
r.raise_for_status()
data = r.json()
for l in data["listings"]:
    print(f"{l['title'][:40]:<40} ${l['price']}/mo  score={l['score']}  {l['nearest_transit']}")
```

### Classify a listing (no storage)

```python
r = requests.post(
    f"{BASE}/classify",
    headers=HEADERS,
    json={
        "title": "Bright private room near Bloor-Yonge",
        "price": 1350,
        "address": "Bloor St W, Toronto",
        "description": "Clean private room, shared bath, month-to-month, professional landlord.",
    },
    timeout=35,
)
print(r.json()["classification"])
# {'private_room': True, 'occupants': 2, 'cleanliness': 4, 'landlord_vibe': 4,
#  'scam_risk': 4, 'lease_flexibility': 5, 'move_in_match': 4,
#  'furniture_match': 3, 'reasoning': '...'}
```

### JavaScript (fetch)

```javascript
const BASE = "https://your-rapidapi-host.p.rapidapi.com";
const headers = {
  "X-RapidAPI-Proxy-Secret": "YOUR_RAPIDAPI_KEY",
  // "X-API-Key": "your-direct-key",
};

const url = new URL(`${BASE}/listings/top`);
url.searchParams.set("n", "5");
url.searchParams.set("rent_limit", "1400");
url.searchParams.set("max_walking_m", "1000");
url.searchParams.set("min_cleanliness", "3");

const res = await fetch(url, { headers });
if (!res.ok) throw new Error(`HTTP ${res.status}`);
const data = await res.json();
console.log(data.count, data.tier);
for (const l of data.listings) {
  console.log(`${l.title}  $${l.price}/mo  score=${l.score}  ${l.nearest_transit}`);
}
```

## Why this API

**Niche, defensible positioning.** There is no clean single source for scored
Toronto rentals with transit proximity. Each listing site (Kijiji, Zumper,
Rentals.ca, Padmapper, Craigslist, liv.rent, ViewIt, Condos.ca) is a walled
garden with its own format, and none score quality or measure TTC access.
TorontoRentalFinder is the only place that aggregates all nine sources,
geocodes each listing, measures walking distance to the nearest of 76 TTC
subway stations, and runs an LLM quality classification -- then ranks
everything on a single re-filterable 0-10 scale.

**Transit scoring is the differentiator.** For Toronto renters, walking
distance to a subway station is often the deciding factor, but no listing
site surfaces it. This API computes Haversine distance to all 76 stations
(Lines 1, 2, 4) and bakes it into the score, so a listing 200m from Union
ranks above one 2km from the nearest station even if the rent is similar.

**LLM quality signals catch what price and location cannot.** The classifier
estimates scam risk, landlord professionalism, cleanliness, and lease
flexibility from the listing text -- signals that a raw price comparison
completely misses and that protect renters from common Toronto rental scams
(too-cheap wire-only listings, fake landlords, bait-and-switch).

**Canadian focus = clear target market.** Rents are in CAD, transit is TTC,
and the geo filter is bounded to the City of Toronto. Relocation services
supporting inbound employees, rental agents, and comparison sites get a
ranked feed that matches what a Toronto renter actually cares about.

**Low-cost, reliable infra.** Runs on Oracle Cloud's free tier with SQLite as
the single store -- no database bill to pass through, which keeps the pricing
low. The scrape is polite (rate-limited, respects site delays) and the API
serves cached scored data so read latency is low even when a scrape is
running.
