import json

from .vgap import query_one

from .econ import (
    PlanetColony,
    calc_native_max_pop,
    calc_native_tax_income,
    calc_native_tax_rate_for_income,
    calc_native_happiness_change,
    calc_native_tax_for_happiness_change,
)

AUTO_TAX_OPTS = {
    "Growth": {
        "minhappy": 70,
        "maxhappy": 100,
        "minoffset": 0,
        "maxoffset": 0,
        "maxpophappy": 70,
    },
    "Growth+": {
        "minhappy": 70,
        "maxhappy": 100,
        "minoffset": -1,
        "maxoffset": 0,
        "maxpophappy": 40,
    },
    "Flat 70": {
        "minhappy": 70,
        "maxhappy": 70,
        "minoffset": 0,
        "maxoffset": 0,
        "maxpophappy": 70,
    },
    "Flat 40": {
        "minhappy": 40,
        "maxhappy": 40,
        "minoffset": 0,
        "maxoffset": 0,
        "maxpophappy": 40,
    },
}


def get_planet_autotax(turn, planet_id):
    "Get the autotax settings for the planet"
    notes = turn.rst["notes"]
    body = query_one(
        notes, lambda n: n["targettype"] == 100 and n["targetid"] == planet_id
    ).get("body", {})
    return json.loads(body).get("name", "")


def calc_auto_tax(colony: PlanetColony, auto_tax: str) -> int:
    """
    Returns the tax percent rate for the given auto_tax (e.g. "Growth" or "Growth+")
    """
    opts = AUTO_TAX_OPTS[auto_tax]

    # If there are no native clans, no native tax is applied.
    if colony.nativeracename in ["Amorphous", "none"]:
        return 0

    if colony.nativeclans == 0:
        return 0

    # Compute maximum income assuming full tax.
    maxincome = calc_native_tax_income(colony, 100)
    maxincome_rate = calc_native_tax_rate_for_income(colony, maxincome)
    maxincome_delta = calc_native_happiness_change(colony, nativetaxrate=maxincome_rate)

    # Check if colony is at or over maximum native population.
    maxpop = calc_native_max_pop(colony)
    if colony.nativeclans >= maxpop:
        if colony.nativehappypoints + maxincome_delta >= opts["maxpophappy"]:
            return maxincome_rate
        return calc_native_tax_for_happiness_change(
            colony, opts["maxpophappy"] - colony.nativehappypoints
        )

    # Calculate the maximum happiness change with 0% tax.
    maxhappychange = calc_native_happiness_change(colony, nativetaxrate=0)

    # Calculate the minimum happiness target.
    mintarget = opts["minhappy"]
    if opts["minoffset"]:
        # for Growth+ the effective minimum target is reduced by the maximum potential change
        mintarget += opts["minoffset"] * maxhappychange

    # if taxing at max rate won’t drop happiness below minimum target, tax at the maximum rate
    if colony.nativehappypoints + maxincome_delta >= mintarget:
        return maxincome_rate

    # calculate the maximum happiness target.
    maxtarget = opts["maxhappy"]
    if opts["maxoffset"]:
        maxtarget += opts["maxoffset"] * maxhappychange

    # If the happiness with no tax is below target, then no tax is applied.
    if colony.nativehappypoints + maxhappychange <= maxtarget:
        return 0

    # Finally, decide on the tax rate.
    if colony.nativehappypoints + maxincome_delta >= mintarget:
        return maxincome_rate
    else:
        return calc_native_tax_for_happiness_change(
            colony, mintarget - colony.nativehappypoints
        )
