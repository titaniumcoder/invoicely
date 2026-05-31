# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**invoicely** — Python 3.13 project, managed with `uv`.

## Commands

```bash
uv run python main.py       # run the app
uv run pytest               # run tests (once pytest is added)
uv add <package>            # add a dependency
```

## Architecture

Early-stage project. Currently a single entry point (`main.py`) with no modules or packages yet. As the project grows, structure should follow here.
