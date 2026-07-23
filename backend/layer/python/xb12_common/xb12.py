"""
XB12 INSTRUCTIONAL-MATERIAL-COST classification.

Implements the decision tree for the California Community Colleges MIS data
element XB12 (see Data/XB12-Data-Element-Dictionary.md). The code is derived
for a *section* (course) from the full set of course materials adopted for it.

Coding values (FIELD CHECK: A, C, D, E, F, G, Y)
  A  Section has no associated course material
  C  Section has course material costs, none of which are passed on to students
  D  Section has low course material costs (as defined locally)          [LTC]
  E  Section uses only no-cost, OER course material                       [ZTC]
  F  Section uses only no-cost digital course material that is not OER
  G  Section uses a mix of no-cost OER and other cost-bearing resources,
     but no costs are passed to the student
  Y  Section does not meet no-cost or low-cost course material criteria

Note: code "B" was removed Summer 2024 and is intentionally not produced.
"""

from decimal import Decimal, InvalidOperation

# Locally-defined "low cost" ceiling (dollars). Overridable per deployment.
DEFAULT_LOW_COST_THRESHOLD = Decimal("50")

# Recognised per-material cost categories supplied by the UI / caller.
COST_TYPES = ("oer", "free_non_oer", "subsidized", "priced")

XB12_MEANINGS = {
    "A": "Section has no associated course material",
    "C": "Section has course material costs, none of which are passed on to students",
    "D": "Section has low course material costs (as defined locally)",
    "E": "Section uses only no-cost, OER course material",
    "F": "Section uses only no-cost digital course material that does not meet OER guidelines",
    "G": "Section uses a mix of no-cost OER and other cost-bearing resources, but no costs are passed to the student",
    "Y": "Section does not meet no-cost or low-cost course material criteria",
}


def _to_decimal(value):
    """Best-effort conversion of a price-like value to Decimal (0 on failure)."""
    if value is None or value == "":
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")


def normalize_material(material):
    """
    Normalise a single material dict into the fields the classifier needs.

    Expected input keys (all optional, sensible defaults applied):
      costType : one of COST_TYPES. If absent it is inferred from price/oer/url.
      price    : list/retail price of the material (number or numeric string)
      isOER    : bool - explicitly flags an Open Educational Resource
      url      : platform / resource URL (used to infer a free digital resource)
      isbn     : ISBN of a physical/commercial textbook

    Returns a dict with derived booleans and the student-facing cost.
    """
    cost_type = (material.get("costType") or "").strip().lower()
    price = _to_decimal(material.get("price"))
    is_oer_flag = bool(material.get("isOER"))
    has_url = bool((material.get("url") or "").strip())

    # Infer a cost type when the caller did not provide an explicit one.
    if cost_type not in COST_TYPES:
        if is_oer_flag:
            cost_type = "oer"
        elif price > 0:
            cost_type = "priced"
        elif has_url:
            cost_type = "free_non_oer"
        else:
            cost_type = "free_non_oer"

    is_oer = cost_type == "oer"
    is_free_digital_non_oer = cost_type == "free_non_oer"
    # A resource that inherently costs money (whether or not the student pays).
    is_cost_bearing = cost_type in ("priced", "subsidized") or price > 0
    # What the student actually pays out of pocket.
    student_cost = price if cost_type == "priced" else Decimal("0")

    return {
        "costType": cost_type,
        "price": price,
        "studentCost": student_cost,
        "isOER": is_oer,
        "isFreeDigitalNonOER": is_free_digital_non_oer,
        "isCostBearing": is_cost_bearing,
    }


