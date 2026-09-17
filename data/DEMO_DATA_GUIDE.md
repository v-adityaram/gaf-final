# GAF Demo Data Guide

**Synthetic data for prototype/demo purposes only.** Product names come from gaf.com's
residential taxonomy; every price, account, stock figure, order, contractor, rep, email and
approval number is invented (the two Florida approval numbers FL-16254.3 / NOA 22-0518.09
are reused from the original prototype brief).

**Source of truth:** `GAF_AI_Prototype_Synthetic_Datasets 1.xlsx` at the repo root.
`python scripts/build_dataset.py` regenerates every JSON file here from it (plus the synthetic
extensions listed below); `python scripts/validate_demo_data.py` proves the files agree with each
other. Edit the workbook or the build script -- never the JSON by hand.

The backend reads all of this from disk (`GAF_DATA_SOURCE=local`) through
`backend/app/services/gaf_catalog.py`; the Function App zip built by
`scripts/build_function_app_zip.py` ships the same files under `gaf_data/` and the same module,
so "local" and "live" answers are identical.

## Files

| File | Records | From | What it drives |
|---|---:|---|---|
| `products.json` | 24 | workbook Products | SKU, family, colour (+ swatch hex, High/Bold Definition), unit price per base unit, bundles/square, coverage, website badges, recommended add-ons, ridge-cap colour match, large-order thresholds |
| `add_on_rules.json` | 11 | workbook Addon_Rules (+AR-011) | add-on quantities: starter 1 bundle/10 sq, deck 1 roll/10, leak barrier 1 roll/20, ridge cap 1 bundle/3, vent 1 piece/4 ridge ft; delivery review >30 sq, site access >100 sq |
| `customers.json` | 18 | workbook Customers (+trade names, contacts, ZIPs, reps) | account resolution by legal name / trade name / alias, credit limit & available credit, home DC, sales rep |
| `warehouses.json` | 6 | workbook Warehouses | DC names, lat/long |
| `inventory.json` | 144 | workbook Inventory | per-DC on-hand / reserved / available, safety stock, inbound, receipt dates, backorder risk |
| `orders.json` | 45 | workbook Orders + Order_Lines | priced order history (107 lines) for duplicate detection, rep dashboards |
| `documents.json` + `warranty_docs/*.md` | 12 | workbook Knowledge_Docs (+DOC-106..111) | approved knowledge docs **with full content**; DOC-OLD is expired on purpose |
| `kb_passages.json` | 27 | workbook KB_Passages (+extensions) | citable passages; keyword-scored retrieval for the Warranty Advisor |
| `product_approval.json` | 8 | brief | Florida / Miami-Dade approvals and wind tiers for HDZ and UHDZ |
| `warranty_rules.json`, `escalation_rules.json` | 2 / 5 | brief | Standard Limited vs WindProven; escalation table |
| `counties.json`, `zips.json` | 15 / 21 | workbook Counties (+extensions) | HVHZ vs non-HVHZ regimes; ZIP -> city/county/lat-long |
| `discounts.json` | 8 | synthetic | volume tiers (30+ 3%, 60+ 5%, 100+ 8%), Fall HDZ promo 4% (Sep-Oct 2026), UHDZ launch 2.5% (Sep 2026), Winter leak-barrier/deck promo 6% (Nov-Jan), Complete-System bonus 5% on add-ons, Distributor allowance 2% |
| `contractors.json` | 164 | **73 real** (5 cities) + synthetic (rest) | GAF-certified contractors across 23 ZIPs with tier, rating, reviews, phone, warranties offered -- see note below |
| `sales_reps.json` | 4 | synthetic | reps, territories, commission rate, quota, assigned accounts |
| `emails.json` | 10 | synthetic | customer inbox for the Email Agent (orders, bulk lists, house description, credit-hold rush, warranty, leak, HVHZ nailing, contractor referral, old quote) |
| `demo_scenarios/use_cases.json` | 17 + 36 + 28 | synthetic + workbook scenarios | the header "Demo scenarios" menu, plus the workbook's order/advisor scenarios |

Runtime state written by the app (not part of the dataset): `metrics/*.jsonl`,
`orders/confirmed_orders.json`, `review_queue/warranty_reviews.jsonl`.
`python scripts/reset_demo_state.py` clears them.

