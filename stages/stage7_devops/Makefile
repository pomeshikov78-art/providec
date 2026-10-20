# АИС «Техноконтур» — команды разработки и эксплуатации
.PHONY: install dev test lint up down logs build metrics demo clean

install:            ## установка зависимостей бэкенда
	pip install -r backend/requirements.txt

dev:                ## запуск бэкенда в dev-профиле (SQLite + in-process шина)
	cd backend && TC_DATABASE_URL=sqlite:///./technocontour.db TC_BUS_BACKEND=memory \
	  uvicorn app.main:app --reload --port 8000

test:               ## полный прогон тестов (ядро, данные, модули, гео, безопасность, интеграции)
	cd backend && python -m pytest tests/ -q

lint:
	ruff check backend/app --select E,F,W --ignore E501 || true
	node --check src/app.js && node --check src/server.js

build:              ## сборка единого HTML-клиента из исходников
	sh src/assemble.sh ais_providets.html

up:                 ## стенд docker compose (БД + Redis + MinIO + backend + frontend)
	docker compose -f deploy/docker-compose.yml --profile monitoring up -d --build

down:
	docker compose -f deploy/docker-compose.yml --profile monitoring down

logs:
	docker compose -f deploy/docker-compose.yml logs -f backend

metrics:            ## проверить Prometheus-метрики
	python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/metrics').read().decode())"

demo:               ## демо: открыть клиент (серверный режим: http://localhost:8000)
	python -c "print('Откройте ais_providets.html; в блоке «Серверный режим» укажите http://localhost:8000, логин admin/tc-admin-2026 (MFA: TOTP из БД users)')"

clean:
	rm -f backend/technocontour.db backend/*.db-journal
