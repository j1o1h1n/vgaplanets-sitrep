import math

from typing import NamedTuple

from .vgap import query_one


def get_player_race_name(turn):
    player_race_id = turn.rst["player"]["raceid"]
    races = turn.rst["races"]
    race = query_one(races, lambda x: x["id"] == player_race_id)
    return race["adjective"]


class PlanetResources(NamedTuple):
    """Represents the resources of a planet."""

    neutronium: int
    duranium: int
    tritanium: int
    molybdenum: int
    groundneutronium: int
    groundduranium: int
    groundtritanium: int
    groundmolybdenum: int
    # density params are Percentage (0-100) values
    densityneutronium: int
    densityduranium: int
    densitytritanium: int
    densitymolybdenum: int


class PlanetColony(NamedTuple):
    """Represents the state of a planetary colony."""

    megacredits: int
    supplies: int
    factories: int
    mines: int
    clans: int
    nativeclans: int
    temp: int
    colonisttaxrate: int
    nativetaxrate: int
    colonisthappypoints: int
    nativehappypoints: int
    colonistracename: str  # e.g., "Fed", "Lizard", "Bird Man", etc.
    nativeracename: str  # e.g., "Siliconoid", "Amorphous", etc.
    nativegovernment: str


def build_planet_resources(turn, planet_id) -> PlanetResources:
    planet_data = query_one(turn.rst["planets"], lambda x: x["id"] == planet_id)
    args = {k: planet_data[k] for k in PlanetResources._fields}
    return PlanetResources(**args)


def build_planet_colony(turn, planet_id) -> PlanetColony:
    player_race = get_player_race_name(turn)
    planet_data = query_one(turn.rst["planets"], lambda x: x["id"] == planet_id)
    args = {k: planet_data[k] for k in PlanetColony._fields if k != "colonistracename"}
    args["colonistracename"] = player_race
    return PlanetColony(**args)


def update_mining(resources: PlanetResources, mines: int) -> PlanetResources:
    """
    Calculates the updated planetary resource state after mining.

    Parameters:
    - resources (PlanetResources): The current resource state of the planet.
    - mines (int): The number of operational mines.

    Returns:
    - PlanetResources: Updated planetary resources after production.
    """

    def mine_mineral(ground: int, density: int, mines: int) -> int:
        """Determines the amount of mineral mined given density and ground availability."""
        return min(ground, round(density / 100 * mines))

    def mutation_yield(density: int) -> int:
        """Determines trans-uranium mutation yield based on density."""
        return math.ceil(density / 20)

    # Calculate mining output
    neutroniummined = mine_mineral(
        resources.groundneutronium, resources.densityneutronium, mines
    )
    duraniummined = mine_mineral(
        resources.groundduranium, resources.densityduranium, mines
    )
    tritaniummined = mine_mineral(
        resources.groundtritanium, resources.densitytritanium, mines
    )
    molybdenummined = mine_mineral(
        resources.groundmolybdenum, resources.densitymolybdenum, mines
    )

    # Update ground minerals with trans-uranium mutation yield
    new_groundneutronium = (
        resources.groundneutronium
        - neutroniummined
        + mutation_yield(resources.densityneutronium)
    )
    new_groundduranium = (
        resources.groundduranium
        - duraniummined
        + mutation_yield(resources.densityduranium)
    )
    new_groundtritanium = (
        resources.groundtritanium
        - tritaniummined
        + mutation_yield(resources.densitytritanium)
    )
    new_groundmolybdenum = (
        resources.groundmolybdenum
        - molybdenummined
        + mutation_yield(resources.densitymolybdenum)
    )

    return PlanetResources(
        neutronium=resources.neutronium + neutroniummined,
        duranium=resources.duranium + duraniummined,
        tritanium=resources.tritanium + tritaniummined,
        molybdenum=resources.molybdenum + molybdenummined,
        groundneutronium=new_groundneutronium,
        groundduranium=new_groundduranium,
        groundtritanium=new_groundtritanium,
        groundmolybdenum=new_groundmolybdenum,
        densityneutronium=resources.densityneutronium,
        densityduranium=resources.densityduranium,
        densitytritanium=resources.densitytritanium,
        densitymolybdenum=resources.densitymolybdenum,
    )


