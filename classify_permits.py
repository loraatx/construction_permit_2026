#!/usr/bin/env python3
"""
Classify Austin construction permits into 5 trade-specific categories
based on description field keyword matching, supplemented by permit type
and contractor trade signals.

Weight tiers
------------
primary   = 10  — near-certain indicator; beats permit-type + contractor combined
high      =  3  — strong indicator
medium    =  1  — weak / supporting indicator
permit_type bonus =  4
contractor bonus  =  4
Ambiguity: flag when 2nd-best score >= 75 % of best score.

Output: 5 category CSVs + 1 flagged-for-review CSV
"""

import json
import csv
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Keyword definitions  (matched against lower-cased, space-padded description)
# ---------------------------------------------------------------------------

KEYWORDS = {
    "electrical": {
        # primary: unmistakable electrical work
        "primary": [
            "220v", "240v", "50 amp", "100 amp", "200 amp", "400 amp",
            "ev charger", "electric car charger", "electric vehicle charger",
            "electric vehicle charging",
            "photovoltaic", "pv system", "solar array", "solar panel",
            "rooftop solar", "ground mount solar", "solar interconnect",
            "solar pv", "back-feed breaker", "backfeed breaker",
            "battery storage", "battery backup",
            "service entrance", "meter base", "service upgrade",
            "subpanel", "sub-panel", "breaker panel",
            "generator transfer", "transfer switch",
            "tpole", "t-pole", "temp pole", "temporary power pole",
            "low voltage wiring", "fire alarm system", "security system wiring",
        ],
        "high": [
            "electrical", "rewire", "wiring", "conduit",
            "panel upgrade", "panel replacement",
            "inverter", "transformer",
            "circuit breaker", "lighting fixture",
        ],
        "medium": [
            "generator", "outlet", "switch", "lighting",
            "ceiling fan", "light fixture", "power",
        ],
    },
    "plumbing": {
        "primary": [
            "water heater", "tankless water heater",
            "gas line", "gas pipe", "gas piping", "gas riser", "gas meter",
            "natural gas supply", "gas supply line",
            "sewer line", "sewer main", "sewer lateral", "sanitary sewer",
            "water main", "water service line", "water meter",
            "backflow preventer", "backflow prevention", "rpz valve",
            "grease trap", "grease interceptor", "septic system",
            "water softener", "pressure reducing valve",
            "fire suppression", "fire sprinkler",
        ],
        "high": [
            "plumbing", "domestic water", "gas generator",
            "water line replacement", "drain line", "sewer repair",
        ],
        "medium": [
            "drain", "pipe", "faucet", "valve", "sink",
            "fixture", "shower", "tub", "toilet", "lavatory",
        ],
    },
    "mechanical": {
        "primary": [
            "hvac", "heat and air", "heating and cooling", "heating & cooling",
            "central air conditioning", "central air", "central heat",
            "heat pump", "mini-split", "mini split", "ductless split",
            "split system", "ductless system",
            "furnace replacement", "furnace installation",
            "boiler replacement", "boiler installation",
            "chiller", "air handler", "air handling unit",
            "rooftop unit", "package unit", "package hvac",
            "ductwork replacement", "duct system",
            "kitchen hood", "commercial hood", "range hood", "exhaust hood",
            "makeup air unit", "energy recovery ventilator",
            "walk-in cooler", "walk-in freezer",
            "vav box", "fau", "attic fan", "whole house fan",
        ],
        "high": [
            "mechanical", "furnace", "boiler",
            "air conditioning", "air conditioner",
            "ductwork", "duct work", "ventilation",
            "condenser unit", "condenser replacement",
            "exhaust fan", "exhaust system",
            "refrigeration system",
        ],
        "medium": [
            "heating", "cooling", "blower", "coil",
            "a/c", " ac ", "damper", "thermostat",
        ],
    },
    "site_landscape": {
        # primary: work unmistakably done by site/landscape/pool contractors
        "primary": [
            "irrigation", "drip irrigation", "sprinkler system",
            "irrigation installation", "irrigation system",
            "swimming pool", "in-ground pool", "inground pool",
            "pool construction", "pool remodel", "pool renovation",
            "pool and spa", "pool & spa",
            "retaining wall",
            "fencing", "fence installation", "fence replacement",
            "wood fence", "iron fence", "chain link fence",
            "site grading", "rough grading", "finish grading",
            "erosion control", "storm drain", "detention pond",
            "driveway approach", "concrete approach",
            "tree removal", "tree trimming",
            "landscaping", "landscape installation",
        ],
        "high": [
            "new pool", "pool deck", "pool equipment",
            "hot tub", "new spa",
            " fence ", " fencing",
            "grading", "site drainage",
            "driveway", "sidewalk", "curb and gutter", "curb & gutter",
            "hardscape", "paving", "asphalt",
            "site work", "earthwork", "excavation",
            "pergola", "gazebo", "arbor", "pavilion",
            "outdoor kitchen",
        ],
        "medium": [
            "pool", "spa ", "concrete deck",
            "patio", " deck", "turf", "sod", "drainage", "grade",
            "pavement", "landscape",
        ],
    },
    "general_construction": {
        "primary": [
            "new construction",
            "new single family", "new residence", "new home",
            "new commercial building", "new office building",
            "tenant improvement", "finish out", "build-out", "build out",
            "fire restoration", "fire damage restoration",
            "foundation repair", "structural repair",
            "roof replacement", "re-roof", "reroof",
            "accessory dwelling", "adu", "in-law suite", "casita", "guest house",
            "ada compliance", "accessibility upgrade",
        ],
        "high": [
            "remodel", "renovation", "addition",
            "demolition", "structural", "foundation",
            "framing", "load bearing",
            "drywall", "insulation", "flooring", "siding", "stucco",
            "roofing", "window replacement", "door replacement",
            "egress window", "fire damage", "storm damage",
            "attached garage", "detached garage", "carport",
            "accessory structure",
            "eplan", "residential expedited review",
            "commercial expedited review",
        ],
        "medium": [
            "repair", "interior", "exterior",
            "residential", "commercial", "shed ", "balcony",
            "stairway", "handrail", "guardrail",
        ],
    },
}