## Contractors: real data for 5 cities, synthetic everywhere else

`scripts/real_contractors.py` holds **73 real, currently-operating GAF-certified contractors**
for Tampa (ZIP 33602), Jacksonville (32202), Fort Lauderdale (33301), Naples (34102) and Orlando
(32801) -- real names, phone numbers, ratings, review counts and certification tiers, hand-copied
by the user from gaf.com's public locator on 2026-09-18 (not scraped: an automated headless-browser
pull was tested first and blocked outright by gaf.com's Akamai WAF with "Access Denied", so this is
a one-time manual snapshot, not a live sync -- ratings/review counts will drift from the live site
over time). Every other city in `contractors.json` (Miami, West Palm Beach, Pensacola, Atlanta,
Marietta, Savannah, Dallas, Houston, Charlotte, Newark, plus the 8 new regions below) is synthetic,
same as the rest of this dataset. `build_contractors()` in `build_dataset.py` splices the real list
in for those 5 cities and generates fictional ones for every other ZIP; every real record's `notes`
field says `"REAL DATA -- ..."` so the two are always distinguishable at a glance.

New regions added purely for geographic spread beyond FL/GA/TX/NC/NJ (all synthetic): Chicago IL
(60606), Phoenix AZ (85003), Denver CO (80202), Seattle WA (98101), Los Angeles CA (90017),
Columbus OH (43215), Philadelphia PA (19103), Nashville TN (37203).

## Accounts

| Account | Trade name (legal name) | City | Type | Limit | Available | Status | Rep |
|---|---|---|---|---:|---:|---|---|
| ACC-1001 | Sunshine Roofing Supply (Tampa Contractor Group 01) | Tampa, FL 33602 | Contractor | $125,000 | $65,000 | Good standing | Jordan Reyes |
| ACC-1002 | Gulf Coast Home Builders (Naples Home Builder Group 02) | Naples, FL 34102 | Home Builder | $200,000 | $56,000 | Good standing | Jordan Reyes |
| ACC-1003 | Bayline Distributors (Miami Distributor Group 03) | Miami, FL 33131 | Distributor | $75,000 | $6,750 | **Review** | Maya Chen |
| ACC-1004 | Lauderdale Roofing Co (Fort Lauderdale Contractor Group 04) | Fort Lauderdale, FL 33301 | Contractor | $125,000 | -$7,500 | **CREDIT HOLD** | Maya Chen |
| ACC-1005 | First Coast Builders (Jacksonville Home Builder Group 05) | Jacksonville, FL 32202 | Home Builder | $200,000 | $150,000 | Good standing | Jordan Reyes |
| ACC-1006 | Orange Blossom Supply (Orlando Distributor Group 06) | Orlando, FL 32801 | Distributor | $75,000 | $39,000 | Good standing | Jordan Reyes |
| ACC-1007 | Peachtree Contractors (Atlanta Contractor Group 07) | Atlanta, GA 30303 | Contractor | $125,000 | $35,000 | Good standing | Derek Okafor |
| ACC-1008 | Savannah Coastal Homes (Savannah Home Builder Group 08) | Savannah, GA 31401 | Home Builder | $200,000 | $18,000 | **Review** | Derek Okafor |
| ACC-1009 | Lone Star Distribution (Dallas Distributor Group 09) | Dallas, TX 75201 | Distributor | $75,000 | -$4,500 | **CREDIT HOLD** | Sofia Alvarez |
| ACC-1010 | Bayou City Roofing (Houston Contractor Group 10) | Houston, TX 77002 | Contractor | $125,000 | $93,750 | Good standing | Sofia Alvarez |
| ACC-1011 | Queen City Builders (Charlotte Home Builder Group 11) | Charlotte, NC 28202 | Home Builder | $200,000 | $104,000 | Good standing | Derek Okafor |
| ACC-1012 | Garden State Supply (Newark Distributor Group 12) | Newark, NJ 07102 | Distributor | $75,000 | $21,000 | Good standing | Derek Okafor |
| ACC-1013 | Bay Area Roofing Pros (Tampa Contractor Group 13) | Tampa, FL 33607 | Contractor | $125,000 | $11,250 | **Review** | Jordan Reyes |
| ACC-1014 | Paradise Coast Homes (Naples Home Builder Group 14) | Naples, FL 34103 | Home Builder | $200,000 | -$12,000 | **CREDIT HOLD** | Jordan Reyes |
| ACC-1015 | Magic City Distributors (Miami Distributor Group 15) | Miami, FL 33130 | Distributor | $75,000 | $56,250 | Good standing | Maya Chen |
| ACC-1016 | Broward Roof Works (Fort Lauderdale Contractor Group 16) | Fort Lauderdale, FL 33304 | Contractor | $125,000 | $65,000 | Good standing | Maya Chen |
| ACC-1017 | Riverside Home Builders (Jacksonville Home Builder Group 17) | Jacksonville, FL 32204 | Home Builder | $200,000 | $56,000 | Good standing | Jordan Reyes |
| ACC-1018 | Central Florida Supply (Orlando Distributor Group 18) | Orlando, FL 32803 | Distributor | $75,000 | $6,750 | **Review** | Jordan Reyes |

