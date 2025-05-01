
## Install

```
pip install textual requests httpx textual_plotext
```

```
pip install textual-dev
```

## Dev Cycle

```
textual console

textual run --dev sitrep.sitrep

black sitrep && flake8 sitrep && black sitrep && mypy sitrep && textual run --dev sitrep.sitrep
```
