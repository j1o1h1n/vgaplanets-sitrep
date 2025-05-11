from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.widgets import Header, Footer, Input, RadioSet, RadioButton, Markdown
from textual.events import Click
from textual.screen import Screen

from .widgets import rule

from . import helpdoc

import re


MESSAGE_TYPES = {
    999: "All",
    0: "Outbound",
    1: "System",
    2: "Terraforming",
    3: "Minelaying",
    4: "Mine Sweep",
    5: "Colony",
    6: "Combat",
    7: "Fleet",
    8: "Ship",
    9: "Enemy Distress Call",
    10: "Explosion",
    11: "Starbase",
    12: "Web Mines",
    13: "Meteors",
    14: "Sensor Sweep",
    15: "Bio Scan",
    16: "DistressCall",
    17: "Player",
    18: "Diplomacy",
    19: "MineScan",
    20: "Dark Sense",
    21: "Hiss",
}


class Sidebar(Container):
    pass


def all_message_types(game):
    found = {999}
    for turn in game.turns.values():
        for m in turn.rst["messages"]:
            found.add(m["messagetype"])
    return [mt for mt in MESSAGE_TYPES if mt in found]


class MessagesControl:

    def __init__(self, game, viewer):
        self.game = game
        self.viewer = viewer

    def build_markup(self, msg_type, search_text):
        pat = re.compile(".*") if not search_text else re.compile(search_text)

        def filter_message(m):
            if msg_type < 999 and m["messagetype"] != msg_type:
                return False
            return pat.search(m["headline"]) or pat.search(m["body"])

        doc = {}
        for turn_id in reversed(self.game.turns):
            turn = self.game.turns[turn_id]
            doc[turn_id] = {}
            for m in turn.rst["messages"]:
                if not filter_message(m):
                    continue
                headline = m["headline"]
                body = m["body"]
                if headline not in doc[turn_id]:
                    doc[turn_id][headline] = []
                doc[turn_id][headline].append(body)
        markup = []
        for turn_id in doc:
            if not doc[turn_id]:
                continue
            markup.append(f"# Turn {turn_id}")
            for headline in doc[turn_id]:
                if not doc[turn_id][headline]:
                    continue
                markup.append(f"## {headline}")
                for body in doc[turn_id][headline]:
                    markup.append(f"🭬 {body}\n")

        return "\n".join(markup)

    def update(self, msg_type, search_text):
        markup = self.build_markup(msg_type, search_text)
        self.viewer.update(markup)


class MessagesScreen(Screen):

    TITLE = "Messages"
    SUB_TITLE = ""

    BINDINGS = [
        ("ctrl+t", "toggle_sidebar", "Toggle Sidebar"),
    ]

    def __init__(self, game, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game = game
        self.viewer = Markdown("# Turn 1")
        self.viewer_control = MessagesControl(self.game, self.viewer)
        self.input_value = ""
        self.message_type = 999
        self.message_types = all_message_types(self.game)

    def on_screen_resume(self):
        self.app.update_help(helpdoc.MSGLOG)

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Input("Search")
            with Sidebar(classes="-hidden"):
                yield rule.Rule.horizontal(
                    id="message_type_rule",
                    title="┣ MESSAGE TYPE ┫",
                    line_style="heavy",
                    cap_style="none",
                )
                with RadioSet():
                    for message_type_id in self.message_types:
                        yield RadioButton(
                            f"{MESSAGE_TYPES[message_type_id]}",
                            id=f"m_{message_type_id}",
                        )
            with VerticalScroll():
                yield self.viewer
        yield Footer()

    def on_mount(self):
        self.sub_title = self.game.name
        self.viewer_control.update(self.message_type, self.input_value)

    @on(Input.Submitted)
    def on_input(self, event: Input.Submitted) -> None:
        self.input_value = event.value
        self.viewer_control.update(self.message_type, self.input_value)

    @on(RadioSet.Changed)
    def on_message_type(self, event: RadioSet.Changed) -> None:
        self.message_type = int(str(event.pressed.id)[2:])
        self.viewer_control.update(self.message_type, self.input_value)

    def action_toggle_sidebar(self):
        self.query_one(Sidebar).toggle_class("-hidden")

    def on_click(self, event: Click):
        if type(event.widget) is rule.Rule and event.widget.id == "message_type_rule":
            self.query_one(Sidebar).toggle_class("-hidden")
