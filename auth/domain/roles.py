from enum import Enum


class Role(str, Enum):
    EMPLOYEE = "Сотрудник"
    IT_DEPARTMENT = "IT отдел"
    PARTNER = "Партнер"
    ADMIN = "Администратор"
    MAIN_ADMIN = "Главный администратор"
    OFFICE_MANAGER = "Офис менеджер"


class TimeTrackingRole(str, Enum):
    """Роль пользователя в модуле учёта времени."""

    USER = "user"  # ведение учёта времени
    MANAGER = "manager"  # управление списком пользователей и доступом
