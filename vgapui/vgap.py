"""
See https://help.planets.nu/API for the APi
"""
import requests
import sqlite3
import json
import logging
import datetime

from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,  # Set the logging level to DEBUG
    format="%(asctime)s - %(levelname)s - %(message)s"
)

LOAD_TURN = "http://api.planets.nu/game/loadturn"

# req = requests.get("http://api.planets.nu/game/loadturn", data=dict(gameid=game['id'], apikey=account['apikey']))

TABLES = {
    "settings":
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT NOT NULL PRIMARY KEY,
            data JSON NOT NULL
        );""",
    "games":
        """
        CREATE TABLE IF NOT EXISTS games (
            game_id INTEGER PRIMARY KEY, 
            name TEXT NOT NULL,
            data JSON NOT NULL,
            last_updated TEXT NOT NULL
        );""",
    "turns":
        """
        CREATE TABLE IF NOT EXISTS turns (
            game_id INTEGER NOT NULL, 
            turn INTEGER NOT NULL,
            data JSON NOT NULL,
            PRIMARY KEY (game_id, turn)
        );"""
}

INSERT_GAME = """
REPLACE INTO games (game_id, name, data, last_updated)
VALUES (?, ?, ?, ?);
"""

INSERT_TURN = """
REPLACE INTO turns (game_id, turn, data)
VALUES (?, ?, ?);
"""


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
    api_key_path = Path.home() / "vgap.apikey"
    with open(api_key_path, 'w') as f:
        f.write(json.dumps(account))
        f.close()


def get_ts(td: datetime.timedelta=None) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc)
    if td:
        dt = dt + td
    return dt.isoformat(" ", "seconds")


class Game:

    def __init__(self, data):
        self.game_id = data["game_id"]
        self.game_name = data["name"]


class Planets:

    def __init__(self, db_file):
        self.db_file = db_file
        self.account = load_api_key()
        self.conn = configure_wal(sqlite3.connect(db_file))
        for table in TABLES.values():
            self.conn.execute(table)

    def close(self):
        # self.conn.execute("PRAGMA wal_checkpoint(FULL);")
        self.conn.close()

    def login(self, username, password):
        data = dict(username=username, password=password)
        req = requests.post(f"http://api.planets.nu/account/login", data=data)
        apikey = req.json()['apikey']
        self.account = {'username': username, 'apikey': apikey}
        save_api_key(self.account)
        return self.account

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
                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, data)
                    VALUES (?, ?);
                """, (key, json_data))
            self.conn.commit()
        finally:
            cursor.close()

    def update(self):
        if not self.load_games():
            return
        cursor = self.conn.cursor()
        try:
            for game in self.games():
                game_id, latest_turn = game["game_id"], game["latest_turn"]
                cursor.execute("""
                    SELECT turn
                    FROM turns
                    WHERE game_id = ?
                """, (game_id,))
                existing_turns = {row[0] for row in cursor.fetchall()} 
                # Find missing turns
                missing_turns = set(range(1, latest_turn + 1)) - existing_turns
                logging.debug(f"existing: {existing_turns}, fetching missing turns: {missing_turns}")
                if 2 in missing_turns:
                    # FIXME host seems to be missing turn 2
                    missing_turns.remove(2)
                # Load each missing turn
                for turn in sorted(missing_turns):
                    self.load_turn(game_id, turn)
            self.conn.commit()
        finally:
            cursor.close()        

    def load_games(self, force_update=False) -> bool:
        """
        Update the games table with latest information for each game.

        If not force_update and the game data was last updated less than an 
        hour ago, returns False.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("select min(last_updated) from games")
            last_updated = cursor.fetchone()[0]
            if not force_update and last_updated > get_ts(datetime.timedelta(hours=-1)):
                logging.debug(f"games last updated {last_updated}, skipping refresh")
                return False
            username = self.account['username']
            req = requests.get(f"http://api.planets.nu/games/list?username={username}&scope=1")
            games = req.json()
            for game in games:
                game_id = game['id']
                game_name = game['name']
                game_json = json.dumps(game)  # Convert game dictionary to JSON string
                cursor.execute(INSERT_GAME, (game_id, game_name, game_json, get_ts()))
            self.conn.commit()
            return True
        finally:
            cursor.close()

    def load_turn(self, game_id, turn=None):
        """ Load the given turn for the given game. """
        cursor = self.conn.cursor()
        try:
            req_data = dict(gameid=game_id, apikey=self.account['apikey'])
            if turn is not None:
                req_data['turn'] = turn
            req = requests.post("http://api.planets.nu/game/loadturn", data=req_data)
            data = req.json()
            rst = data['rst']
            turn = rst['game']['turn']

            # Serialize the turn data into JSON format
            turn_data_json = json.dumps(data)

            # Execute the insert query
            cursor.execute(INSERT_TURN, (game_id, turn, turn_data_json,))
            self.conn.commit()
        finally:
            cursor.close()

    def games(self):
        """ Returns a list of dict(name, game_id, latest_turn) """
        query = """
        SELECT 
            g.name, 
            g.game_id, 
            CAST(JSON_EXTRACT(g.data, '$.turn') AS INTEGER) AS latest_turn
        FROM games g
        ORDER BY g.name;
        """

        cursor = self.conn.cursor()
        try:
            cursor.execute(query)
            rows = cursor.fetchall()
            for row in rows:
                name, game_id, latest_turn = row
                yield dict(name=name, game_id=game_id, latest_turn=latest_turn)
        finally:
            cursor.close()

    def turn(self, game_id, turn):
        """
        Retrieve the turn data for a specific game and turn.

        Parameters:
            game_id (int): The ID of the game.
            turn (int): The turn number to retrieve.

        Returns:
            dict: The turn data as a dictionary, or None if not found.
        """
        query = """
        SELECT data
        FROM turns
        WHERE game_id = ? AND turn = ?;
        """

        cursor = self.conn.cursor()
        try:
            cursor.execute(query, (game_id, turn))
            row = cursor.fetchone()
            if row:
                turn_data = json.loads(row[0])  # Deserialize JSON data
                return turn_data
            else:
                logging.error(f"No data found for game_id={game_id}, turn={turn}")
                return None
        finally:
            cursor.close()

    def turns(self, game_id):
        """ Load all turns """
        query = """
        SELECT data
        FROM turns
        WHERE game_id = ?
        ORDER by turn;
        """

        cursor = self.conn.cursor()
        try:
            turns = []
            cursor.execute(query, (game_id,))
            for row in cursor:
                turn_data = json.loads(row[0])
                turns.append(turn_data)
            return turns
        finally:
            cursor.close()        

    def milscore(self, game_id, username):
        """
        Print the military scores for a specific player by username for each turn in a game.

        Parameters:
            game_id (int): The ID of the game.
            username (str): The username of the player.
        """
        query = """
        SELECT turn, data
        FROM turns
        WHERE game_id = ?
        ORDER BY turn ASC;
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute(query, (game_id,))
            rows = cursor.fetchall()

            #print(f"{'Turn':<10} {'Military Score':<15} {'Change':<10} {'Warships':<10} {'+/-':<4} ")
            #print("-" * 40)

            player_id = None

            for turn, data_json in rows:
                turn_data = json.loads(data_json)  # Deserialize JSON
                if player_id is None:
                    # Find player ID by username
                    players = turn_data['rst']['players']
                    for player in players:
                        if player['username'].lower() == username.lower():
                            player_id = player['id']
                            break
                    if player_id is None:
                        #logging.debug(f"Player '{username}' not found in turn {turn_data['rst']['game']['turn']}.")
                        continue

                # Extract the military score for the player's ID
                scores = turn_data['rst']['scores']
                for score in scores:
                    if score['ownerid'] == player_id:
                        #print(f"{turn:<10} {score['militaryscore']:<15} {score['militarychange']:<10} {score['capitalships']:<10} {score['shipchange']:<4}")
                        yield turn, score['militaryscore'], score['militarychange'], score['capitalships'] ,score['shipchange']
                        break

        finally:
            cursor.close()