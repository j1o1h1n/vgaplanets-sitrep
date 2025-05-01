from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Center
from textual.reactive import reactive
from textual.timer import Timer
import random
import itertools

# flake8: noqa
TRANSMISSION = """
      I N C O M I N G  T R A N S M I S S I O N     

                  🭇   .   .  🭇🬽    
                 🬑  .'' .     : 🬟
                🬐  .      🮭 '  . 🬐 
                🬡  ; 🮪 ,  .' ; .🬒
                  🬢   .  🮬 .  🬖    
                    🭸🬱   . 🬵🭸  
                       🬥  🬙
                        🭙🭤

              AUTHORISED ACCESS ONLY"""

STAR_CHARS = "🮩🮪🮫🮬🮭🮮🮯"

COLORS = [
    "primary-lighten-3",
    "primary-lighten-2",
    "primary-lighten-1",
    "primary",
    "primary-darken-1",
    "primary-darken-2",
    "primary-darken-3",
]

BORDER_COLORS = [
    "accent-lighten-2",
    "accent-lighten-2",
    "accent-lighten-2",
    "accent-lighten-1",
    "accent-lighten-1",
    "accent",
    "accent",
]


def find_all(text, chars):
    """Returns a list of indexes of all occurrences of any character in 'chars' in 'text'."""
    return [i for i, c in enumerate(text) if c in chars]


def build_star_anim(text, chars):
    res = {}
    for idx in find_all(text, chars):
        c = chars.find(text[idx])
        res[idx] = itertools.cycle(chars[c:] + chars[:c])
    return res


class TransmissionPanel(Static):
    star_text = reactive("")
    star_anims = build_star_anim(TRANSMISSION, STAR_CHARS)
    step = 0

    def on_mount(self) -> None:
        self.set_interval(0.2, self.animate_stars)

    def animate_stars(self) -> None:
        stars = "".join(random.choice(STAR_CHARS) for _ in range(20))
        self.star_text = stars
        pos = 0
        fragments = []
        for i in self.star_anims:
            fragments.append(TRANSMISSION[pos:i])
            fragments.append(next(self.star_anims[i]))
            pos = i + 1
        fragments.append(TRANSMISSION[pos:])
        transmission = "".join(fragments)
        self.step = (self.step + 1) % len(COLORS)
        self.styles.color = self.app.theme_variables[COLORS[self.step]]
        border_color = self.app.theme_variables[BORDER_COLORS[self.step]]
        self.styles.border = ("round", border_color)

        self.update(f"{transmission}\n               {self.star_text}")


class TransmissionApp(App):

    CSS_PATH = "situation_report.tcss"

    def compose(self) -> ComposeResult:
        with Center():
            yield TransmissionPanel()


# used by textual run
app = TransmissionApp()


def main():
    app.run()


if __name__ == "__main__":
    main()