def classify(materials, low_cost_threshold=DEFAULT_LOW_COST_THRESHOLD):
    """
    Compute the XB12 code for a section given the list of adopted materials.

    Args:
        materials: list of material dicts (see normalize_material).
        low_cost_threshold: locally-defined ceiling for the "low cost" (D) code.

    Returns:
        (code, explanation) tuple.
    """
    threshold = _to_decimal(low_cost_threshold) or DEFAULT_LOW_COST_THRESHOLD

    if not materials:
        return "A", "No course materials were adopted for this section."

    norm = [normalize_material(m) for m in materials]

    total_student_cost = sum((m["studentCost"] for m in norm), Decimal("0"))
    any_oer = any(m["isOER"] for m in norm)
    all_oer = all(m["isOER"] for m in norm)
    any_cost_bearing = any(m["isCostBearing"] for m in norm)
    any_free_digital_non_oer = any(m["isFreeDigitalNonOER"] for m in norm)

    # ---- Branch 1: nothing is passed on to the student -------------------
    if total_student_cost <= 0:
        if all_oer:
            return "E", "All materials are no-cost Open Educational Resources."

        if any_oer and any_cost_bearing:
            return (
                "G",
                "Mix of no-cost OER and other cost-bearing resources, "
                "but no costs are passed to the student.",
            )

        if any_cost_bearing:
            # Cost-bearing materials exist but the college absorbs the cost,
            # and there is no OER in the mix.
            return (
                "C",
                "Section has course material costs, none of which are "
                "passed on to students.",
            )

        # No cost-bearing materials at all and not all OER: free digital
        # resources, possibly mixed with some OER.
        if any_oer:
            return (
                "G",
                "Mix of no-cost OER and other no-cost resources; "
                "no costs are passed to the student.",
            )
        return (
            "F",
            "Section uses only no-cost digital course material that does "
            "not meet OER guidelines.",
        )

    # ---- Branch 2: the student pays something ----------------------------
    if total_student_cost <= threshold:
        return (
            "D",
            "Section has low course material costs "
            "(${:.2f} <= ${:.2f} local threshold).".format(
                total_student_cost, threshold
            ),
        )

    return (
        "Y",
        "Section does not meet no-cost or low-cost course material criteria "
        "(student cost ${:.2f}).".format(total_student_cost),
    )


# Map legacy / friendly cost-status markings to official XB12 letter codes.
MARKING_TO_CODE = {
    "ZTC-OER": "E",   # zero textbook cost via OER -> only no-cost OER material
    "ZTC": "E",
    "LTC": "D",       # low textbook cost -> low course material cost
    "STANDARD": "Y",  # regular priced -> does not meet no/low-cost criteria
    "NONE": "A",      # no material
}


# Known Open Educational Resource publishers / repositories. A resource whose
# title, publisher, author, or URL matches one of these is treated as no-cost
# OER (XB12 code E), per the OER knowledge-source strategy (OpenStax,
# LibreTexts, Pressbooks, etc.).
OER_MARKERS = (
    "openstax",
    "libretext",           # matches "libretext" and "libretexts"
    "pressbooks",
    "oercommons",
    "oer commons",
    "open education",
    "open educational resource",
    "open textbook",
    "opentextbook",
    "creative commons",
    "merlot",
    "saylor",
    "open.umn.edu",        # Open Textbook Library
    "milne open textbooks",
    "openstax.org",
    "libretexts.org",
)


def is_oer_source(*parts):
    """True if any of the given text fields indicates an OER publisher/source."""
    haystack = " ".join(str(p) for p in parts if p).lower()
    if not haystack.strip():
        return False
    return any(marker in haystack for marker in OER_MARKERS)


def code_from_marking(marking):
    """Return the XB12 letter code for a friendly marking, or None if unknown."""
    if not marking:
        return None
    return MARKING_TO_CODE.get(str(marking).strip().upper())


def is_letter_code(code):
    """True if the value is already an official XB12 letter code."""
    return isinstance(code, str) and code.strip().upper() in XB12_MEANINGS


def zero_low_cost_marking(code):
    """
    Map an XB12 code to the friendly Zero/Low Textbook Cost marking used in
    catalogs (ZTC = zero textbook cost, LTC = low textbook cost).
    """
    if code in ("E", "F", "G", "C"):
        return "ZTC"
    if code == "D":
        return "LTC"
    return ""  # A (no material) or Y (standard cost) have no ZTC/LTC marking
