"""
See https://help.planets.nu/API for the APi
"""

import time
import requests
import httpx
import sqlite3
import json
import logging
import datetime
import io
import zipfile

from typing import NamedTuple, Optional, Any
from pathlib import Path

from . import space

logger = logging.getLogger(__name__)

type GAME_ID = int
type PLAYER_ID = int
type TURN_ID = int
type SHIP_ID = int
type PLANET_ID = int
type STARBASE_ID = int
type PLANET = dict[str, Any]
type SHIP = dict[str, Any]
type STARBASE = dict[str, Any]
type PLANET_SHIP_MAP = dict[PLANET_ID, list[SHIP]]
type RGB = str
type SCORES = dict[PLAYER_ID, dict[TURN_ID, "Score"]]
type TURNS = dict[PLAYER_ID, dict[TURN_ID, "Turn"]]

ONE_HOUR_SECS = 60 * 60

LOAD_TURN = "http://api.planets.nu/game/loadturn"

# req = requests.get("http://api.planets.nu/game/loadturn", data=dict(gameid=game['id'], apikey=account['apikey']))

TABLES = {
    "settings": """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT NOT NULL PRIMARY KEY,
            data JSON NOT NULL
        );""",
    "games": """
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            data JSON NOT NULL,
            meta JSON NOT NULL,
            info JSON NOT NULL
        );""",
    "turns": """
        CREATE TABLE IF NOT EXISTS turns (
            game_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            turn INTEGER NOT NULL,
            data JSON NOT NULL,
            PRIMARY KEY (game_id, player_id, turn)
        );""",
}

INSERT_GAME = """
REPLACE INTO games (game_id, name, meta, data, info)
VALUES (?, ?, ?, ?, ?);
"""

INSERT_TURN = """
REPLACE INTO turns (game_id, player_id, turn, data)
VALUES (?, ?, ?, ?);
"""

# minimum last_updated value where status is 2
LAST_UPDATED = """select COALESCE(JSON_EXTRACT(meta, '$.last_updated'), 0) last_updated,
JSON_EXTRACT(data, '$.status') status
from games where status = 2"""


def query_one(items, filter_func):
    for item in items:
        if filter_func(item):
            return item


def query(items, filter_func):
    return [item for item in items if filter_func(item)]


def get_player_race_name(turn: "Turn") -> str:
    "returns the adjective name for the player race"
    race_id = turn.data["player"]["raceid"]
    race = query_one(turn.data["races"], lambda x: x["id"] == race_id)
    return race["adjective"]


def get_diplomacy_color(turn: "Turn", player_id: PLAYER_ID) -> RGB:
    """Get the colour set in the Planets Nu diplomacy tab"""
    val = query_one(turn.data["relations"], lambda rel: rel["playertoid"] == player_id)[
        "color"
    ]
    return "#" + val if val else "#68e891"


class Score(NamedTuple):
    turn_id: int
    player_id: int
    planets: int
    planets_delta: int
    starbases: int
    starbases_delta: int
    capital_ships: int
    capital_ships_delta: int
    civilian_ships: int
    civilian_ships_delta: int
    military_score: int
    military_score_delta: int
    score: int
    score_delta: int
    pp: int
    pp_delta: int


def configure_wal(conn: sqlite3.Connection) -> sqlite3.Connection:
    # enables write-ahead log so that your reads do not block writes and vice-versa.
    conn.execute("pragma journal_mode=wal")

    # sqlite will wait 0.5 seconds to obtain a lock before returning SQLITE_BUSY errors, which will significantly reduce them.
    conn.execute("pragma busy_timeout = 500")

    # sqlite will sync less frequently and be more performant, still safe to use because of the enabled WAL mode.
    conn.execute("pragma synchronous = NORMAL")

    # negative number means kilobytes, in this case 20MB of memory for cache.
    conn.execute("pragma cache_size = -20000")

    # because of historical reasons foreign keys are disabled by default, we should manually enable them.
    conn.execute("pragma foreign_keys = true")

    # moves temporary tables from disk into RAM, speeds up performance a lot.
    conn.execute("pragma temp_store = memory")

    return conn


def load_api_key():
    api_key_path = Path.home() / ".vgap.apikey"
    if not Path(api_key_path).exists():
        return None
    return json.loads(open(api_key_path).read())


def save_api_key(account):
    api_key_path = Path.home() / ".vgap.apikey"
    with open(api_key_path, "w") as f:
        f.write(json.dumps(account))


def get_ts(td: Optional[datetime.timedelta] = None) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    if td:
        dt = dt + td
    return dt.isoformat(" ", "seconds")


