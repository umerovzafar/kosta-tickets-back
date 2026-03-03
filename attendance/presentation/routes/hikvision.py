from datetime import date
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query

from infrastructure.config import get_settings
from infrastructure.hikvision_client import get_attendance_from_devices

router = APIRouter(prefix="/hikvision", tags=["hikvision"])


def _parse_date(param: Optional[str]) -> Optional[date]:
    if not param:
        return None
    try:
        return date.fromisoformat(param)
    except ValueError:
        return None


def _record_matches_filters(
    rec: dict,
    person_id: Optional[str],
    name: Optional[str],
    department: Optional[str],
    checkpoint: Optional[str],
    attendance_status: Optional[str],
) -> bool:
    if person_id and (rec.get("person_id") or "").strip() != person_id.strip():
        return False
    if name:
        if name.lower() not in (rec.get("name") or "").lower():
            return False
    if department:
        if department.lower() not in (rec.get("department") or "").lower():
            return False
    if checkpoint:
        if checkpoint.lower() not in (rec.get("checkpoint") or "").lower():
            return False
    if attendance_status and (rec.get("attendance_status") or "").strip() != attendance_status.strip():
        return False
    return True


@router.get("/attendance")
async def get_attendance(
    date_from: Optional[str] = Query(None, description="Дата начала в формате YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Дата конца в формате YYYY-MM-DD"),
    max_records_per_device: int = Query(500, ge=1, le=5000),
    person_id: Optional[str] = Query(None, description="Фильтр по идентификатору сотрудника"),
    name: Optional[str] = Query(None, description="Фильтр по имени (contains, без регистра)"),
    department: Optional[str] = Query(None, description="Фильтр по подразделению (contains, без регистра)"),
    checkpoint: Optional[str] = Query(None, description="Фильтр по названию точки прохода (contains)"),
    attendance_status: Optional[str] = Query(None, description="Фильтр по статусу посещения (например, CheckIn)"),
    camera_ip: Optional[str] = Query(None, description="Ограничить список камер (один IP или несколько через запятую)"),
) -> List[dict]:
    """
    Получить события посещения с одной или нескольких камер Hikvision.

    Камеры настраиваются в .env через переменные:
    HIKVISION_DEVICE_IP, HIKVISION_DEVICE_PORT, HIKVISION_DEVICE_USER, HIKVISION_DEVICE_PASSWORD,
    HIKVISION_REQUEST_TIMEOUT, HIKVISION_DEVICE_IPS (список IP через запятую).

    Фильтрация выполняется по полям person_id, name, department, checkpoint, attendance_status.
    """
    settings = get_settings()
    hosts: list[str] = []
    if camera_ip:
        hosts = [h.strip() for h in camera_ip.split(",") if h.strip()]
    elif settings.hikvision_device_ips:
        hosts = [h.strip() for h in settings.hikvision_device_ips.split(",") if h.strip()]
    elif settings.hikvision_device_ip:
        hosts = [settings.hikvision_device_ip.strip()]

    if not hosts:
        raise HTTPException(status_code=400, detail="Не настроены IP камер (HIKVISION_DEVICE_IP(S)).")

    df = _parse_date(date_from)
    dt = _parse_date(date_to)
    results = get_attendance_from_devices(
        hosts=hosts,
        port=settings.hikvision_device_port,
        user=settings.hikvision_device_user,
        password=settings.hikvision_device_password,
        date_from=df,
        date_to=dt,
        max_records_per_device=max_records_per_device,
        timeout=settings.hikvision_request_timeout,
    )

    filtered_results: list[dict] = []
    for res in results:
        records = res.get("records") or []
        filtered = [
            r
            for r in records
            if _record_matches_filters(r, person_id, name, department, checkpoint, attendance_status)
        ]
        new_entry = dict(res)
        new_entry["records"] = filtered
        filtered_results.append(new_entry)

    return filtered_results

