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

from typing import NamedTuple, Optional, Any
from pathlib import Path

from . import space

logger = logging.getLogger(__name__)

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
            turn INTEGER NOT NULL,
            data JSON NOT NULL,
            PRIMARY KEY (game_id, turn)
        );""",
}

INSERT_GAME = """
REPLACE INTO games (game_id, name, meta, data, info)
VALUES (?, ?, ?, ?, ?);
"""

INSERT_TURN = """
REPLACE INTO turns (game_id, turn, data)
VALUES (?, ?, ?);
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
        f.close()


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
        turn_id=data["turn"],
        player_id=data["ownerid"],
        planets=data["planets"],
        planets_delta=data["planetchange"],
        starbases=data["starbases"],
        starbases_delta=data["starbasechange"],
        capital_ships=data["capitalships"],
        capital_ships_delta=data["shipchange"],
        civilian_ships=data["freighters"],
        civilian_ships_delta=data["freighterchange"],
        military_score=data["militaryscore"],
        military_score_delta=data["militarychange"],
        score=data["inventoryscore"],
        score_delta=data["inventorychange"],
        pp=data["prioritypoints"],
        pp_delta=data["prioritypointchange"],
    )


class Player:

    def __init__(self, id, raceid, racename, username):
        self.id = id
        self.raceid = raceid
        self.racename = racename
        self.username = username

    def __repr__(self):
        return f"<Player id={self.id}, name={self.username}, race={self.racename}>"


class Turn:

    def __init__(self, turn_id: int, data: dict[str, Any]):
        self.turn_id = turn_id
        self.data = data
        self.rst = data["rst"]
        self.player_id = self.rst["player"]["id"]
        self._cluster: space.Cluster | None = None

    def _filter_by_owner(self, category, filter_key, filter_value):
        """Helper function to filter objects by owner ID."""
        if filter_value is None:
            return self.rst[category]
        return [obj for obj in self.rst[category] if obj[filter_key] == filter_value]

    def ships(self, player_id=None):
        """Return all ships owned by the specified player, or all ships if no player_id specified."""
        return self._filter_by_owner("ships", "ownerid", player_id)

    def planets(self, player_id=None):
        """Return all planets owned by the specified player, or all planets if no player_id specified."""
        return self._filter_by_owner("planets", "ownerid", player_id)

    def starbases(self, player_id=None):
        """Return all starbases owned by the specified player, or all starbases if no player_id specified."""
        starbases = self.rst["starbases"]
        if player_id:
            planet_ids = {p["id"] for p in self.planets(player_id)}
            starbases = [s for s in starbases if s["planetid"] in planet_ids]
        return starbases

    def cluster(self) -> space.Cluster:
        if self._cluster is None:
            self._cluster = space.Cluster(self)
        return self._cluster

    def sectors(self) -> space.Clique:
        return self.cluster().cliques


# game status codes
STATUS_JOINING, STATUS_RUNNING, STATUS_FINISHED, STATUS_HOLS = range(1, 5)


class Game:

    def __init__(self, game_id, name, meta, data, turns, info):
        self.game_id = game_id
        self.name = name
        self.meta = meta
        self.data = data
        self.info = info
        self.turns = turns
        if self.turns:
            turn = self.turn()
            self.races = {r["id"]: r for r in turn.rst["races"]}
            self.players = {
                p["id"]: Player(
                    p["id"], p["raceid"], self.races[p["raceid"]]["name"], p["username"]
                )
                for p in turn.rst["players"]
            }
            if 0 in self.races:
                del self.races[0]
            if 0 in self.players:
                del self.players[0]

    def turn(self, turn_id=None):
        """Return the given turn, or latest if no turn specified"""
        if turn_id is None:
            turn_id = max(self.turns.keys())
        return self.turns[turn_id]

    def scores(self) -> dict[int, dict[int, Score]]:
        res: dict[int, dict[int, Score]] = {}
        for player_id in self.players:
            res[player_id] = {}
        for turn in self.turns.values():
            for data in turn.rst["scores"]:
                score = create_score(data)
                res[score.player_id][score.turn_id] = score
        return res


class _PlanetsDB:

    def __init__(self, db_file):
        self.db_file = db_file
        self.account = load_api_key()
        self.conn = configure_wal(sqlite3.connect(db_file))
        for table in TABLES.values():
            self.conn.execute(table)

    def login(self, username, password):
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

    def save_settings(self, settings):
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

    def game(self, game_id_or_name) -> Game:
        """Returns a Game"""
        games = [g for g in self.games() if game_id_or_name in [g.game_id, g.name]]
        if len(games) == 0:
            raise KeyError(game_id_or_name)
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

    def turns(self, game_id) -> dict[int, Turn]:
        """Load all turns"""
        query = """
        SELECT data
        FROM turns
        WHERE game_id = ?
        ORDER by turn;
        """

        cursor = self.conn.cursor()
        try:
            turns = {}
            cursor.execute(query, (game_id,))
            for row in cursor:
                turn_data = json.loads(row[0])
                turn_id = turn_data["rst"]["game"]["turn"]
                turns[turn_id] = Turn(turn_id, turn_data)
            return turns
        finally:
            cursor.close()

    def save_turn(self, game_id: int, turn_id: int, data: dict[str, Any]):
        "save turn data loaded from server to the database"
        cursor = self.conn.cursor()
        try:
            # Execute the insert query
            cursor.execute(
                INSERT_TURN,
                (
                    game_id,
                    turn_id,
                    json.dumps(data),
                ),
            )
            self.conn.commit()
        finally:
            cursor.close()