def create_score(data: dict[str, int]) -> Score:
    """
    Creates a Score object from a given dictionary of game data.

    Parameters:
    - data (dict): Dictionary containing game state values.

    Returns:
    - Score: A named tuple representing the player's score for the turn.
    """
    return Score(
        turn_id=data.get("turn", 0),
        player_id=data.get("ownerid", 0),
        planets=data.get("planets", 0),
        planets_delta=data.get("planetchange", 0),
        starbases=data.get("starbases", 0),
        starbases_delta=data.get("starbasechange", 0),
        capital_ships=data.get("capitalships", 0),
        capital_ships_delta=data.get("shipchange", 0),
        civilian_ships=data.get("freighters", 0),
        civilian_ships_delta=data.get("freighterchange", 0),
        military_score=data.get("militaryscore", 0),
        military_score_delta=data.get("militarychange", 0),
        score=data.get("inventoryscore", 0),
        score_delta=data.get("inventorychange", 0),
        pp=data.get("prioritypoints", 0),
        pp_delta=data.get("prioritypointchange", 0),
    )


class Player(NamedTuple):
    player_id: PLAYER_ID
    race_id: int
    name: str
    race: str
    color: RGB
    short_name: str
    adjective: str


class Turn:

    def __init__(self, player_id: PLAYER_ID, turn_id: TURN_ID, data: dict[str, Any]):
        self.player_id = player_id
        self.turn_id = turn_id
        if "rst" in data:
            data = data["rst"]
        self.data = data
        self._cluster: space.Cluster | None = None

    def filter_objs(
        self, category: str, filter_key: str, filter_value: int | None
    ) -> list:
        """Helper function to filter objects by owner ID."""
        if filter_value is None:
            return self.data[category]
        return [obj for obj in self.data[category] if obj[filter_key] == filter_value]

    def stockpile(self, rsrc: str, player_id: PLAYER_ID | None = None) -> int:
        "Returns the total amount of the given resource, on owned planets and ships"
        if player_id is None:
            player_id = self.player_id
        val = sum([p.get(rsrc, 0) for p in self.planets(player_id)])
        val += sum([s.get(rsrc, 0) for s in self.ships(player_id)])
        return val

    def ships(self, player_id: PLAYER_ID | None = None) -> list[SHIP]:
        """Return all ships owned by the specified player, or all ships if no player_id specified."""
        return self.filter_objs("ships", "ownerid", player_id)

    def planets(self, player_id: PLAYER_ID | None = None) -> list[PLANET]:
        """Return all planets owned by the specified player, or all planets if no player_id specified."""
        return self.filter_objs("planets", "ownerid", player_id)

    def starbases(self, player_id: PLAYER_ID | None = None) -> list[STARBASE]:
        """Return all starbases owned by the specified player, or all starbases if no player_id specified."""
        starbases = self.data["starbases"]
        if player_id:
            planet_ids = {p["id"] for p in self.planets(player_id)}
            starbases = [s for s in starbases if s["planetid"] in planet_ids]
        return starbases

    def cluster(self) -> "space.Cluster":
        if self._cluster is None:
            self._cluster = space.Cluster(self)
        return self._cluster

    def sectors(self) -> "space.Clique":
        return self.cluster().cliques


# game status codes
STATUS_JOINING, STATUS_RUNNING, STATUS_FINISHED, STATUS_HOLS = range(1, 5)


class Game:

    def __init__(
        self,
        game_id: GAME_ID,
        name: str,
        meta: dict,
        data: dict,
        turns: TURNS,
        info: dict,
    ):
        self.game_id = game_id
        self.name = name
        self.meta = meta
        self.data = data
        self.info = info
        self._turns = turns

        # get player information from 4th turn unless not available
        model_turn = self._turns.get(self.meta["player_id"], {}).get(4)
        if not model_turn:
            return
        races = model_turn.data["races"]
        self.races = {r["id"]: r for r in races}
        players = model_turn.data["players"]
        self.players = {}
        for p in players:
            race = self.races[p["raceid"]]
            color = get_diplomacy_color(model_turn, p["id"]) if model_turn else "#cccccc"
            player = Player(
                p["id"],
                p["raceid"],
                p["username"],
                race["name"],
                color,
                race["shortname"],
                race["adjective"],
            )
            self.players[p["id"]] = player
        if 0 in self.races:
            del self.races[0]
        if 0 in self.players:
            del self.players[0]

    def turn(
        self, turn_id: TURN_ID | None = None, player_id: PLAYER_ID | None = None
    ) -> Turn:
        """Return the given turn, or latest if no turn specified"""
        if player_id is None:
            player_id = self.meta["player_id"]
        if turn_id is None:
            turn_id = max(self._turns.get(player_id, {}).keys())

        return self._turns[player_id][turn_id]

    def turns(self, player_id: PLAYER_ID | None = None) -> dict[TURN_ID, Turn]:
        """Return the turns for the given player"""
        if player_id is None:
            player_id = self.meta["player_id"]
        return {
            turn_id: self._turns[player_id][turn_id]
            for turn_id in self._turns[player_id]
        }

    def scores(self) -> SCORES:
        res: SCORES = {p: {} for p in self.players}
        if self.info["game"]["status"] == 3:
            # Finished
            for player_id in self.players:
                turns = self.turns(player_id)
                for turn_id in turns:
                    turn = turns[turn_id]
                    data = query_one(
                        turn.data["scores"], lambda sd: sd["ownerid"] == player_id
                    )
                    res[player_id][turn_id] = create_score(data)
        else:
            res = {p: {} for p in self.players}
            turns = self.turns()
            for turn_id in turns:
                turn = turns[turn_id]
                for score_data in turn.data["scores"]:
                    score = create_score(score_data)
                    res[score_data["ownerid"]][turn_id] = score
        return res


