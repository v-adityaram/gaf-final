"""Pure text-matching helpers against the local dataset's own vocabulary
(customer names/aliases, product families/colours/SKUs, warehouse cities).

These are retrieval aids, not AI: they answer "which JSON records in data/
does this free-text question plausibly refer to", the same job
order_orchestrator._match_product already does with a substring/word match
against the fetched product catalogue. Nothing here classifies intent,
extracts full order fields, or writes an answer -- those are gpt-5-mini's
job (see foundry_client.py + the orchestrators' own prompts). This module
exists so general_query_orchestrator can find the right customer/product
record to hand to gpt-5-mini, without a second model round trip just to
figure out which record to fetch.
"""

import re
from typing import Optional

from app.services import local_data_repository as repo

_ACCOUNT_ID_PATTERN = re.compile(r"\bACC-\d+\b", re.IGNORECASE)
_CUSTOMER_PHRASE_FALLBACK = re.compile(
    r"\bfor\s+(?:the\s+)?([A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*){0,4})"
)


def find_customer_phrase(text: str) -> Optional[str]:
    """Best-effort extraction of a customer-referring phrase from free
    text -- NOT resolution to an account. Resolution (including
    ambiguous/unknown handling) is local_data_repository.get_customers's
    job."""
    if not text:
        return None
    m = _ACCOUNT_ID_PATTERN.search(text)
    if m:
        return m.group(0).upper()

    text_l = text.lower()
    names: set[str] = set()
    for c in repo.load_customers():
        names.add(c["customer_name"])
        names.update(c.get("aliases", []))
    for name in sorted(names, key=len, reverse=True):
        if name.lower() in text_l:
            return name

    m2 = _CUSTOMER_PHRASE_FALLBACK.search(text)
    return m2.group(1).strip() if m2 else None


def find_product_family_and_colour(text: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (productDescription, colour) drawn from the real product
    catalogue's own family names / SKUs / colours."""
    if not text:
        return None, None
    text_l = text.lower()
    products = repo.load_products()

    skus = sorted({p["sku"] for p in products}, key=len, reverse=True)
    sku_hit = next((s for s in skus if s.lower() in text_l), None)
    if sku_hit:
        return sku_hit, None

    families = sorted({p["product_family"] for p in products}, key=len, reverse=True)
    family_hit = next((f for f in families if f.lower() in text_l), None)

    colours = sorted(
        {p["color"] for p in products if p.get("color") and p["color"] != "N/A"}, key=len, reverse=True
    )
    colour_hit = next((c for c in colours if c.lower() in text_l), None)
    return family_hit, colour_hit


def find_city(text: str) -> Optional[str]:
    if not text:
        return None
    text_l = text.lower()
    cities: set[str] = set()
    for c in repo.load_customers():
        if c.get("city"):
            cities.add(c["city"])
        ship = c.get("default_ship_to_city") or ""
        if ship:
            cities.add(ship.split(",")[0].strip())
    for r in repo.load_inventory():
        wh = r.get("warehouse") or ""
        if wh.endswith(" DC"):
            cities.add(wh[:-3])
    for city in sorted({c for c in cities if c}, key=len, reverse=True):
        if city.lower() in text_l:
            return city
    return None
