import math

from typing import NamedTuple


def query_one(items, filter_func):
    for item in items:
        if filter_func(item):
            return item


def query(items, filter_func):
    return [item for item in items if filter_func(item)]


def get_player_race_name(turn):
    player_race_id = turn.rst['player']['raceid']
    races = turn.rst['races']
    race = query_one(races, lambda x: x['id'] == player_race_id)
    return race['adjective']


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
    clans: int # was colonist_population
    nativeclans: int  # was native_population
    temp: int # was planet_temperature
    colonisttaxrate: int # was colonist_tax
    nativetaxrate: int # was native_tax
    colonisthappypoints: int # was colonist_happiness
    nativehappypoints: int  # was native_happiness
    colonistracename: str  # was colonist_race # e.g., "Fed", "Lizard", "Bird Man", etc.
    nativeracename: str # was native_race  # e.g., "Siliconoid", "Amorphous", etc.
    nativegovernment: str # was native_govt


def build_planet_resources(turn, planet_id) -> PlanetResources:
    planet_data = query_one(turn.rst['planets'], lambda x: x['id'] == planet_id)
    args = {k:planet_data[k] for k in PlanetResources._fields}
    return PlanetResources(**args)


def build_planet_colony(turn, planet_id) -> PlanetColony:
    player_race = get_player_race_name(turn)
    planet_data = query_one(turn.rst['planets'], lambda x: x['id'] == planet_id)
    args = {k:planet_data[k] for k in PlanetColony._fields if k != 'colonistracename'}
    args['colonistracename'] = player_race
    return PlanetColony(**args)


def max_mines(population: int) -> int:
    """ maximum number of mines """
    if population <= 200:
        return population
    return round(math.sqrt(population - 200) + 200)


def max_factories(population: int) -> int:
    """ maximum number of factories """
    if population <= 100:
        return population
    return round(math.sqrt(population - 100) + 100)


def max_defense(population: int) -> int:
    """ maximum number of defense posts """
    if population <= 50:
        return population
    return round(math.sqrt(population - 50) + 50)


def pop_to_struct(population: int) -> dict[str,int]:
    """
    Converts population into maximum possible planetary structures.
    
    Parameters:
    - population (int): The number of colonists (in clans).
    
    Returns:
    - dict: A dictionary containing max mines, factories, and defense, with warnings.
    """
    warnings = []
    
    if population > 100000:
        warnings.append("Population cannot normally be higher than 100000 clans")
    
    return {
        "max_mines": max_mines(population),
        "max_factories": max_factories(population),
        "max_defense": max_defense(population),
        "warnings": warnings
    }


def def_to_pop(defense_posts: int) -> dict[str,int]:
    """
    Converts the number of defense posts into the required colonist population.
    
    Parameters:
    - defense_posts (int): The number of desired defense posts.
    
    Returns:
    - dict: A dictionary containing the required population and any warnings.
    """
    warnings = []
    
    if defense_posts > 366:
        warnings.append("Cannot normally have more than 366 defense posts on any planet (with max colonist population of 10,000,000).")
        defense_posts = 366  # Enforce limit
    
    if defense_posts <= 50:
        required_population = defense_posts
    else:
        required_population = (defense_posts - 50) ** 2 + 50
    
    return {
        "required_population": required_population,
        "warnings": warnings
    }


def fac_to_pop(factories: int) -> dict[str,int]:
    """
    Converts the number of factories into the required colonist population.
    
    Parameters:
    - factories (int): The number of desired factories.
    
    Returns:
    - dict: A dictionary containing the required population and any warnings.
    """
    warnings = []
    
    if factories > 416:
        warnings.append("Cannot normally have more than 416 factories on any planet (with max colonist population of 10,000,000).")
        factories = 416  # Enforce limit
    
    if factories <= 100:
        required_population = factories
    else:
        required_population = (factories - 100) ** 2 + 100
    
    return {
        "required_population": required_population,
        "warnings": warnings
    }


