# Скрипты мок-данных time tracking (из корня tickets-back)
# Требуется: Python, .env с TIME_TRACKING_DATABASE_URL / DATABASE_URL
#
#   make mock-help
#   make mock-seed
#   make mock-reset EXTRA="--weeks 10"
#
# На Windows без make:  python mock_data.py seed

.PHONY: mock-help mock-seed mock-delete mock-delete-apply mock-reset mock-tt

PY ?= python3
export PYTHONPATH := time_tracking

mock-help:
	@echo "make mock-seed             — сид (доп. аргументы: EXTRA=... )"
	@echo "make mock-delete            — сухой прогон удаления"
	@echo "make mock-delete-apply      — удаление из БД"
	@echo "make mock-reset            — delete --apply + seed (EXTRA -> только seed)"
	@echo "make mock-tt ARGS='...'    — произвольный вызов tt_mock_data.py"
	@echo "Пример: make mock-reset EXTRA=\"--weeks 12\""

mock-seed:
	$(PY) time_tracking/scripts/seed_mock_data.py $(EXTRA)

mock-delete:
	$(PY) time_tracking/scripts/delete_mock_data.py $(EXTRA)

mock-delete-apply:
	$(PY) time_tracking/scripts/delete_mock_data.py --apply $(EXTRA)

mock-reset:
	$(PY) time_tracking/scripts/reset_mock_data.py $(EXTRA)

mock-tt:
	$(PY) time_tracking/scripts/tt_mock_data.py $(ARGS)
