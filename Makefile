# АИС «Техноконтур» — команды разработки и эксплуатации
.PHONY: install dev test lint up down logs build wave0 v102 v103 verify test-dom test-e2e test-e2e-srv platform demo clean

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

wave0:              ## сборка v101 из v100 (историческая; цепочка воспроизведения: make wave0 v102 v103) — Волна 0 плана улучшений (детерминированная, с валидацией)
	python3 src10/patch_v101.py

v102:               ## сборка v102 из v101 — «Рабочая платформа» (фикс Д-10), детерминированная
	python3 src11/patch_v102.py

v103:               ## сборка v103 из v102 — «Серверная персистентность» (Этап 12), детерминированная
	python3 src12/patch_v103.py

verify:             ## статическая верификация актуального выпуска (Волна 0 + Д-10 + Этап 12)
	sh src12/verify_v103.sh

test-dom:           ## DOM-тесты клиента v103 (jsdom, 93 проверки; jsdom из node_modules)
	cd /tmp && NODE_PATH=$(CURDIR)/node_modules node -e \
	  "process.argv[2]='$(CURDIR)/ais_providets_v103.html'; require('$(CURDIR)/src12/test_dom_v103.js')"

test-e2e:           ## E2E демо-стенды (Playwright: file:// + http://, 63×2 сценария; см. tests/README.md)
	npx playwright test --config tests/playwright.config.js --project=file --project=http

test-e2e-srv:       ## E2E платформенный стенд (клиент против живого FastAPI, 10 сценариев)
	TC_WITH_BACKEND=1 npx playwright test --config tests/playwright.config.js --project=srv

platform:           ## живой протокол интеграции платформы (17 проверок LP-01…LP-17 против реального API)
	sh src10/run_platform.sh

build:              ## ВНИМАНИЕ: конвейер src/ заморожен на v13 (исторический). Актуальная сборка — `make wave0`.
	@echo "Конвейер src/assemble.sh соответствует исторической линейке v13 и НЕ собирает актуальный выпуск." >&2; \
	 echo "Актуальная сборка: make wave0  (v100 -> v101, см. src10/README.md)." >&2; \
	 if [ "$(FORCE)" != "1" ]; then echo "Принудительный запуск устаревшего конвейера: make build FORCE=1" >&2; exit 1; fi; \
	 sh src/assemble.sh ais_providets.html

up:                 ## стенд docker compose (БД + Redis + MinIO + backend + frontend)
	docker compose -f deploy/docker-compose.yml --profile monitoring up -d --build

down:
	docker compose -f deploy/docker-compose.yml --profile monitoring down

logs:
	docker compose -f deploy/docker-compose.yml logs -f backend

metrics:            ## проверить Prometheus-метрики
	python -c "import urllib.request;print(urllib.request.urlopen('http://localhost:8000/metrics').read().decode())"

demo:               ## демо: открыть клиент (демо-режим либо серверный: http://localhost:8000)
	python3 -c "print('Откройте ais_providets.html (v103): демо-режим — выбрать роль и войти; серверный режим — включите тумблер, укажите http://localhost:8000 (make dev), логин admin/tc-admin-2026, MFA: TOTP-код из секрета в БД users')"

clean:
	rm -f backend/technocontour.db backend/*.db-journal
