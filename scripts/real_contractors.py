"""Real GAF-certified contractors, hand-copied by the user from gaf.com's
public "Find a contractor" locator (https://www.gaf.com/en-us/roofing-
contractors/residential) for five query ZIPs -- 33602 (Tampa), 34102
(Naples), 33301 (Fort Lauderdale), 32202 (Jacksonville), 32801 (Orlando) --
and pasted into the conversation, not scraped by an automated tool (gaf.com
actively blocks headless-browser requests with an Akamai WAF; see the
"Access Denied" test in the session this was built from).

Unlike every other file under data/, the entries below are REAL, currently-
operating GAF-certified businesses: real names, real phone numbers, real
ratings/review counts as of the pull date, and real certification tiers.
They replace the synthetic contractors previously seeded for these five
cities in build_dataset.py's build_contractors(). Everywhere else in the
contractor directory (Miami, West Palm Beach, Pensacola, Atlanta, Marietta,
Savannah, Dallas, Houston, Charlotte, Newark, and any city added later)
stays synthetic/fictional, same as the rest of this demo dataset.

Fields not shown on the locator's list view (years certified, specialties,
whether the contractor also does commercial work) are not fabricated here;
they're left at the same honest defaults for every real entry rather than
invented per-contractor. `city`/`state` and `latitude`/`longitude` are the
contractor's own town (approximate town-centre coordinates, since the
locator doesn't expose a street address) -- not the query ZIP's -- so
distance-based search from any nearby ZIP still sorts correctly.

Source pages (pulled 2026-09-18, `distance=25`, `countryCode=us`,
`numberOfResults=20`): postalCode=33602, 34102, 33301, 32202, 32801.
Ratings/review counts will drift from gaf.com's live site over time; this
is a snapshot, not a live sync.
"""

from __future__ import annotations

# Approximate town-centre coordinates (public knowledge, ~2 decimal
# precision) for every city a contractor below is actually located in --
# not just the five query ZIPs, since GAF's 25-mile radius pulls in
# nearby towns.
CITY_COORDS = {
    ("Tampa", "FL"): (27.9506, -82.4572),
    ("Clearwater", "FL"): (27.9659, -82.8001),
    ("St Petersburg", "FL"): (27.7676, -82.6403),
    ("Odessa", "FL"): (28.1725, -82.5548),
    ("Valrico", "FL"): (27.9375, -82.2359),
    ("Riverview", "FL"): (27.8661, -82.3254),
    ("Brandon", "FL"): (27.9378, -82.2859),
    ("Tarpon Springs", "FL"): (28.1461, -82.7568),
    ("Largo", "FL"): (27.9095, -82.7873),
    ("Lutz", "FL"): (28.1522, -82.4593),
    ("Thonotosassa", "FL"): (28.0578, -82.3007),
    ("Jacksonville", "FL"): (30.3322, -81.6557),
    ("Orange Park", "FL"): (30.1683, -81.7062),
    ("Fleming Island", "FL"): (30.1044, -81.7223),
    ("Yulee", "FL"): (30.6322, -81.6087),
    ("Miami", "FL"): (25.7650, -80.1936),
    ("Pembroke Pines", "FL"): (26.0034, -80.3576),
    ("Hollywood", "FL"): (26.0112, -80.1495),
    ("Oakland Park", "FL"): (26.1706, -80.1329),
    ("Delray Beach", "FL"): (26.4615, -80.0728),
    ("Coral Springs", "FL"): (26.2712, -80.2706),
    ("Fort Lauderdale", "FL"): (26.1224, -80.1373),
    # Nudged closer to Naples than Fort Myers' plain town-centre point --
    # gaf.com's own locator placed these two Fort Myers listings at ~24.5-
    # 24.8 mi from ZIP 34102 (just inside the 25-mile search radius); the
    # plain town centre computes to ~35 mi, which would silently drop them
    # from every search. This keeps the real distances internally
    # consistent with what the locator actually reported.
    ("Fort Myers", "FL"): (26.47, -81.87),
    ("Naples", "FL"): (26.1420, -81.7948),
    ("Bonita Springs", "FL"): (26.3398, -81.7787),
    ("Winter Park", "FL"): (28.5999, -81.3392),
    ("Orlando", "FL"): (28.5383, -81.3792),
    ("Winter Garden", "FL"): (28.5654, -81.5862),
    ("Longwood", "FL"): (28.7031, -81.3387),
    ("Maitland", "FL"): (28.6281, -81.3631),
    ("Apopka", "FL"): (28.6934, -81.5322),
    ("Minneola", "FL"): (28.5658, -81.7359),
}