"Tampa Contractor" on its own matches ACC-1001 **and** ACC-1013 -> the assistant asks which one.
The trade name (e.g. "Sunshine Roofing") resolves exactly.

## Products worth knowing

| SKU | Product | Colour | Price | Notes |
|---|---|---|---:|---|
| TL-HDZ-01..08 | Timberline HDZ | Charcoal, Weathered Wood, Barkwood, Slate (High Definition); Chestnut Valley, Cliffside, Midnight Mesa, Sierra Sand (Bold Definition) | $39.50/bundle = $118.50/sq | 3 bundles/sq; Fall promo 4% |
| TL-UHDZ-01 | Timberline UHDZ (UltraMat, UL 2218 Class 4) | Charcoal | $52.00/bundle = $156/sq | premium consultation warning |
| CAM-II-01 | Camelot II designer | Charcoal | $68.00/bundle = $204/sq | 15% waste in the estimator |
| PRO-START / WEATHERBLOCK | starter strips | -- | $54 / $49 per bundle | 1 per 10 sq |
| TIGER-PAW / DECK-ARMOR | roof deck protection | -- | $112 / $145 per roll | 1 per 10 sq |
| WEATHERWATCH / STORMGUARD | leak barrier | -- | $88 / $94 per roll | 1 per 20 sq |
| SEA-RIDGE-CHAR / SEA-RIDGE-WEA | Seal-A-Ridge ridge cap | Charcoal / Weathered Wood only | $61/bundle | 1 per 3 sq; any other shingle colour -> "confirm ridge colour" |
| TIMBERTEX-CHAR | TimberTex premium ridge cap | Charcoal | $84/bundle | UHDZ / Camelot II match |
| COBRA-RIDGE | ridge ventilation | -- | $19/piece | optional, not a WindProven category |

Stock demo points (Tampa DC): TIMBERTEX-CHAR and FLASH-AL-10 are at 0 available (restock 2026-09-25);
Atlanta DC has 0 PRO-START. Every SKU exists at all six DCs, so alternate-warehouse suggestions fire.

## Demo flow (use the "Demo scenarios" menu)

1. **UC-01** 12 sq HDZ Charcoal for Sunshine Roofing -> priced, ready, Confirm -> rep dashboard updates.
2. **UC-07** 65 sq with the WindProven set, Oct 1 -> volume 5% + Fall 4% + Complete-System 5%, commission shown.
3. **UC-03** 4,000 sq ft two-storey house -> estimate 25 squares -> quick-reply confirm -> order.
4. **UC-02** bulk list for Magic City Distributors -> 4 priced lines + distributor allowance; **UC-17** Bayline -> credit review block.
5. **UC-05** Lauderdale Roofing Co -> CREDIT HOLD blocked.
6. **UC-09** WindProven + Florida approval -> auto-answered at 100 confidence with DOC-102 / DOC-101.
7. **UC-13** coastal + other-manufacturer ridge cap -> confidence < 95 -> review queue (Metrics tab -> approve/edit/reject).
8. **UC-10 / UC-11 / UC-12** expert escalation, urgent leak escalation, StainGuard no-source.
9. **UC-14** contractors near 30061, Master Elite -> cards with tier, rating, distance, phone.
10. **Inbox** (left rail) -> tick Marcus Bell's Riverview order -> Send to assistant -> priced order from the email.
11. **Draft email** (right panel) -> follow-up email signed by the rep.