def get_taxation_warnings(
    colony: PlanetColony, max_colonist_population: int
) -> list[str]:
    """
    Generates warnings based on taxation effects, population constraints, and planetary conditions.

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.
    - max_colonist_population (int): Maximum colonist population allowed by planet conditions.

    Returns:
    - list[str]: A list of warning messages.
    """
    warnings = []

    # Civil War Condition
    if colony.colonisthappypoints < 0 or colony.nativehappypoints < 0:
        warnings.append("Civil war! Large population losses expected.")
    else:
        # Rioting Threshold
        if colony.colonisthappypoints < 30:
            warnings.append(
                "Colonists are rioting! Economic and population growth halted."
            )

        if colony.nativehappypoints < 30:
            warnings.append(
                "Natives are rioting! Economic and population growth halted."
            )

    # Overpopulation Warnings
    if colony.clans > max_colonist_population:
        warnings.append("Colonist population exceeds maximum planetary capacity.")

        if colony.supplies == 0:
            warnings.append("Overpopulated colonists will die due to lack of supplies.")

    return warnings


def update_colonist_happiness(colony: PlanetColony, hiss_effect: int) -> int:
    """
    Calculates the change in colonist happiness based on population, taxation, temperature, and infrastructure.

    Colonists:

    (New Happiness) = (Old Happiness) + TRUNC((1000 - SQRT(Colonist Clans) - 80 * (Colonist Tax Rate) - ABS(BaseTemp - Temperature) * 3 - (Factories + Mines) / 3 ) /100)

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.
    - hiss_effect (int): hiss effect

    Returns:
    - int: The change in colonist happiness.
    """
    tax, population, race = (
        colony.colonisttaxrate,
        colony.clans,
        colony.colonistracename,
    )

    population_penalty = math.sqrt(population)
    tax_penalty = 80 * tax
    temperature_base = 100 if race == "Crystal" else 50
    temperature_penalty = abs(temperature_base - colony.temp) * 3
    infrastructure_penalty = (colony.factories + colony.mines) / 3

    return hiss_effect + math.trunc(
        (
            1000
            - population_penalty
            - tax_penalty
            - temperature_penalty
            - infrastructure_penalty
        )
        / 100
    )


def update_native_happiness(
    colony: PlanetColony, hiss_effect: int, nebula_bonus: bool
) -> int:
    """
        Calculates the change in native happiness based on population, taxation, temperature, and infrastructure.

        Natives:

        (New Happiness) = (Old Happiness) + TRUNC((1000 - SQRT(Native Clans) - (Native Tax Rate * 85) - TRUNC((Factories + Mines) / 2) - (5
    Bonus) + (Nebula Bonus)

        Parameters:
        - colony (PlanetColony): The current state of the planetary colony.
        - for_colonists (bool): True to calculate for colonists, else false

        Returns:
        - int: The change in colonist happiness.
    """
    tax, population, race = (
        colony.nativetaxrate,
        colony.nativeclans,
        colony.nativeracename,
    )

    population_penalty = math.sqrt(population)
    tax_penalty = 85 * tax
    infrastructure_penalty = (colony.factories + colony.mines) / 2
    government_penalty = 50 * (10 - int(colony.nativegovernment))

    happiness_change = hiss_effect + math.trunc(
        (
            1000
            - population_penalty
            - tax_penalty
            - infrastructure_penalty
            - government_penalty
        )
        / 100
    )

    if race == "Avian":
        happiness_change += 10
    if nebula_bonus:
        happiness_change += 5

    return happiness_change


def calculate_native_tax_income(colony: PlanetColony) -> int:
    """
    Calculates the native tax income based on population, race, tax scale, and government type.

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.

    Returns:
    - int: The calculated native tax income.
    """
    if colony.nativeracename == "Amorphous" or colony.nativeracename == "none":
        return 0  # Amorphous natives and no natives generate no tax income.

    base_income = colony.nativeclans / 100
    tax_rate = (
        min(20, colony.nativetaxrate)
        if colony.colonistracename == "Cyborg"
        else colony.nativetaxrate
    )

    native_tax_income = round(
        base_income * (tax_rate / 10) * (int(colony.nativegovernment) / 5)
    )

    # Tax income cannot exceed the number of colonists present.
    return min(colony.clans, native_tax_income)


