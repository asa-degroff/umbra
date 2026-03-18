.PHONY: up down proxy proxy-stop bot dashboard status migrate verify

# Infrastructure
up:
	docker compose up -d

down:
	docker compose down

proxy:
	@echo "Starting claude-max-api-proxy on :3456..."
	nohup claude-max-api > /tmp/claude-proxy.log 2>&1 & echo $$! > /tmp/claude-proxy.pid
	@echo "PID: $$(cat /tmp/claude-proxy.pid)"

proxy-stop:
	@if [ -f /tmp/claude-proxy.pid ]; then \
		kill $$(cat /tmp/claude-proxy.pid) 2>/dev/null && echo "Proxy stopped" || echo "Proxy not running"; \
		rm -f /tmp/claude-proxy.pid; \
	else \
		echo "No PID file found"; \
	fi

# Bot
bot:
	cd bot && source ../.venv/bin/activate && python bsky.py

# Dashboard
dashboard:
	cd dashboard/backend && source ../../.venv/bin/activate && uvicorn main:app --host 0.0.0.0 --port 8081

# Health checks
status:
	@echo "=== Letta Server ==="
	@curl -sf http://localhost:8283/v1/health 2>/dev/null && echo "OK" || echo "DOWN"
	@echo ""
	@echo "=== Ollama ==="
	@curl -sf http://localhost:11434/api/tags 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print('OK -', len(d.get('models',[])), 'models')" 2>/dev/null || echo "DOWN"
	@echo ""
	@echo "=== Claude Proxy ==="
	@curl -sf http://localhost:3456/v1/models 2>/dev/null && echo "OK" || echo "DOWN"
	@echo ""
	@echo "=== Dashboard ==="
	@curl -sf http://localhost:8081/ 2>/dev/null > /dev/null && echo "OK" || echo "DOWN"

# Migration
migrate:
	cd migration && source ../.venv/bin/activate && python export_from_cloud.py && python import_to_selfhosted.py

verify:
	cd migration && source ../.venv/bin/activate && python verify_migration.py
