import os
import json
import requests
from pathlib import Path

CLIENT_ID = os.environ.get("EBAY_CLIENT_ID", "BradleyN-listingm-PRD-e254d2f41-a69abcac")
CLIENT_SECRET = os.environ.get("EBAY_CLIENT_SECRET", "PRD-254d2f41e7a7-5468-4ecf-8e46-f8d8")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "ebay-alerts-x7f2k9")

SEARCHES = [
    {
        "keywords": "oil can",
        "min_price": None,
        "max_price": None,
        "condition": None,
        "category_id": None,
    },
]

SEEN_FILE = Path("seen_items.json")
EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"


def get_access_token():
    response = requests.post(
        EBAY_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "client_credentials",
            "scope": "https://api.ebay.com/oauth/api_scope",
        },
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=15,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def load_seen_items():
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text())
    return {}


def save_seen_items(seen):
    SEEN_FILE.write_text(json.dumps(seen))


def search_ebay(token, search):
    params = {"q": search["keywords"], "limit": "50", "sort": "newlyListed"}

    filters = []
    if search.get("min_price") is not None or search.get("max_price") is not None:
        lo = search.get("min_price", "")
        hi = search.get("max_price", "")
        filters.append(f"price:[{lo}..{hi}],priceCurrency:GBP")
    if search.get("condition"):
        filters.append(f"conditions:{{{search['condition']}}}")
    if filters:
        params["filter"] = ",".join(filters)
    if search.get("category_id"):
        params["category_ids"] = search["category_id"]

    response = requests.get(
        EBAY_SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "X-EBAY-C-MARKETPLACE-ID": "EBAY_GB",
        },
        params=params,
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("itemSummaries", [])


def send_notification(title, message, url=None):
    headers = {"Title": title}
    if url:
        headers["Click"] = url
    requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers=headers,
        timeout=10,
    )


def main():
    token = get_access_token()
    seen = load_seen_items()

    for search in SEARCHES:
        key = search["keywords"]
        seen_ids = set(seen.get(key, []))

        items = search_ebay(token, search)
        new_items = [item for item in items if item["itemId"] not in seen_ids]

        for item in new_items:
            title = item.get("title", "New listing")
            price = item.get("price", {}).get("value", "?")
            currency = item.get("price", {}).get("currency", "")
            link = item.get("itemWebUrl", "")
            send_notification(
                title=f"New: {search['keywords']}",
                message=f"{title}\n{price} {currency}",
                url=link,
            )

        all_ids = seen_ids.union(item["itemId"] for item in items)
        seen[key] = list(all_ids)

        print(f"Checked search: '{key}' — {len(new_items)} new listing(s) found")

    save_seen_items(seen)


if __name__ == "__main__":
    main()