def update_colony(
    colony: PlanetColony, hiss_effect=0, nebula_bonus=False
) -> tuple[PlanetColony, list[str]]:
    """
    Calculates the effect of taxation on colonists and natives, including happiness, growth, and economy.

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.

    Returns:
    - tuple[PlanetColony, list[str]]: Updated colony state and a list of warnings.
    """
    warnings: list[str] = []

    def max_hiss_effect(happiness: int, hiss_effect: int) -> int:
        return min(100 - happiness, hiss_effect)

    colonist_hiss_effect = max_hiss_effect(colony.colonisthappypoints, hiss_effect)
    native_hiss_effect = max_hiss_effect(colony.nativehappypoints, hiss_effect)

    # Happiness Change
    new_colonist_happiness = min(
        100,
        colony.colonisthappypoints
        + update_colonist_happiness(colony, colonist_hiss_effect),
    )
    new_native_happiness = min(
        100,
        colony.nativehappypoints
        + update_native_happiness(colony, native_hiss_effect, nebula_bonus),
    )

    # Supplies & Income Calculation
    colonist_tax_income = round(colony.clans / 100 * colony.colonisttaxrate / 10)
    native_tax_income = calculate_native_tax_income(colony)

    if new_colonist_happiness <= 30:
        colonist_tax_income = 0
    if new_native_happiness <= 30:
        native_tax_income = 0

    if colony.nativeracename == "Insectoid":
        native_tax_income *= 2
    if colony.colonistracename == "Fed":
        native_tax_income *= 2
        colonist_tax_income *= 2
    tax_income = min(5000, native_tax_income + colonist_tax_income)

    colonist_growth = 0
    native_growth = 0
    native_max_population = 0

    # Borg Assimilation
    if colony.colonistracename == "Cyborg" and colony.nativeracename != "Amorphous":
        assimilation_rate = 1.0  # 100%
        colonist_growth = round(
            min(
                colony.clans * assimilation_rate, colony.nativeclans * assimilation_rate
            )
        )
        native_growth = -colonist_growth

    # Colonist Growth Conditions (Happiness ≥ 70)
    if colony.colonisthappypoints >= 70:
        if colony.colonistracename == "Crystalline":
            growth_rate = (colony.temp**2) / 4000
        else:
            if 15 <= colony.temp <= 84:
                growth_rate = math.sin(math.pi * ((100 - colony.temp) / 100))
            else:
                growth_rate = 0

        pop = colony.clans / 20
        tax = 5 / (colony.colonisttaxrate + 5)
        colonist_growth += round(growth_rate * pop * tax)
        colonist_growth = math.trunc(colonist_growth)

    # Native Growth Conditions (Happiness ≥ 70)
    if colony.nativehappypoints >= 70:
        if colony.nativeracename == "Siliconoid":
            native_max_population = colony.temp * 1000
            native_growth_rate = colony.temp / 100
        else:
            native_max_population = round(
                math.sin(math.pi * ((100 - colony.temp) / 100)) * 150000
            )
            native_growth_rate = math.sin(math.pi * ((100 - colony.temp) / 100))

        pop = colony.nativeclans / 20
        tax = 5 / (colony.nativetaxrate + 5)
        native_growth += round(native_growth_rate * pop * tax)

    # Large native population reduces growth
    if colony.nativeclans > 66000 and native_growth > 0:
        native_growth = round(native_growth / 2)

    # Ensure native growth does not exceed max population
    native_growth = min(native_growth, native_max_population - colony.nativeclans)

    # Non-Borg natives cannot have negative growth
    if colony.colonistracename != "Cyborg":
        native_growth = max(0, native_growth)

    # Amorphous natives consume colonists
    if colony.nativeracename == "Amorphous":
        colonist_growth -= max(5, 100 - colony.nativehappypoints)

    colonist_cur_max_pop = -1
    climate_death_rate = 0.1
    if colony.colonistracename == "Crystalline":
        # Crystaline formula (likes 100° planets)
        colonist_abs_max_pop = round(colony.temp * 1000)
    else:
        # Non-Crystaline formula (likes 50° planets)
        colonist_abs_max_pop = round(
            math.sin(math.pi * ((100 - colony.temp) / 100)) * 100000
        )
        if colony.temp > 84:
            colonist_abs_max_pop = math.trunc(
                (20099.9 - (200 * colony.temp)) * climate_death_rate
            )
            colonist_cur_max_pop = (
                colony.clans
                - math.trunc(colony.clans * climate_death_rate)
                - 2 * (100 - colony.temp)
            )
        elif colony.temp < 15:
            colonist_abs_max_pop = math.trunc(
                (299.9 + (200 * colony.temp)) * climate_death_rate
            )
            colonist_cur_max_pop = (
                colony.clans
                - math.trunc(colony.clans * climate_death_rate)
                - 2 * (1 + colony.temp)
            )
    if colony.temp <= 19 and colony.colonistracename == "Rebels":
        # Rebels can have up to 90,000 clans (9 million colonists) on any planet
        # with a temperature of 19 degrees or less
        colonist_abs_max_pop = max(colonist_abs_max_pop, 90000)
    colonist_cur_max_pop = max(colonist_abs_max_pop, colonist_cur_max_pop)
    if colony.colonistracename in ["Fury", "Robots", "Rebels", "Colonies"]:
        colonist_abs_max_pop = max(colonist_abs_max_pop, 60)
    if colonist_cur_max_pop == -1:
        colonist_cur_max_pop = colonist_abs_max_pop

    # update supplies
    new_supplies = colony.factories
    if colony.nativeracename == "Bovinoid":
        new_supplies += min(colony.clans, math.trunc(colony.nativeclans / 100))

    # If the planet/planetoid has more population that the maximum, the excess population
    # will either need to have supplies present, or some of them will die.

    # The number of clans that can be supported by supplies can be calculated as follows:
    #    (Clans Supported By Supplies) = ROUND((Planet Supplies) / 4)
    clans_supported_by_supplies = round(colony.supplies / 4)
    colonist_cur_max_pop = colonist_abs_max_pop + clans_supported_by_supplies
    supplies_consumed = 0
    if colony.clans > colonist_cur_max_pop:
        clans_killed = math.ceil((colony.clans - colonist_cur_max_pop) / 10)
        colonist_growth = -clans_killed
        supplies_consumed = 1 + math.trunc((colony.clans - colonist_cur_max_pop) / 400)

    if colonist_growth > 0 and colony.clans > colonist_abs_max_pop:
        colonist_growth = 0

    # civil war
    if new_colonist_happiness < 0 or new_native_happiness < 0:
        # A number of colonists and natives are killed when either natives or
        # colonists are at civil war.
        # This means that if colonists are in civil war they kill both colonists
        # and natives; when natives are in civil war they kill both natives and colonists.
        # For each turn that natives and/or colonists are in civil war, 30% of
        # the population plus an additional 100 clans (of both the native and
        # the colonist population) are killed.
        # Amorphous natives are not killed during civil wars.
        colonist_growth -= round(colony.clans * 0.3) + 100
        if colony.nativeracename != "Amorphous":
            native_growth -= round(colony.nativeclans * 0.3) + 100

    # update pops, supplies, happiness
    new_megacredits = max(0, colony.megacredits + tax_income)
    new_supplies = max(0, colony.supplies + new_supplies - supplies_consumed)
    new_colonist_clans = max(0, colony.clans + colonist_growth)
    new_native_clans = max(0, colony.nativeclans + native_growth)

    updated_colony = PlanetColony(
        megacredits=new_megacredits,
        supplies=new_supplies,
        factories=colony.factories,
        mines=colony.mines,
        clans=new_colonist_clans,
        nativeclans=new_native_clans,
        temp=colony.temp,
        colonisttaxrate=colony.colonisttaxrate,
        nativetaxrate=colony.nativetaxrate,
        colonisthappypoints=new_colonist_happiness,
        nativehappypoints=new_native_happiness,
        colonistracename=colony.colonistracename,
        nativeracename=colony.nativeracename,
        nativegovernment=colony.nativegovernment,
    )

    return updated_colony, warnings