TIER_LABEL = {
    "presidents_club": "GAF President's Club Award",
    "master_elite": "GAF Master Elite",
    "certified_plus": "GAF Certified Plus",
    "certified": "GAF Certified",
}
TIER_WARRANTIES = {
    "presidents_club": ["President's Club Limited Warranty", "Golden Pledge Limited Warranty", "Silver Pledge Limited Warranty", "System Plus Limited Warranty"],
    "master_elite": ["Golden Pledge Limited Warranty", "Silver Pledge Limited Warranty", "System Plus Limited Warranty"],
    "certified_plus": ["Silver Pledge Limited Warranty", "System Plus Limited Warranty"],
    "certified": ["System Plus Limited Warranty"],
}

# (name, city, state, rating, review_count, phone, tier, query_zip)
# query_zip is the ZIP the row was actually found under -- stored on the
# record only so it validates against zips.json; distance search itself
# always uses the real lat/long above, never this field.
_ROWS: list[tuple[str, str, str, float, int, str, str, str]] = [
    # Tampa, FL -- postalCode=33602 (page 1 of 3; 47 total results on gaf.com, 20 pulled)
    ("Arry's Roofing Services Inc", "Tarpon Springs", "FL", 4.8, 1716, "(727) 939-7195", "presidents_club", "33602"),
    ("Ridge Top Exteriors", "Clearwater", "FL", 4.7, 1194, "(656) 800-9877", "presidents_club", "33602"),
    ("Watertight Roofing Services LLC", "Tampa", "FL", 4.7, 144, "(813) 921-3601", "presidents_club", "33602"),
    ("Affordable Roofing Systems Inc", "Tampa", "FL", 4.2, 160, "(813) 921-7757", "presidents_club", "33602"),
    ("Baldwin Roofing Company LLC", "St Petersburg", "FL", 4.9, 584, "(813) 736-8824", "presidents_club", "33602"),
    ("Sharpe Roofing", "Odessa", "FL", 4.9, 282, "(727) 910-4993", "presidents_club", "33602"),
    ("Certified Roofers & General Contractors", "Valrico", "FL", 4.8, 239, "(813) 473-2015", "presidents_club", "33602"),
    ("Millard Roofing Inc", "Riverview", "FL", 4.8, 112, "(813) 473-6899", "presidents_club", "33602"),
    ("Dynamic Roofing Concepts Inc.", "Brandon", "FL", 4.6, 64, "(813) 937-5567", "presidents_club", "33602"),
    ("Blue Sky Roofing", "Largo", "FL", 4.9, 245, "(727) 966-2709", "presidents_club", "33602"),
    ("Weatherproof Roofing Company", "Clearwater", "FL", 4.9, 218, "(727) 732-2109", "presidents_club", "33602"),
    ("Robinson Roofing & Restoration LLC", "Lutz", "FL", 4.9, 120, "(656) 952-9196", "presidents_club", "33602"),
    ("Red Truck Roofing LLC", "Odessa", "FL", 4.8, 262, "(656) 223-3531", "presidents_club", "33602"),
    ("GreenTek Roofing & Solar", "Thonotosassa", "FL", 4.7, 517, "(833) 519-4525", "presidents_club", "33602"),
    ("Hytz Roofing Inc", "Tampa", "FL", 5.0, 250, "(813) 798-6803", "master_elite", "33602"),
    ("Lionheart Roofing LLC", "Valrico", "FL", 5.0, 79, "(813) 736-9599", "master_elite", "33602"),
    ("All-Bay Roofing Inc", "Odessa", "FL", 5.0, 27, "(727) 939-5331", "master_elite", "33602"),
    ("Dynamic National", "St Petersburg", "FL", 5.0, 4, "(727) 390-3797", "master_elite", "33602"),
    ("Protek Roofing Heating Air & Solar", "Tampa", "FL", 4.9, 1056, "(727) 935-3141", "master_elite", "33602"),
    ("Drew Roofing Inc", "St Petersburg", "FL", 4.9, 304, "(727) 390-3147", "master_elite", "33602"),

    # Jacksonville, FL -- postalCode=32202 (25 total, 20 pulled)
    ("Roof It Right", "Orange Park", "FL", 4.6, 236, "(904) 541-1191", "presidents_club", "32202"),
    ("Stonebridge Construction Services LLC", "Jacksonville", "FL", 4.6, 225, "(904) 262-6636", "presidents_club", "32202"),
    ("Triton Roofing & Restoration LLC", "Fleming Island", "FL", 4.4, 105, "(904) 619-8212", "presidents_club", "32202"),
    ("Minorcan Construction Group Inc", "Jacksonville", "FL", 5.0, 10, "(904) 497-9729", "presidents_club", "32202"),
    ("Red Fox Roofers LLC", "Jacksonville", "FL", 4.9, 409, "(904) 404-1718", "presidents_club", "32202"),
    ("Benton Integrity Roofing Systems", "Jacksonville", "FL", 4.7, 107, "(904) 262-7663", "presidents_club", "32202"),
    ("Preferred Roofing LLC", "Jacksonville", "FL", 4.7, 87, "(904) 751-0840", "presidents_club", "32202"),
    ("All Weather Contractors", "Jacksonville", "FL", 4.5, 360, "(904) 781-7060", "presidents_club", "32202"),
    ("Endless Summer Roofing Co", "Jacksonville", "FL", 5.0, 115, "(904) 357-0722", "master_elite", "32202"),
    ("Southern Coast Roofing", "Jacksonville", "FL", 4.9, 313, "(904) 356-7663", "master_elite", "32202"),
    ("First Light Home Services LLC", "Jacksonville", "FL", 4.9, 227, "(904) 571-3646", "master_elite", "32202"),
    ("Eco Restore LLC", "Jacksonville", "FL", 4.9, 131, "(904) 226-9265", "master_elite", "32202"),
    ("Bohemia Roofing Co Inc", "Jacksonville", "FL", 4.9, 108, "(904) 859-3539", "master_elite", "32202"),
    ("The Dantzler Group Inc", "Jacksonville", "FL", 4.9, 89, "(904) 783-1010", "master_elite", "32202"),
    ("Peak Roofing & Construction Inc", "Jacksonville", "FL", 4.9, 35, "(904) 759-6932", "master_elite", "32202"),
    ("TaylorMade Roofing Inc", "Yulee", "FL", 4.7, 111, "(904) 589-8430", "master_elite", "32202"),
    ("Beaver Home Services Inc", "Orange Park", "FL", 4.6, 481, "(904) 591-6576", "master_elite", "32202"),
    ("1st Impressions Contractors Inc", "Jacksonville", "FL", 4.6, 11, "(904) 233-1116", "master_elite", "32202"),
    ("Townsend Roofing & Construction Services", "Jacksonville", "FL", 4.5, 50, "(904) 645-5887", "master_elite", "32202"),
    ("Florida Shower and Bath LLC", "Jacksonville", "FL", 4.2, 358, "(904) 518-6181", "master_elite", "32202"),

    # Fort Lauderdale, FL -- postalCode=33304 (complete, 8 of 8)
    ("T&S Roofing Systems Inc", "Miami", "FL", 4.8, 1241, "(305) 363-6133", "presidents_club", "33301"),
    ("Florida Home 360", "Pembroke Pines", "FL", 4.8, 1145, "(954) 828-0208", "master_elite", "33301"),
    ("Earl W Johnston Roofing", "Hollywood", "FL", 4.8, 438, "(954) 989-7794", "master_elite", "33301"),
    ("RHI Construction Inc", "Oakland Park", "FL", 4.8, 181, "(954) 290-3992", "master_elite", "33301"),
    ("Imperial Roofing LLC", "Delray Beach", "FL", 4.7, 25, "(954) 667-2990", "master_elite", "33301"),
    ("ABC Roofing Corp", "Coral Springs", "FL", 4.6, 399, "(954) 344-4622", "master_elite", "33301"),
    ("Nast Roofing", "Fort Lauderdale", "FL", 4.6, 383, "(954) 475-0610", "master_elite", "33301"),
    ("All American Roofing Inc", "Oakland Park", "FL", 4.6, 139, "(954) 772-7663", "master_elite", "33301"),

    # Naples, FL -- postalCode=34102 (complete, 9 of 9)
    ("CWC Roofing", "Fort Myers", "FL", 5.0, 14, "(636) 681-6291", "master_elite", "34102"),
    ("Gulf Coast Roofing Company Inc", "Naples", "FL", 4.8, 59, "(239) 653-8342", "master_elite", "34102"),
    ("Saint Raphael Roofing Inc", "Fort Myers", "FL", 4.6, 136, "(239) 999-3315", "master_elite", "34102"),
    ("Halo Roofing Inc", "Naples", "FL", 5.0, 40, "(239) 610-7340", "certified", "34102"),
    ("Roof Wars LLC", "Naples", "FL", 5.0, 11, "(239) 383-0064", "certified", "34102"),
    ("D' Roofing Group Inc", "Naples", "FL", 4.9, 46, "(645) 666-1558", "certified", "34102"),
    ("iRoof LLC", "Naples", "FL", 4.9, 31, "(239) 447-1066", "certified", "34102"),
    ("RRCA", "Naples", "FL", 4.3, 489, "(239) 734-2993", "certified", "34102"),
    ("Gulf Western Roofing", "Bonita Springs", "FL", 4.0, 30, "(239) 734-6995", "certified", "34102"),

    # Orlando, FL -- postalCode=32801 (21 total; 4 with no rating/reviews yet excluded)
    ("BFARR Contracting", "Winter Park", "FL", 5.0, 636, "(321) 475-1438", "presidents_club", "32801"),
    ("JA Edwards of America", "Orlando", "FL", 4.6, 421, "(407) 677-7663", "presidents_club", "32801"),
    ("Schick Roofing", "Orlando", "FL", 5.0, 373, "(407) 749-0808", "presidents_club", "32801"),
    ("Sheegog Contracting", "Winter Park", "FL", 4.9, 511, "(407) 637-5339", "presidents_club", "32801"),
    ("Next Level Roofers Inc", "Orlando", "FL", 4.9, 409, "(407) 237-7960", "presidents_club", "32801"),
    ("Level Roofing", "Winter Garden", "FL", 4.9, 392, "(407) 883-0637", "presidents_club", "32801"),
    ("CFL Roofing Inc", "Orlando", "FL", 4.9, 356, "(407) 917-7663", "presidents_club", "32801"),
    ("Roof Bear LLC", "Orlando", "FL", 4.8, 269, "(847) 863-2324", "presidents_club", "32801"),
    ("Edge 2 Edge Roofing LLC", "Longwood", "FL", 4.7, 26, "(678) 765-6510", "presidents_club", "32801"),
    ("Stratus Roofing", "Maitland", "FL", 4.6, 174, "(407) 625-5866", "presidents_club", "32801"),
    ("Construction Unlimited", "Apopka", "FL", 4.9, 219, "(407) 714-1919", "master_elite", "32801"),
    ("AGU Roofing & Solar LLC", "Minneola", "FL", 4.9, 215, "(407) 459-6904", "master_elite", "32801"),
    ("Fiddler's Roofing", "Orlando", "FL", 4.9, 188, "(407) 366-2300", "master_elite", "32801"),
    ("Best Price Roofing Inc", "Apopka", "FL", 4.9, 105, "(407) 814-3572", "master_elite", "32801"),
    ("Premiere Roofing & Carpentry Inc", "Orlando", "FL", 4.4, 59, "(407) 578-6893", "master_elite", "32801"),
    ("Sun Coast Roofing and Solar", "Longwood", "FL", 4.1, 23, "(407) 322-2925", "master_elite", "32801"),
]

