from __future__ import annotations

from typing import Iterable

from textual.app import App, ComposeResult

from rich.console import Console, ConsoleOptions
from rich.segment import Segment
from rich.style import Style
from typing_extensions import Literal

from textual.app import RenderResult
from textual.css._error_tools import friendly_list
from textual.geometry import Size
from textual.reactive import Reactive, reactive
from textual.widget import Widget

RuleOrientation = Literal["horizontal", "vertical"]
"""The valid orientations of the rule widget."""

LineStyle = Literal[
    "ascii",
    "none",
    "dashed",
    "double",
    "heavy",
    "hidden",
    "none",
    "solid",
    "thick",
    "medium",
]
"""The valid line styles of the rule widget."""

CapStyle = Literal[
    "none",
    "round",
    "triangle",
]
"""The valid cap styles of the rule widget."""

_VALID_RULE_ORIENTATIONS = {"horizontal", "vertical"}

_VALID_LINE_STYLES = {
    "ascii",
    "none",
    "dashed",
    "double",
    "heavy",
    "hidden",
    "none",
    "solid",
    "thick",
    "medium",
}

_VALID_CAP_STYLES = {
    "none",
    "round",
    "triangle",
}

_HORIZONTAL_LINE_CHARS: dict[LineStyle, str] = {
    "ascii": "-",
    "none": " ",
    "dashed": "╍",
    "double": "═",
    "heavy": "━",
    "hidden": " ",
    "none": " ",
    "solid": "─",
    "thick": "█",
    "medium": "■",
}

_VERTICAL_LINE_CHARS: dict[LineStyle, str] = {
    "ascii": "|",
    "none": " ",
    "dashed": "╏",
    "double": "║",
    "heavy": "┃",
    "hidden": " ",
    "none": " ",
    "solid": "│",
    "thick": "█",
    "medium": "▐",
}

_HORIZONTAL_CAP_CHARS: dict[CapStyle, str] = {
    "round": "◖◗",
    "triangle": "◀▶",
    "none": "",
}

_VERTICAL_CAP_CHARS: dict[CapStyle, str] = {
    "round": "◚◛",
    "triangle": "▲▼",
    "none": "",
}


class InvalidRuleOrientation(Exception):
    """Exception raised for an invalid rule orientation."""


class InvalidLineStyle(Exception):
    """Exception raised for an invalid rule line style."""


class InvalidCapStyle(Exception):
    """Exception raised for an invalid rule cap style."""