class PlanetsDB(_PlanetsDB):
    "synchronous version"

    def update_info(self, game_id) -> dict:
        req_data = dict(gameid=game_id)
        req = requests.post("http://api.planets.nu/game/loadinfo", data=req_data)
        return req.json()

    def update_games(self, force_update=False) -> bool:
        """
        Update the games table with latest information for each game.

        If not force_update and the game data was last updated less than an
        hour ago, returns False.
        """
        cursor = self.conn.cursor()
        try:
            last_updated = self.last_updated()
            now = int(time.time())
            ref_ts = now - ONE_HOUR_SECS
            logger.info(
                f"load_games last_updated {last_updated}, comparison ts {ref_ts}"
            )
            if not force_update and last_updated and last_updated > ref_ts:
                logging.info(f"games last updated {last_updated}, skipping refresh")
                return False

            existing_meta = {}
            cursor.execute("select game_id, meta from games")
            for row in cursor:
                existing_meta[row[0]] = json.loads(row[1])

            username = self.account["username"]
            req = requests.get(
                f"http://api.planets.nu/games/list?username={username}&scope=1"
            )
            games = req.json()
            for game in games:
                game_id = game["id"]
                game_name = game["name"]
                meta = existing_meta.get(game_id, {})
                meta["last_updated"] = now
                meta = json.dumps(meta)
                data = json.dumps(game)
                info = json.dumps(self.update_info(game["id"]))
                cursor.execute(INSERT_GAME, (game_id, game_name, meta, data, info))
            self.conn.commit()
            return True
        finally:
            cursor.close()

    def update_turn(self, game_id, turn_id=None) -> bool:
        """Update the turn information for the given turn from the server."""
        req_data = dict(gameid=game_id, apikey=self.account["apikey"])
        if turn_id is not None:
            req_data["turn"] = turn_id
        res = requests.post("http://api.planets.nu/game/loadturn", data=req_data)
        data = res.json()
        if not data["success"]:
            logger.warn(
                f"update_turn game_id={game_id}, turn={turn_id}: {data['error']}"
            )
            return False
        if turn_id is None:
            turn_id = data["rst"]["game"]["turn"]
        self.save_turn(game_id, turn_id, data)
        return True

    def update(self, force_update=False):
        if not self.update_games(force_update):
            return
        cursor = self.conn.cursor()
        try:
            for game in self.games():
                latest = game.data["turn"]
                missing = {t for t in range(1, latest + 1) if t not in game.turns}
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

    async def update_info(self, game_id) -> dict:
        req_data = dict(gameid=game_id)
        async with httpx.AsyncClient() as client:
            res = await client.post(
                "http://api.planets.nu/game/loadinfo", data=req_data
            )
            data = res.json()
        return data

    async def update_turn(self, game_id, turn_id=None) -> bool:
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
        self.save_turn(game_id, turn_id, data)
        return True

    async def update(self, force_update=False):
        if not await self.update_games(force_update):
            return
        cursor = self.conn.cursor()
        try:
            for game in self.games():
                latest = game.data["turn"]
                missing = {t for t in range(1, latest + 1) if t not in game.turns}
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
        """
        Update the games table with latest information for each game.

        If not force_update and the game data was last updated less than an
        hour ago, returns False.
        """
        cursor = self.conn.cursor()
        try:
            last_updated = self.last_updated()
            now = int(time.time())
            ref_ts = now - ONE_HOUR_SECS
            logger.info(
                f"load_games last_updated {last_updated}, comparison ts {ref_ts}"
            )
            if not force_update and last_updated and last_updated > ref_ts:
                logging.info(f"games last updated {last_updated}, skipping refresh")
                return False

            existing_meta = {}
            cursor.execute("select game_id, meta from games")
            for row in cursor:
                existing_meta[row[0]] = json.loads(row[1])

            username = self.account["username"]
            async with httpx.AsyncClient() as client:
                req = await client.get(
                    f"http://api.planets.nu/games/list?username={username}&scope=1"
                )
                games = req.json()
            for game in games:
                game_id = game["id"]
                game_name = game["name"]
                meta = existing_meta.get(game_id, {})
                meta["last_updated"] = now
                meta = json.dumps(meta)
                data = json.dumps(game)
                info = json.dumps(await self.update_info(game["id"]))
                cursor.execute(INSERT_GAME, (game_id, game_name, meta, data, info))
            self.conn.commit()
            return True
        finally:
            cursor.close()