# Cities covered by this real batch -- build_contractors() uses this to
# know which query ZIPs to skip synthetic generation for.
REAL_CITIES = {"Tampa", "Jacksonville", "Fort Lauderdale", "Naples", "Orlando"}


def build_real_contractors(start_index: int) -> list[dict]:
    """Returns full contractor records, numbered CTR-<start_index> onward.
    accepts_quote_requests mirrors what gaf.com's own list view showed:
    every "Certified" (lowest, no Master Elite) listing lacked the
    "Request a Quote" button in this pull; every Master Elite and
    President's Club listing had it.
    """
    out = []
    for i, (name, city, state, rating, reviews, phone, tier, query_zip) in enumerate(_ROWS, start=start_index):
        lat, lon = CITY_COORDS[(city, state)]
        out.append({
            "contractor_id": f"CTR-{i:03d}",
            "name": name,
            "city": city, "state": state, "zip": query_zip,
            "latitude": lat, "longitude": lon,
            "phone": phone,
            "rating": rating, "review_count": reviews,
            "certification_tier": tier, "certification_label": TIER_LABEL[tier],
            "warranties_offered": TIER_WARRANTIES[tier],
            "awards": [TIER_LABEL["presidents_club"]] if tier == "presidents_club" else [],
            "specialties": [],
            "years_certified": None,
            "residential": True,
            "commercial": False,
            "accepts_quote_requests": tier != "certified",
            "service_radius_miles": 25,
            "notes": "REAL DATA -- copied from gaf.com's public contractor locator by the user on 2026-09-18; not GAF-affiliated, not verified beyond what the locator showed, and will drift from gaf.com's live site over time.",
        })
    return out
