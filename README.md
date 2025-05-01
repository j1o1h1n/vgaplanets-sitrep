# SitRep

View information about your VGA Planets games from the convenience of the terminal using [textualize](https://www.textualize.io/).

## Install

To install this project, download from github and install these dependencies.

```
pip install textual requests httpx textual_plotext
```

## Run

```
python -m sitrep.sitrep
```

## Development

If you want to develop, also install textual-dev

```
pip install textual-dev
```

Run the Textual console so that you can see log messages.

```
textual console
```

To simply run the UI in dev mode:

```
textual run --dev sitrep.sitrep
```

If you are doing development, use black, flake8 and mypy like this:

```
black sitrep && flake8 sitrep && black sitrep && mypy sitrep && textual run --dev sitrep.sitrep
```
