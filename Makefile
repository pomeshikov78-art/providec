# АИС «Техноконтур» — команды разработки и эксплуатации
.PHONY: install dev test lint up down logs build wave0 verify test-dom demo clean

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

wave0:              ## сборка v101 из v100 — Волна 0 плана улучшений (детерминированная, с валидацией)
	python3 src10/patch_v101.py

verify:             ## статическая верификация v101 по критериям приёмки 0.1–0.8
	sh src10/verify_v101.sh

test-dom:           ## DOM-тесты клиента v101 (jsdom, 87 проверок; требуется установленный jsdom)
	cd /tmp && NODE_PATH=$(or $(NODE_PATH),/home/user/testenv/node_modules) node -e \
	  "process.argv[2]='$(CURDIR)/ais_providets_v101.html'; require('$(CURDIR)/src10/test_dom_v101.js')"

test-e2e:           ## E2E-тесты клиента (Playwright, 63 сценария × file:// и http://; см. tests/README.md)
	npx playwright test --config tests/playwright.config.js

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
	python -c "print('Откройте ais_providets.html (v101): демо-режим — выбрать роль и войти; серверный режим — включите тумблер, укажите http://localhost:8000, логин admin/tc-admin-2026 (MFA: TOTP из БД users)')"

clean:
	rm -f backend/technocontour.db backend/*.db-journal
