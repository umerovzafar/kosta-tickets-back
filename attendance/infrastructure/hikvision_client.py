from datetime import date
from typing import Any, Optional

import httpx


def _norm(s: Any, default: str = "-") -> str:
    if s is None or (isinstance(s, str) and not str(s).strip()):
        return default
    return str(s).strip()


def _norm_int(n: Any) -> Optional[int]:
    if n is None:
        return None
    try:
        return int(n)
    except (TypeError, ValueError):
        return None


def _parse_record_from_info(info: dict) -> dict:
    """Преобразование одной записи из InfoList (JSON) в удобный формат."""
    person_id = _norm(
        info.get("employeeNoString") or info.get("employeeNo") or info.get("cardNo"),
        "-",
    )
    name = _norm(info.get("name"))
    department = _norm(info.get("department"))
    time_val = _norm(info.get("time") or info.get("dateTime"), "")
    door_no = _norm_int(info.get("doorNo"))
    door_name = _norm(info.get("doorName"))
    checkpoint = door_name if door_name != "-" else (f"Door{door_no}" if door_no is not None else "Door")
    attendance_status = _norm(info.get("attendanceStatus"))
    label = _norm(info.get("label"), "")
    return {
        "person_id": person_id,
        "name": name,
        "department": department,
        "time": time_val or None,
        "checkpoint": checkpoint,
        "attendance_status": attendance_status,
        "door_no": door_no,
        "label": label,
    }


def _parse_json_response(body: dict) -> tuple[list[dict], int, int, str]:
    """Парсит JSON-ответ AcsEvent. Возвращает (records, totalMatches, numOfMatches, responseStatusStrg)."""
    acs = body.get("AcsEvent") or {}
    total = int(acs.get("totalMatches", 0) or 0)
    num = int(acs.get("numOfMatches", 0) or 0)
    status_str = _norm(acs.get("responseStatusStrg", ""), "")
    info_list = acs.get("InfoList") or []
    if isinstance(info_list, dict):
        info_list = info_list.get("InfoListItem") or info_list.get("info") or []
        if not isinstance(info_list, list):
            info_list = [info_list] if info_list else []
    records: list[dict] = []
    for item in info_list:
        if isinstance(item, dict):
            records.append(_parse_record_from_info(item))
    return records, total, num, status_str


def get_attendance_from_device(
    host: str,
    port: int = 80,
    user: str = "admin",
    password: str = "",
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    max_records: int = 2000,
    timeout: float = 60.0,
    use_basic_auth: bool = False,
) -> dict:
    if not host or not user:
        return {
            "records": [],
            "error": "Устройство не настроено (host, user)",
            "camera_ip": host or "-",
        }

    today = date.today()
    date_from = date_from or today
    date_to = date_to or date_from
    max_records = max(1, min(10000, max_records))

    start_time = f"{date_from.isoformat()}T00:00:00+00:00"
    end_time = f"{date_to.isoformat()}T23:59:59+00:00"

    base_url = f"http://{host}:{port}"
    path = "/ISAPI/AccessControl/AcsEvent"
    auth: httpx.Auth = (
        httpx.BasicAuth(user, password or "")
        if use_basic_auth
        else httpx.DigestAuth(user, password or "")
    )
    all_records: list[dict] = []
    use_json = True
    position = 0

    with httpx.Client(timeout=timeout, auth=auth) as client:
        while len(all_records) < max_records:
            page_size = min(10, max_records - len(all_records))
            body_json = {
                "AcsEventCond": {
                    "searchID": "1",
                    "searchResultPosition": position,
                    "maxResults": page_size,
                    "major": 5,
                    "minor": 0,
                    "startTime": start_time,
                    "endTime": end_time,
                }
            }
            try:
                url = f"{base_url}{path}?format=json" if use_json else f"{base_url}{path}?format=xml"
                if use_json:
                    resp = client.post(
                        url,
                        json=body_json,
                        headers={"Accept": "application/json"},
                    )
                else:
                    resp = client.post(url, json=body_json, headers={"Accept": "application/json"})
            except Exception as e:
                err_msg = str(e).strip().lower()
                if "timed out" in err_msg or "timeout" in err_msg:
                    return {
                        "records": all_records,
                        "error": (
                            "Таймаут подключения к устройству. Проверьте: "
                            "устройство доступно с сервера, IP/порт/логин/пароль в .env."
                        ),
                        "camera_ip": host,
                    }
                return {"records": all_records, "error": f"Ошибка подключения: {e}", "camera_ip": host}

            if resp.status_code != 200:
                if use_json and resp.status_code == 400 and "badJsonFormat" in (resp.text or ""):
                    use_json = False
                    continue
                return {
                    "records": all_records,
                    "error": f"HTTP {resp.status_code}: {(resp.text or '')[:200]}",
                    "camera_ip": host,
                }

            try:
                data = resp.json()
                records, total, num, status_str = _parse_json_response(data)
            except Exception as e:
                return {"records": all_records, "error": f"Ошибка разбора ответа: {e}", "camera_ip": host}

            all_records.extend(records)
            if status_str != "MORE" or num == 0:
                break
            position += num
            if position >= total:
                break

    return {"records": all_records, "error": None, "camera_ip": host}


def get_attendance_from_devices(
    hosts: list[str],
    port: int,
    user: str,
    password: str,
    date_from: Optional[date],
    date_to: Optional[date],
    max_records_per_device: int,
    timeout: float,
) -> list[dict]:
    """Запросить события сразу с нескольких устройств Hikvision."""
    results: list[dict] = []
    for host in hosts:
        host = host.strip()
        if not host:
            continue
        result = get_attendance_from_device(
            host=host,
            port=port,
            user=user,
            password=password,
            date_from=date_from,
            date_to=date_to,
            max_records=max_records_per_device,
            timeout=timeout,
        )
        results.append(result)
    return results