# Permit type → category bonus (description keywords take priority)
PERMIT_TYPE_BONUS = {
    "ep": ("electrical", 4),
    "pp": ("plumbing", 4),
    "mp": ("mechanical", 4),
    "bp": ("general_construction", 3),
    "ds": ("site_landscape", 4),
}

# Contractor trade → category bonus
TRADE_BONUS = {
    "electrical contractor": ("electrical", 4),
    "plumbing contractor": ("plumbing", 4),
    "mechanical contractor": ("mechanical", 4),
    "general contractor": ("general_construction", 4),
}

WEIGHTS = {"primary": 10, "high": 3, "medium": 1}

CATEGORY_LABELS = {
    "general_construction": "General Construction",
    "electrical": "Electrical",
    "plumbing": "Plumbing",
    "mechanical": "Mechanical/HVAC",
    "site_landscape": "Site & Landscape",
}

OUTPUT_FILES = {
    "general_construction": "permits_general_construction.csv",
    "electrical": "permits_electrical.csv",
    "plumbing": "permits_plumbing.csv",
    "mechanical": "permits_mechanical_hvac.csv",
    "site_landscape": "permits_site_landscape.csv",
    "flagged": "permits_flagged_review.csv",
}

AMBIGUITY_THRESHOLD = 0.75


def score_record(record):
    desc = (record.get("description") or "").lower()
    desc = " " + desc + " "

    scores = defaultdict(float)

    for cat, groups in KEYWORDS.items():
        for tier, weight in WEIGHTS.items():
            for kw in groups.get(tier, []):
                if kw in desc:
                    scores[cat] += weight

    ptype = (record.get("permittype") or "").lower()
    bonus = PERMIT_TYPE_BONUS.get(ptype)
    if bonus:
        scores[bonus[0]] += bonus[1]

    trade = (record.get("contractor_trade") or "").lower()
    bonus = TRADE_BONUS.get(trade)
    if bonus:
        scores[bonus[0]] += bonus[1]

    return dict(scores)


def classify_record(record):
    scores = score_record(record)

    if not scores:
        return "general_construction", True, scores

    sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_cat, best_score = sorted_cats[0]

    ambiguous = False
    if best_score <= 0:
        ambiguous = True
    elif len(sorted_cats) > 1:
        second_score = sorted_cats[1][1]
        if second_score > 0 and (second_score / best_score) >= AMBIGUITY_THRESHOLD:
            ambiguous = True

    return best_cat, ambiguous, scores


def load_data(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    return json.loads(raw)


def flatten_record(record):
    flat = {}
    for k, v in record.items():
        flat[k] = json.dumps(v) if isinstance(v, dict) else v
    return flat


def main():
    data_path = "constructionpermits.csv"
    print(f"Loading records from {data_path}...")
    records = load_data(data_path)
    print(f"  Loaded {len(records):,} records")

    buckets = defaultdict(list)
    flagged = []

    for record in records:
        category, ambiguous, scores = classify_record(record)
        record["_assigned_category"] = CATEGORY_LABELS[category]
        record["_ambiguous_flag"] = "YES" if ambiguous else ""
        sorted_cats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        record["_score_top1"] = f"{sorted_cats[0][0]}={sorted_cats[0][1]:.0f}" if sorted_cats else ""
        record["_score_top2"] = (
            f"{sorted_cats[1][0]}={sorted_cats[1][1]:.0f}" if len(sorted_cats) > 1 else ""
        )

        buckets[category].append(record)
        if ambiguous:
            flagged.append(record)

    print("\nClassification summary:")
    total = sum(len(v) for v in buckets.values())
    for cat, label in CATEGORY_LABELS.items():
        n = len(buckets[cat])
        pct = 100 * n / total if total else 0
        print(f"  {label:<25} {n:>5}  ({pct:.1f}%)")
    print(f"  {'Flagged for review':<25} {len(flagged):>5}  ({100*len(flagged)/total:.1f}%)")
    print(f"  {'TOTAL':<25} {total:>5}")

    # Collect all fieldnames in encounter order
    meta_cols = ["_assigned_category", "_ambiguous_flag", "_score_top1", "_score_top2"]
    all_keys, seen = [], set()
    for rec in records:
        for k in rec:
            if k not in seen and k not in meta_cols:
                seen.add(k)
                all_keys.append(k)
    fieldnames = meta_cols + all_keys

    for cat, label in CATEGORY_LABELS.items():
        fname = OUTPUT_FILES[cat]
        rows = buckets[cat]
        with open(fname, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for rec in rows:
                writer.writerow(flatten_record(rec))
        print(f"  Wrote {len(rows):>5} rows → {fname}")

    fname = OUTPUT_FILES["flagged"]
    with open(fname, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in flagged:
            writer.writerow(flatten_record(rec))
    print(f"  Wrote {len(flagged):>5} rows → {fname}")

    print("\nDone.")


if __name__ == "__main__":
    main()
