"""
Servicio centralizado de gestión de fechas y zonas horarias (Timezone Architecture).
Garantiza que toda la lógica de negocio y persistencia en base de datos
opere con la zona horaria comercial local (America/Lima, UTC-5),
independientemente de la hora del sistema operativo o servidor en la nube.
"""
import os
from datetime import datetime, timezone, date, time, timedelta
from zoneinfo import ZoneInfo

# Configuración de Timezone Comercial (por defecto America/Lima, UTC-5)
APP_TIMEZONE_NAME = os.getenv("APP_TIMEZONE", "America/Lima")

try:
    LOCAL_TZ = ZoneInfo(APP_TIMEZONE_NAME)
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-5))

UTC_TZ = timezone.utc

def ahora_local() -> datetime:
    """Retorna el timestamp actual con timezone en la hora local comercial."""
    return datetime.now(LOCAL_TZ)

def ahora_utc() -> datetime:
    """Retorna el timestamp actual con timezone en UTC estándar."""
    return datetime.now(UTC_TZ)

def fecha_local() -> date:
    """Retorna la fecha calendario actual correspondiente a la hora local."""
    return ahora_local().date()

def hora_local() -> time:
    """Retorna la hora actual correspondiente a la hora local."""
    return ahora_local().time()

def a_local(dt: datetime) -> datetime:
    """
    Convierte cualquier objeto datetime a la zona horaria local.
    Si el objeto es naive (sin timezone), se asume UTC y se convierte a local.
    """
    if dt is None:
        return ahora_local()
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC_TZ)
    return dt.astimezone(LOCAL_TZ)

def a_utc(dt: datetime) -> datetime:
    """Convierte cualquier datetime a UTC (para persistencia o sincronización externa)."""
    if dt is None:
        return ahora_utc()
    if not isinstance(dt, datetime):
        return dt
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LOCAL_TZ)
    return dt.astimezone(UTC_TZ)

def formatear_fecha_hora(dt, formato: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Formatea un datetime en la zona horaria local comercial."""
    if dt is None:
        return ""
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return a_local(dt).strftime(formato)
    return str(dt)

