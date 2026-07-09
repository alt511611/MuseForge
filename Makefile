.PHONY: help install server client test lint docker-up docker-down

help:
	@echo "MuseForge — common tasks"
	@echo "  make install      Install server + client dependencies"
	@echo "  make server       Run the FastAPI backend (:8000)"
	@echo "  make client       Run the Next.js frontend (:3000)"
	@echo "  make test         Run the backend test suite"
	@echo "  make docker-up    Build & run the full stack via docker compose"
	@echo "  make docker-down  Stop the docker compose stack"

install:
	cd server && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
	cd client && npm install

server:
	cd server && .venv/bin/python api.py

client:
	cd client && npm run dev

test:
	cd server && .venv/bin/python -m pytest -v

docker-up:
	docker compose up --build

docker-down:
	docker compose down
