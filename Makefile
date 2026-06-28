.PHONY: help venv tui test apple-health gen-svg lint check format build ci

help:
	@echo "Available targets:"
	@echo "  make venv          - Create venv and install Python dependencies (uv sync)"
	@echo "  make tui           - Run the Textual TUI"
	@echo "  make test          - Run Python tests"
	@echo "  make apple-health  - Sync Apple Health data (set EXPORT_PATH, default: apple_health_export)"
	@echo "  make gen-svg       - Generate SVG assets from database"
	@echo "  make lint          - Run frontend lint"
	@echo "  make check         - Run frontend format check"
	@echo "  make format        - Format frontend files"
	@echo "  make build         - Build frontend assets"
	@echo "  make ci            - Run test, lint, check, and build"

venv:
	uv sync

tui:
	uv run run_page

test:
	uv run python -m unittest discover -s . -p 'test_*.py'

apple-health:
	uv run python run_page/apple_health_sync.py $(or $(EXPORT_PATH),apple_health_export) $(APPLE_HEALTH_ARGS)

gen-svg:
	uv run python run_page/gen_svg.py --from-db --type github --output assets/github.svg
	uv run python run_page/gen_svg.py --from-db --type grid --output assets/grid.svg

lint:
	pnpm run lint

check:
	pnpm run check

format:
	pnpm run format

build:
	pnpm run build

ci: test lint check build
