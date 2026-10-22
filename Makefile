SHELL := /bin/bash
VENV ?= .venv
PY := $(VENV)/bin/python
export PYTHONPATH := backend

.PHONY: help install dev run build test demo bench-dry clean fmt

help:
	@echo "make install    venv + dépendances backend/frontend"
	@echo "make dev        backend :8000 + Vite :5173 (proxy /api)"
	@echo "make run        build UI puis un seul process sur :8000"
	@echo "make test       suite pytest (aucun GPU requis)"
	@echo "make demo       parcours complet en simulation + export QC"
	@echo "make bench-dry  plan des 3 benchmarks + estimations de coût"
	@echo "make clean      supprime données locales et build"

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip
	$(VENV)/bin/pip install -q -r backend/requirements.txt
	cd frontend && npm install --no-audit --no-fund

dev:
	bash scripts/dev.sh

run:
	bash scripts/run.sh

build:
	cd frontend && npm run build

test:
	$(PY) -m pytest tests -q

demo:
	$(PY) scripts/demo_offline.py

bench-dry:
	$(PY) benchmarks/run_benchmark.py --all --dry-run --json benchmarks/results/plan.json

clean:
	rm -rf data/studio.db data/studio.db-wal data/studio.db-shm data/projects data/tmp data/uploads
	rm -rf frontend/dist .pytest_cache