class _PlanetsDB:

    def __init__(self, db_file: str):
        self.db_file = db_file
        self.account = load_api_key()
        self.conn = configure_wal(sqlite3.connect(db_file))
        for table in TABLES.values():
            self.conn.execute(table)

    def login(self, username: str, password: str):
        data = dict(username=username, password=password)
        req = requests.post("http://api.planets.nu/account/login", data=data)
        apikey = req.json()["apikey"]
        self.account = {"username": username, "apikey": apikey}
        save_api_key(self.account)
        return self.account

    def close(self):
        # self.conn.execute("PRAGMA wal_checkpoint(FULL);")
        self.conn.close()

    def settings(self):
        cursor = self.conn.cursor()
        try:
            cursor.execute("""select key, data from settings""")
            settings = {}
            for row in cursor:
                settings[row[0]] = json.loads(row[1])
            return settings
        finally:
            cursor.close()

    def save_settings(self, settings: dict):
        """
        Save the provided settings dictionary to the database.

        Args:
            settings (dict): A dictionary where keys are setting names and values are setting data.
        """
        cursor = self.conn.cursor()
        try:
            for key, value in settings.items():
                # Convert the value to a JSON string
                json_data = json.dumps(value)
                # Insert or replace the setting in the database
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO settings (key, data)
                    VALUES (?, ?);
                """,
                    (key, json_data),
                )
            self.conn.commit()
        finally:
            cursor.close()

    def last_updated(self) -> int:
        cursor = self.conn.cursor()
        try:
            return cursor.execute(LAST_UPDATED).fetchone()[0] or 0
        finally:
            cursor.close()

    def requires_update(self) -> bool:
        last_updated = self.last_updated()
        now = int(time.time())
        stale_ts = last_updated + ONE_HOUR_SECS
        return not last_updated or now > stale_ts

    def games(self) -> list[Game]:
        """Returns a list of Game"""
        query = """
        SELECT
            g.name,
            g.game_id,
            g.meta,
            g.data,
            g.info
        FROM games g
        ORDER BY g.name;
        """
        ret = []
        cursor = self.conn.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                name, game_id, meta, data, info = row
                meta = json.loads(meta)
                data = json.loads(data)
                info = json.loads(info)
                ret.append(Game(game_id, name, meta, data, self.turns(game_id), info))
            return ret
        finally:
            cursor.close()

    def game(self, id_or_name: str | int) -> Game:
        """Returns a Game"""
        games = [g for g in self.games() if id_or_name in [g.game_id, g.name]]
        if len(games) == 0:
            raise KeyError(id_or_name)
        return games[0]

    def save(self, game: Game):
        cursor = self.conn.cursor()
        try:
            meta = json.dumps(game.meta)
            data = json.dumps(game.data)
            info = json.dumps(game.info)
            cursor.execute(INSERT_GAME, (game.game_id, game.name, meta, data, info))
        finally:
            cursor.close()

    def turns(self, game_id: int) -> TURNS:
        """load all turns"""
        query = """
                SELECT player_id, turn, data
                FROM turns
                WHERE game_id = ? and turn > 0
                ORDER by player_id, turn;
                """
        cursor = self.conn.cursor()
        turns: TURNS = {}
        try:
            cursor.execute(query, (game_id,))
            for player_id, turn_id, data in cursor:
                if player_id not in turns:
                    turns[player_id] = {}
                turns[player_id][turn_id] = Turn(player_id, turn_id, json.loads(data))
            return turns
        finally:
            cursor.close()

    def save_turn(self, game_id: GAME_ID, turn_id: TURN_ID, data: dict[str, Any]):
        "save turn data loaded from server to the database"
        player_id = data["player"]["id"]
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                INSERT_TURN,
                (
                    game_id,
                    player_id,
                    turn_id,
                    json.dumps(data),
                ),
            )
            self.conn.commit()
        finally:
            cursor.close()

    def save_turns(self, content: bytes):
        """Save turn data in zipped archive from loadall"""
        recs = []
        game_dict = None
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            # List all file names in the archive
            for filename in zf.namelist():
                try:
                    if filename.endswith(".trn"):
                        with zf.open(filename) as f:
                            data = json.load(f)
                            game_dict = data["game"]
                            game_id = game_dict["id"]
                            game_name = game_dict["name"]
                            player_id = data["player"]["id"]
                            turn_id = game_dict["turn"]
                            recs.append((game_id, player_id, turn_id, json.dumps(data)))
                except json.JSONDecodeError as jsex:
                    print(f"JSON error on {filename}: {jsex}")
        cursor = self.conn.cursor()
        try:
            cursor.executemany(INSERT_TURN, recs)
            self.conn.commit()
        finally:
            cursor.close()

        info = self.update_info(game_dict["id"])
        self._save_update_games([info["game"]], [info])

    def update_games(self, force_update=False) -> bool:
        if not force_update and not self.requires_update():
            return False

        username = self.account["username"]
        res = requests.get(
            f"http://api.planets.nu/games/list?username={username}&scope=1&status=2,3"
        )
        games = res.json()

        infos = []
        for game in games:
            game_id = game["id"]
            infos.append(self.update_info(game_id))

        self._save_update_games(games, infos)
        return True


    def _save_update_games(self, games: list[dict], infos: list[dict]) -> None:
        """Insert or update games with accompanying metadata and info"""
        cursor = self.conn.cursor()
        try:
            existing_meta = {}
            cursor.execute("SELECT game_id, meta FROM games")
            for row in cursor:
                existing_meta[row[0]] = json.loads(row[1])

            now = int(time.time())
            for game, info in zip(games, infos):
                game_id = game["id"]
                game_name = game["name"]

                player = query_one(
                    info["players"], lambda p: p["username"] == self.account["username"]
                )
                player_id = player["id"] if player else 1

                meta = existing_meta.get(game_id, {})
                meta["last_updated"] = now
                meta["player_id"] = player_id

                meta_js = json.dumps(meta)
                data_js = json.dumps(game)
                info_js = json.dumps(info)

                cursor.execute(
                    INSERT_GAME, (game_id, game_name, meta_js, data_js, info_js)
                )
            self.conn.commit()
        finally:
            cursor.close()


class PlanetsDB(_PlanetsDB):
    "synchronous version"

    def update_info(self, game_id: GAME_ID) -> dict:
        req_data = dict(gameid=game_id)
        req = requests.post("http://api.planets.nu/game/loadinfo", data=req_data)
        return req.json()

    def update_games(self, force_update=False) -> bool:
        if not force_update and not self.requires_update():
            return False

        username = self.account["username"]
        res = requests.get(
            f"http://api.planets.nu/games/list?username={username}&scope=1&status=2,3"
        )
        games = res.json()

        infos = []
        for game in games:
            game_id = game["id"]
            infos.append(self.update_info(game_id))

        self._save_update_games(games, infos)
        return True

    def update_turn(self, game_id: int, turn_id: int|None=None, player_id: int|None=None) -> bool:
        """Update the turn information for the given turn from the server."""
        req_data = dict(gameid=game_id, apikey=self.account["apikey"])
        if turn_id is not None:
            req_data["turn"] = turn_id
        if player_id is not None:
            req_data["playerid"] = player_id
        res = requests.post("http://api.planets.nu/game/loadturn", data=req_data)
        data = res.json()
        if not data["success"]:
            logger.warn(
                f"update_turn game_id={game_id}, turn={turn_id}: {data['error']}"
            )
            return False
        if turn_id is None:
            turn_id = data["rst"]["game"]["turn"]
        self.save_turn(game_id, turn_id, data["rst"])
        return True

    def load_all(self, game_id: int, save_file=None) -> None:
        """Get a ZIP archive containing all of the turns of a completed game, except the very last turn of a game"""
        req_data = dict(gameid=game_id, apikey=self.account["apikey"])
        res = requests.post("http://api.planets.nu/game/loadall", data=req_data)
        if save_file:
            save_file.write(res.content)
        self.save_turns(res.content)
        # get the last turn for each player
        self.load_last_turns(game_id)

    def load_all_from_archive(self, game_id: int, archive_file) -> None:
        """Get a ZIP archive containing all of the turns of a completed game, except the very last turn of a game"""
        content = open(archive_file, 'rb').read()
        self.save_turns(content)
        # get the last turn for each player
        self.load_last_turns(game_id)

    def load_last_turns(self, game_id: int) -> None:
        " because the zip archive retrieved in load_all doesn't include the last turn "
        game = self.game(game_id)
        assert game.data['statusname'] == 'Finished'
        last_turn = game.data['turn']
        players = [p for p in game.players]
        for p in players:
            if last_turn not in game._turns[p]:
                self.update_turn(game_id=game.game_id, turn_id=last_turn, player_id=p)

    def update(self, force_update=False) -> None:
        if not self.update_games(force_update):
            return
        cursor = self.conn.cursor()
        try:
            for game in self.games():
                latest = game.data["turn"]
                player_id = game.meta["player_id"]
                missing = {
                    t for t in range(1, latest + 1) if t not in game._turns.get(player_id, [])
                }
                unavail = game.meta.get("unavailable_turns", [])
                for t in unavail:
                    missing.discard(t)
                if not missing:
                    continue
                logger.info(f"loading turns {missing} for {game.name}")
                for turn_id in missing:
                    if not self.update_turn(game.game_id, turn_id):
                        unavail.append(turn_id)
                unavail = list(set(unavail))
                unavail.sort()
                game.meta["unavailable_turns"] = unavail
                cursor.execute(
                    "update games set meta = json(?) where game_id = ?",
                    (json.dumps(game.meta), game.game_id),
                )
            self.conn.commit()
        finally:
            cursor.close()


class PlanetsDBAsync(_PlanetsDB):
    "asynchronous version"

    async def update_info(self, game_id: GAME_ID) -> dict:
        req_data = dict(gameid=game_id)
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "http://api.planets.nu/game/loadinfo", data=req_data
            )
            data = res.json()
        return data

    async def update_turn(
        self, game_id: GAME_ID, turn_id: TURN_ID | None = None
    ) -> bool:
        """Update the turn information for the given turn from the server."""
        req_data = dict(gameid=game_id, apikey=self.account["apikey"])
        if turn_id is not None:
            req_data["turn"] = turn_id
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "http://api.planets.nu/game/loadturn", data=req_data
            )
            data = res.json()
        if not data["success"]:
            logger.warn(
                f"update_turn game_id={game_id}, turn={turn_id}: {data['error']}"
            )
            return False
        if turn_id is None:
            turn_id = data["rst"]["game"]["turn"]
        self.save_turn(game_id, turn_id, data["rst"])
        return True

    async def load_all(self, game_id: GAME_ID) -> bool:
        """Get a ZIP archive containing all of the turns of a completed game, except the very last turn of a game"""
        req_data = dict(gameid=game_id, apikey=self.account["apikey"])
        async with httpx.AsyncClient() as client:
            res = await client.post("http://api.planets.nu/game/loadall", data=req_data)
            res.raise_for_status()
            self.save_turns(res.content)
        return True

    async def update(self, force_update=False):
        if not await self.update_games(force_update):
            return
        cursor = self.conn.cursor()
        try:
            for game in self.games():
                latest = game.data["turn"]
                player_id = game.meta["player_id"]
                missing = {
                    t for t in range(1, latest + 1) if t not in game._turns.get(player_id, [])
                }
                unavail = game.meta.get("unavailable_turns", [])
                for t in unavail:
                    missing.discard(t)
                if not missing:
                    continue
                logger.info(f"loading turns {missing} for {game.name}")
                for turn_id in missing:
                    if not await self.update_turn(game.game_id, turn_id):
                        unavail.append(turn_id)
                unavail = list(set(unavail))
                unavail.sort()
                game.meta["unavailable_turns"] = unavail
                cursor.execute(
                    "update games set meta = json(?) where game_id = ?",
                    (json.dumps(game.meta), game.game_id),
                )
            self.conn.commit()
        finally:
            cursor.close()

    async def update_games(self, force_update=False) -> bool:
        last_updated = self.last_updated()
        now = int(time.time())
        if not force_update and last_updated and last_updated > now - ONE_HOUR_SECS:
            logger.info(f"games last updated {last_updated}, skipping refresh")
            return False

        username = self.account["username"]
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"http://api.planets.nu/games/list?username={username}&scope=1"
            )
            games = res.json()

        infos = []
        for game in games:
            game_id = game["id"]
            infos.append(await self.update_info(game_id))

        self._save_update_games(games, infos)
        return True