def min_to_pop(mines: int) -> dict[str,int]:
    """
    Converts the number of mines into the required colonist population.
    
    Parameters:
    - mines (int): The number of desired mines.
    
    Returns:
    - dict: A dictionary containing the required population and any warnings.
    """
    warnings = []
    
    if mines > 515:
        warnings.append("Cannot normally have more than 515 mines on any planet (with max colonist population of 10,000,000).")
        mines = 515  # Enforce limit
    
    if mines <= 200:
        required_population = mines
    else:
        required_population = (mines - 200) ** 2 + 200
    
    return {
        "required_population": required_population,
        "warnings": warnings
    }


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
    neutroniummined = mine_mineral(resources.groundneutronium, resources.densityneutronium, mines)
    duraniummined = mine_mineral(resources.groundduranium, resources.densityduranium, mines)
    tritaniummined = mine_mineral(resources.groundtritanium, resources.densitytritanium, mines)
    molybdenummined = mine_mineral(resources.groundmolybdenum, resources.densitymolybdenum, mines)

    # Update ground minerals with trans-uranium mutation yield
    new_groundneutronium = resources.groundneutronium - neutroniummined + mutation_yield(resources.densityneutronium)
    new_groundduranium = resources.groundduranium - duraniummined + mutation_yield(resources.densityduranium)
    new_groundtritanium = resources.groundtritanium - tritaniummined + mutation_yield(resources.densitytritanium)
    new_groundmolybdenum = resources.groundmolybdenum - molybdenummined + mutation_yield(resources.densitymolybdenum)

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
        densitymolybdenum=resources.densitymolybdenum
    )


def get_taxation_warnings(colony: PlanetColony, max_colonist_population: int) -> list[str]:
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
    if colony.colonist_happiness < 0 or colony.native_happiness < 0:
        warnings.append("Civil war! Large population losses expected.")
    else:
        # Rioting Threshold
        if colony.colonist_happiness < 30:
            warnings.append("Colonists are rioting! Economic and population growth halted.")

        if colony.native_happiness < 30:
            warnings.append("Natives are rioting! Economic and population growth halted.")

    # Overpopulation Warnings
    if colony.colonist_population > max_colonist_population:
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
    tax, population, race = colony.colonist_tax, colony.colonist_population, colony.colonist_race

    population_penalty = math.sqrt(population)
    tax_penalty = 80 * tax
    temperature_base = 100 if colony.colonist_race == "Crystal" else 50
    temperature_penalty = abs(temperature_base - colony.planet_temperature) * 3
    infrastructure_penalty = (colony.factories + colony.mines) / 3

    return hiss_effect + math.trunc((1000 - population_penalty - tax_penalty - temperature_penalty - infrastructure_penalty) / 100)


def update_native_happiness(colony: PlanetColony, hiss_effect: int, nebula_bonus: bool) -> int:
    """
    Calculates the change in native happiness based on population, taxation, temperature, and infrastructure.

    Natives:
    
    (New Happiness) = (Old Happiness) + TRUNC((1000 - SQRT(Native Clans) - (Native Tax Rate * 85) - TRUNC((Factories + Mines) / 2) - (50 * (10 - Native Government Level))) / 100) + (Native Race Bonus) + (Nebula Bonus) 

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.
    - for_colonists (bool): True to calculate for colonists, else false

    Returns:
    - int: The change in colonist happiness.
    """
    tax, population, race = colony.native_tax, colony.native_population, colony.native_race

    population_penalty = math.sqrt(population)
    tax_penalty = 85 * tax
    infrastructure_penalty = (colony.factories + colony.mines) / 2
    government_penalty = 50 * (10 - colony.native_govt)

    happiness_change = hiss_effect + math.trunc((1000 - population_penalty - tax_penalty - infrastructure_penalty - government_penalty) / 100)

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
    if colony.native_race == "Amorphous" or colony.native_race == "none":
        return 0  # Amorphous natives and no natives generate no tax income.

    base_income = colony.native_population / 100
    # The Borg can only earn taxes at a maximum of 20%, even if a higher tax rate is set.
    tax_rate = min(20, colony.native_tax) if colony.colonist_race == "Borg" else colony.native_tax

    native_tax_income = round(base_income * (tax_rate / 10) * (native_government / 5))

    # Tax income cannot exceed the number of colonists present.
    return min(colony.colonist_population, native_tax_income)


