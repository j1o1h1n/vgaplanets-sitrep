# flake8: noqa

SITREP = r"""
          🛸                                 ,----,                 ˗ˏˋ ★ ˎˊ˗                              
                                          ,/   .`|                                🛰️           ,-.----. 𖤓 
  .--.--.              ,---,            ,`   .'  :        ,-.----.               ,---,.        \    /  \   
 /  /    '.      ✮  ,`--.' |          ;    ;     /        \    /  \            ,'  .' |        |   :    \  
|  :  /`. /         |   :  :        .'___,/    ,'         ;   :    \         ,---.'   |        |   |  .\ : 
;  |  |--`          :   |  '        |    :     |   |-o-|  |   | .\ :         |   |   .'        .   :  |: | 
|  :  ;_            |   :  |        ;    |.';  ;          .   : |: |         :   :  |-,        |   |   \ : 
 \  \    `.         '   '  ;        `----'  |  |          |   |  \ :         :   |  ;/|        |   : .   / 
  `----.   \        |   |  |            '   :  ;          |   : .  /         |   :   .'        ;   | |`-'  
  __ \  \  |        '   :  ;   |-o-|    |   |  '          ;   | |  \         |   |  |-,  ⋆✴︎˚｡⋆ |   | ;     
 /  /`--'  /        |   |  '            '   :  |          |   | ;\  \        '   :  ;/|        :   ' |     
'--'.     /         '   :  |            ;   |.'           :   ' | \.'   🪐   |   |    \        :   : :     
  `--'---'          ;   |.'             '---'        ✰    :   : :-'          |   :   .'        |   | :     
                    '---'                                 |   |.'            |   | ,'          `---'.|     
       ⋆˚꩜｡                                               `---'              `----'              `---`     
                                                                                                           
"""

MAIN = """
# SITUATION REPORT

This is the main page for the SitRep app.  This app shows you information about
you VGAPlanets Nu games.  It is an invaluable tool for managing your interstellar
empire.

## Graph

The top part of this page shows a graph of various resources over time.  To switch
between the metrics, you can use the square bracket [ and ] keys.

The following resource graphs are available: Mines, Factories, Megacredits, 
Supplies, Neutronium, Molybdenum, Duranium, Tritanium, Neutronium Reserves,
Molybdenum Reserves, Duranium Reserves, Tritanium Reserves, Population (player),
Population (natives) and Income.

## Standard Reports

Below the graph are buttons that will take you to individual report pages.  The available
reports are:

* Intel - Information similar to what is available on the in-game Scoreboard
* Econ - Resource levels at each planet, grouped by star-base
* FreightTrac - Enemy freighter locations, with options to copy, export as in-game diagram
* MsgLog - In game messages, for all turns

## Switch Game

At any time, press "g" to change games.


## Quit

User ctrl+q to quit.

"""

INTEL = """
# Intel Report

This report shows the information about a players military score, capital 
ships, freighters and starbases, similar to what can be seen on the in-game 
Scoreboard.

Press "c" to copy the information to the clipboard.

Press the escape key to return to the main screen.
"""

ECON = """

# Econ Report

This report displays a table of the resources at each planet.  The planets are
grouped by star-base and then by sector (a group of connected systems).

Use the "[" and "]" keys to go back or forward a turn.  You can advance to 
future turns and a prediction of future resources will be generated.

Press "c" to copy the information to the clipboard.

Press the escape key to return to the main screen.
"""

FREIGHTERS = """

# Freighter Report

This shows locations information about freighter sightings for a given player.

Press "c" to copy the table to the clipboard.

## Export As Drawing

The data can also be copied as a diagram that can be pasted into the planets 
nu client as a "Drawing Layer". This has two parts, "z" to copy a Java script 
function called "install_drawing" to the clipboard.  This can be pasted into 
the JavaScript console.

Then use "x" to copy the table as a diagram to the clipboard.  This will use the
`install_drawing` function to add a new drawing layer with an appropriate name 
like "Bird Man (1) Freighters".

## install_drawing Function

```
install_drawing = function(layer) {
    const overlays = vgap.map.drawingtool.overlays;

    // Check for valid structure
    if (!layer || !layer.name || !Array.isArray(layer.markups)) {
        console.warn("Invalid overlay layer format");
        return;
    }

    // Replace or add the layer
    const existingIndex = overlays.findIndex(l => l.name === layer.name);
    if (existingIndex !== -1) {
        overlays[existingIndex] = layer;
    } else {
        overlays.push(layer);
    }

    // Activate and redraw
    vgap.map.drawingtool.current = {
        overlay: layer,
        markup: null,
        editindex: null,
        addType: "point"
    };
    vgap.map.draw();

    // save as note
    const note = vgap.getNote(0, -133919);
    // FIXME fails on no notes
    let body = [];
    if (note['body']) {
        body = JSON.parse(note['body']);
        layerIndex = body.findIndex(entry => entry.name === layer.name);
        if (layerIndex !== -1) {
            body[layerIndex] = layer;
        } else {
            body.push(layer);
        }
    } else {
        body.push(layer);
    }
    note['body'] = JSON.stringify(body);
    note["changed"] = 1;
};
```

"""

MSGLOG = """

# Message log

This report shows all the messages.  Use the input box to search the messages.

By default the report shows explosions, but the message type can be changed by
using ctrl+t to toggle a sidebar of "Message Types" which can be used to change 
the type of message shown.

Press the escape key to return to the main screen.
"""

GAMES = """

# Game List

This screen shows the list of active games and the current status.

It shows a list of players and a coloured dot showing the status of each turn,
white for unseen, orange for in progress and blue for ready.  The border colour
around the game reflects your turn status.

There are two buttons "Select" to view reports for this game, and "Refresh", to
update game information from the server.

Access this report by selecting "g" from any screen.

Press the escape key to return to the main screen.
"""
