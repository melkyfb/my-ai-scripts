# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Collection of small, focused utility scripts in various languages. Each script solves one task and is usable directly from the terminal.

## Planned scripts (categories)

- **Image generation** — generate images from a terminal prompt (likely via API, e.g. OpenAI/Stability)
- **PDF tools** — create PDFs from images; diary PDFs with a repeated image N times; reduce a PDF to plain text for AI ingestion
- **Web tools** — given a URL, extract a sitemap or scrape content into a format suitable for an AI knowledge base
- **Git wrapper** — simplified/aliased git commands to reduce friction in daily use

## Conventions

- Each script should be self-contained and runnable from the terminal with minimal setup
- Scripts that require API keys or external dependencies should document them at the top of the file
- Prefer a consistent CLI style within each language (e.g. `argparse` for Python, `flag`/`cobra` for Go)
- Name scripts descriptively: `pdf-from-images`, `site-scraper`, `git-wrap`, etc.
