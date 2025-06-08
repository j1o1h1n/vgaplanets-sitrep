

def build_starmap(game, skip_last_turn=True):
    players = list(game.players.values())
    planets = {}
    turninfo = {}
    skip_turn = -1 if not skip_last_turn else max(game.turns().keys())
    for player in players:
        player_id = player.player_id
        turns = game.turns(player_id)
        for turn in turns.values():
            if turn.turn_id == skip_turn:
                continue
            # update with any new planets
            for p in turn.planets():
                if p["id"] in planets:
                    continue
                name = p["name"].replace("'\"", "")
                planets[p["id"]] = {"id": p["id"], "name": name, "x": p["x"], "y": p["y"]}
            # update planet and starbase ownership
            if turn.turn_id not in turninfo:
                turninfo[turn.turn_id] = {"planet_owner": {}, "starbase_owner": {}}
            for planet in turn.planets(player_id):
                turninfo[turn.turn_id]["planet_owner"][planet["id"]] = player_id
            for sb in turn.starbases(player_id):
                turninfo[turn.turn_id]["starbase_owner"][sb["planetid"]] = player_id
    return {"planets": planets, "turns": turninfo}


def write_starmap(game, output_path):
    turn = game.turns()[1]
    settings = turn.data["settings"]
    mapshape = settings["mapshape"]
    mapwidth = settings["mapwidth"]
    mapheight = settings["mapheight"]
    players = [
        { "id": p.player_id, "name": p.name, "race": p.short_name, "color": p.color }
        for p in game.players.values()
    ]

    data = build_starmap(game)

    starmap = {
      "title": game.name,
      "width": mapwidth,
      "height": mapheight,
      "mapshape": mapshape,
      "padding": 50,
      "players": players,
      "planets": list(data["planets"].values()),
      "turns": data["turns"],
    };

    with open(output_path, 'w') as f:
        f.write(json.dumps(starmap, indent=2))