class HorizontalRuleRenderable:
    """Renders a horizontal rule."""

    def __init__(
        self,
        title: str,
        character: str,
        cap_character: str,
        style: Style,
        text_align: str,
        width: int,
    ):
        self.title = title
        self.character = character
        self.cap_character = cap_character
        self.style = style
        self.text_align = text_align
        self.width = width

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterable[Segment]:
        character = self.character
        left_cap = right_cap = ""
        if len(self.cap_character) == 2:
            left_cap, right_cap = self.cap_character[0], self.cap_character[1]

        body_width = self.width - len(self.title) - len(self.cap_character)
        text_align = self.text_align or "left"
        if text_align == "right":
            body = character * body_width
            segment = f"{left_cap}{body}{self.title}{right_cap}"
        elif text_align == "center":
            body = character * (body_width // 2)
            pad = character * (body_width % 2)
            segment = f"{left_cap}{body}{self.title}{body}{pad}{right_cap}"
        else:
            # TODO error on unknown text align?
            body = character * body_width
            segment = f"{left_cap}{self.title}{body}{right_cap}"

        yield Segment(segment, self.style)


class VerticalRuleRenderable:
    """Renders a vertical rule."""

    def __init__(
        self,
        title: str,
        character: str,
        cap_character: str,
        style: Style,
        text_align: str,
        height: int,
    ):
        self.title = title
        self.character = character
        self.cap_character = cap_character
        self.style = style
        self.text_align = text_align
        self.height = height

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterable[Segment]:
        segment = Segment(self.character, self.style)
        new_line = Segment.line()
        return ([segment, new_line] * self.height)[:-1]


class Rule(Widget, can_focus=False):
    """A rule widget to separate content, similar to a `<hr>` HTML tag."""

    DEFAULT_CSS = """
    Rule {
        color: $secondary;
    }

    Rule.-horizontal {
        height: 1;
        margin: 1 0;
        width: 1fr;      
    }

    Rule.-vertical {
        width: 1;
        margin: 0 2;
        height: 1fr;
    }
    """

    orientation: Reactive[RuleOrientation] = reactive[RuleOrientation]("horizontal")
    """The orientation of the rule."""

    line_style: Reactive[LineStyle] = reactive[LineStyle]("solid")
    """The line style of the rule."""

    def __init__(
        self,
        title="",
        orientation: RuleOrientation = "horizontal",
        line_style: LineStyle = "solid",
        cap_style: CapStyle = "none",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        """Initialize a rule widget.

        Args:
            orientation: The orientation of the rule.
            line_style: The line style of the rule.
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes of the widget.
            disabled: Whether the widget is disabled or not.
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.title = title
        self.orientation = orientation
        self.line_style = line_style
        self.cap_style = cap_style
        self.expand = True

    def render(self) -> RenderResult:
        rule_character: str
        title = self.title
        style = self.rich_style
        text_align = self.styles.text_align
        if self.orientation == "vertical":
            rule_character = _VERTICAL_LINE_CHARS[self.line_style]
            cap_character = _VERTICAL_CAP_CHARS[self.cap_style]
            return VerticalRuleRenderable(
                title,
                rule_character,
                cap_character,
                style,
                text_align,
                self.content_size.height,
            )
        elif self.orientation == "horizontal":
            rule_character = _HORIZONTAL_LINE_CHARS[self.line_style]
            cap_character = _HORIZONTAL_CAP_CHARS[self.cap_style]
            return HorizontalRuleRenderable(
                title,
                rule_character,
                cap_character,
                style,
                text_align,
                self.content_size.width,
            )
        else:
            raise InvalidRuleOrientation(
                f"Valid rule orientations are {friendly_list(_VALID_RULE_ORIENTATIONS)}"
            )

    def watch_orientation(
        self, old_orientation: RuleOrientation, orientation: RuleOrientation
    ) -> None:
        self.remove_class(f"-{old_orientation}")
        self.add_class(f"-{orientation}")

    def validate_orientation(self, orientation: RuleOrientation) -> RuleOrientation:
        if orientation not in _VALID_RULE_ORIENTATIONS:
            raise InvalidRuleOrientation(
                f"Valid rule orientations are {friendly_list(_VALID_RULE_ORIENTATIONS)}"
            )
        return orientation

    def validate_line_style(self, style: LineStyle) -> LineStyle:
        if style not in _VALID_LINE_STYLES:
            raise InvalidLineStyle(
                f"Valid rule line styles are {friendly_list(_VALID_LINE_STYLES)}"
            )
        return style

    def validate_cap_style(self, style: CapStyle) -> CapStyle:
        if style not in _VALID_CAP_STYLES:
            raise InvalidCapStyle(
                f"Valid rule cap styles are {friendly_list(_VALID_CAP_STYLES)}"
            )
        return style

    def get_content_width(self, container: Size, viewport: Size) -> int:
        if self.orientation == "horizontal":
            return container.width
        return 1

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        if self.orientation == "horizontal":
            return 1
        return container.height

    @classmethod
    def horizontal(
        cls,
        title="",
        line_style: LineStyle = "solid",
        cap_style: CapStyle = "none",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> Rule:
        """Utility constructor for creating a horizontal rule.

        Args:
            line_style: The line style of the rule.
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes of the widget.
            disabled: Whether the widget is disabled or not.

        Returns:
            A rule widget with horizontal orientation.
        """
        return Rule(
            title=title,
            orientation="horizontal",
            line_style=line_style,
            cap_style=cap_style,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )

    @classmethod
    def vertical(
        cls,
        title="",
        line_style: LineStyle = "solid",
        cap_style: CapStyle = "none",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> Rule:
        """Utility constructor for creating a vertical rule.

        Args:
            line_style: The line style of the rule.
            name: The name of the widget.
            id: The ID of the widget in the DOM.
            classes: The CSS classes of the widget.
            disabled: Whether the widget is disabled or not.

        Returns:
            A rule widget with vertical orientation.
        """
        return Rule(
            title=title,
            orientation="vertical",
            line_style=line_style,
            cap_style=cap_style,
            name=name,
            id=id,
            classes=classes,
            disabled=disabled,
        )
