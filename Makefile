.DEFAULT_GOAL := help
PYTHON ?= python3
VENV := .venv
BIN := $(VENV)/bin

.PHONY: help venv install dev-install run test lint fmt clean docker-build docker-up docker-down docker-logs

help: ## Hiển thị danh sách lệnh
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

venv: ## Tạo virtual environment
	$(PYTHON) -m venv $(VENV)

install: venv ## Cài thư viện chạy
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements.txt

dev-install: venv ## Cài thư viện phát triển
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -r requirements-dev.txt

run: ## Chạy bot (cần bot_token.txt)
	$(BIN)/python -m app.main

test: ## Chạy unit test
	$(BIN)/python -m unittest discover -s tests -p 'test_*.py' -v

lint: ## Kiểm tra bằng ruff
	$(BIN)/ruff check .

fmt: ## Định dạng bằng ruff
	$(BIN)/ruff format .

clean: ## Xóa cache và file tạm
	rm -rf $(VENV) .ruff_cache .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

docker-build: ## Build Docker image
	docker compose build

docker-up: ## Chạy bằng Docker Compose
	docker compose up -d --build

docker-down: ## Dừng Docker Compose
	docker compose down

docker-logs: ## Xem log Docker
	docker compose logs -f bot
