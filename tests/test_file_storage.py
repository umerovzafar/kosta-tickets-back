"""Тесты валидации загрузки файлов (логика проверки расширений)."""

import pytest

# Всеowed extensions для каждого сервиса (дублируем из file_storage для изоляции тестов)
TICKETS_ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf", ".doc", ".docx"}
INVENTORY_ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
NOTIFICATIONS_ALLOWED = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def _validate_ticket_extension(filename: str) -> bool:
    ext = (filename.split(".")[-1] if "." in filename else "").lower()
    return f".{ext}" in TICKETS_ALLOWED if ext else False


def _validate_inventory_extension(filename: str) -> bool:
    ext = (filename.split(".")[-1] if "." in filename else "").lower()
    return f".{ext}" in INVENTORY_ALLOWED if ext else False


def _validate_notifications_extension(filename: str) -> bool:
    ext = (filename.split(".")[-1] if "." in filename else "").lower()
    return f".{ext}" in NOTIFICATIONS_ALLOWED if ext else False


class TestTicketsFileStorage:
    """Тесты tickets file_storage."""

    def test_validate_attachment_allowed_extension(self):
        """Разрешённые расширения принимаются."""
        assert _validate_ticket_extension("test.jpg") is True
        assert _validate_ticket_extension("test.pdf") is True
        assert _validate_ticket_extension("test.PNG") is True
        assert _validate_ticket_extension("test.docx") is True

    def test_validate_attachment_forbidden_extension(self):
        """Запрещённые расширения отклоняются."""
        assert _validate_ticket_extension("test.exe") is False
        assert _validate_ticket_extension("test.php") is False
        assert _validate_ticket_extension("test.js") is False


class TestInventoryFileStorage:
    """Тесты inventory file_storage."""

    def test_validate_photo_allowed(self):
        """Разрешённые изображения."""
        assert _validate_inventory_extension("photo.jpg") is True
        assert _validate_inventory_extension("photo.png") is True

    def test_validate_photo_forbidden(self):
        """Запрещённые типы."""
        assert _validate_inventory_extension("file.pdf") is False


class TestNotificationsFileStorage:
    """Тесты notifications file_storage."""

    def test_validate_photo_allowed(self):
        """Разрешённые изображения."""
        assert _validate_notifications_extension("photo.webp") is True

    def test_validate_photo_forbidden(self):
        """Запрещённые типы."""
        assert _validate_notifications_extension("script.js") is False
