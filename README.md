
textual console

textual run --dev vgapui.sitrep

black vgapui && flake8 vgapui/*.py && black vgapui && mypy vgapui && textual run --dev vgapui.sitrep