def update_colony(colony: PlanetColony, hiss_effect=0, nebula_bonus=False) -> tuple[PlanetColony, list[str]]:
    """
    Calculates the effect of taxation on colonists and natives, including happiness, growth, and economy.

    Parameters:
    - colony (PlanetColony): The current state of the planetary colony.

    Returns:
    - tuple[PlanetColony, list[str]]: Updated colony state and a list of warnings.
    """
    warnings = []

    def max_hiss_effect(happiness: int, hiss_effect: int) -> int:
        return min(100 - happiness, hiss_effect)

    colonist_hiss_effect = max_hiss_effect(colony.colonist_happiness, hiss_effect)
    native_hiss_effect = max_hiss_effect(colony.native_happiness, hiss_effect)

    # Happiness Change
    colonist_happiness = min(100, colony.colonist_happiness + update_colonist_happiness(colony, colonist_hiss_effect))
    native_happiness = min(100, colony.native_happiness + update_native_happiness(colony, native_hiss_effect, nebula_bonus))

    # Supplies & Income Calculation
    colonist_tax_income = round(colony.colonist_population / 100 * colony.colonist_tax / 10)
    native_tax_income = calculate_native_tax_income(colony)

    if colonist_happiness <= 30:
        colonist_tax_income = 0
    if native_happiness <= 30:
        native_tax_income = 0

    if colony.native_race == "Insectoid":
        native_tax_income *= 2
    if colony.colonist_race == "Federation":
        native_tax_income *= 2
        colonist_tax_income *= 2
    tax_income = min(5000, native_tax_income + colonist_tax_income)

    colonist_growth = 0
    native_growth = 0
    native_max_population = 0

    # Borg Assimilation
    if colony.colonist_race == "Borg" and colony.native_race != "Amorphous":
        assimilation_rate = 0.01  # Assume 1% assimilation rate
        colonist_growth = min(colony.colonist_population * assimilation_rate, colony.native_population * assimilation_rate)
        native_growth = -colonist_growth

    # Colonist Growth Conditions (Happiness ≥ 70)
    if colony.colonist_happiness >= 70:
        if colony.colonist_race == "Crystal":
            growth_formula = (colony.planet_temperature ** 2) / 4000
        else:
            if 15 <= colony.planet_temperature <= 84:
                growth_formula = math.sin(math.pi * ((100 - colony.planet_temperature) / 100))
            else:
                growth_formula = 0

        colonist_growth += round(
            growth_formula * (colony.colonist_population / 20) * (5 / (colony.colonist_tax + 5))
        )
        colonist_growth = math.trunc(colonist_growth * (phost_growth_rate / 100))

    # Native Growth Conditions (Happiness ≥ 70)
    if colony.native_happiness >= 70:
        if colony.native_race == "Siliconoid":
            native_max_population = colony.planet_temperature * 1000
            native_growth = round(
                (colony.planet_temperature / 100) * (colony.native_population / 25) * (5 / (colony.native_tax + 5))
            )
        else:
            native_max_population = round(math.sin(math.pi * ((100 - colony.planet_temperature) / 100)) * 150000)
            native_growth = round(
                math.sin(math.pi * ((100 - colony.planet_temperature) / 100)) * (colony.native_population / 25) * (5 / (colony.native_tax + 5))
            )

    # Large native population reduces growth
    if colony.native_population > 66000:
        native_growth = round(native_growth / 2)

    # Ensure native growth does not exceed max population
    native_growth = min(native_growth, native_max_population - colony.native_population)

    # Non-Borg natives cannot have negative growth
    if colony.colonist_race != "Borg":
        native_growth = max(0, native_growth)

    # Amorphous natives consume colonists
    if colony.native_race == "Amorphous":
        colonist_growth -= max(5, 100 - colony.native_happiness)

    # Update Population with Growth
    updated_colony = PlanetColony(
        megacredits=new_megacredits,
        supplies=new_supplies,
        factories=colony.factories,
        mines=colony.mines,
        colonist_population=colony.colonist_population + new_colonist_growth,
        native_population=colony.native_population + new_native_growth,
        planet_temperature=colony.planet_temperature,
        colonist_tax=colony.colonist_tax,
        native_tax=colony.native_tax,
        colonist_happiness=new_colonist_happiness,
        native_happiness=new_native_happiness,
        colonist_race=colony.colonist_race,
        native_race=colony.native_race
    )

    return updated_colony, warnings
