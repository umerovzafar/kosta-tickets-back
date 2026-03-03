from enum import Enum


class Role(str, Enum):
    EMPLOYEE = "Сотрудник"
    IT_DEPARTMENT = "IT отдел"
    PARTNER = "Партнер"
    ADMIN = "Администратор"
    OFFICE_MANAGER = "Офис менеджер"
