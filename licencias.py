"""
Módulo de licencias Recovery Pro.
Verifica la licencia contra el servidor online.
Guarda en licencia.json: clave + cache del estado.
"""
import json, os, re
from datetime import datetime

_LIC_FILE  = os.path.join(os.path.dirname(__file__), "licencia.json")
SERVER_URL = os.environ.get("RECOVERY_SERVER", "https://recovery-pro.up.railway.app").rstrip("/")
MASTER_KEY = os.environ.get("MASTER_KEY", "admindasoto88")

_MASTER_RESP = {
    "activo": True, "plan": "ADMIN", "dias_restantes": 9999,
    "email": "admin@local", "fecha_fin": "2099-12-31",
    "permisos": {"usb": True, "disco_duro": True, "sd_card": True, "celular": True},
}

# Permisos por plan (para UI sin conexión temporal)
PLAN_LIMITES = {
    "BASICO": {
        "nombre": "Básico",
        "precio": 299,
        "permisos": {"usb": True, "disco_duro": False, "sd_card": False, "celular": False},
        "descripcion": "Solo recuperación USB",
    },
    "PRO": {
        "nombre": "Pro",
        "precio": 599,
        "permisos": {"usb": True, "disco_duro": True, "sd_card": True, "celular": False},
        "descripcion": "USB + Disco Duro + SD Card",
    },
    "PREMIUM": {
        "nombre": "Premium",
        "precio": 999,
        "permisos": {"usb": True, "disco_duro": True, "sd_card": True, "celular": True},
        "descripcion": "Todos los dispositivos",
    },
}

_FORMATO = re.compile(r"^RECOVERY-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")

def validar_formato(clave: str) -> bool:
    return bool(_FORMATO.match(clave.strip().upper()))

def verificar_online(clave: str) -> dict:
    """Consulta el servidor. Retorna dict con activo, plan, dias_restantes, msg."""
    try:
        import requests
        r = requests.get(f"{SERVER_URL}/api/verificar/{clave.strip().upper()}", timeout=6)
        return r.json()
    except Exception as e:
        return {"activo": None, "msg": f"Sin conexión al servidor: {e}"}

def guardar_licencia_local(clave: str, datos_servidor: dict):
    """Cachea resultado del servidor en licencia.json."""
    datos = {
        "clave":          clave.upper(),
        "plan":           datos_servidor.get("plan", ""),
        "email":          datos_servidor.get("email", ""),
        "dias_restantes": datos_servidor.get("dias_restantes", 0),
        "fecha_fin":      datos_servidor.get("fecha_fin", ""),
        "ultimo_check":   datetime.now().isoformat(),
    }
    with open(_LIC_FILE, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

def cargar_licencia_local() -> dict | None:
    if not os.path.exists(_LIC_FILE):
        return None
    try:
        with open(_LIC_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def activar(clave: str) -> dict:
    """Intenta activar la clave contra el servidor."""
    clave = clave.strip().upper()
    if clave == MASTER_KEY:
        guardar_licencia_local(clave, _MASTER_RESP)
        return {"ok": True, "msg": "🔐 Modo Admin activado.", "datos": _MASTER_RESP}
    if not validar_formato(clave):
        return {"ok": False, "msg": "Formato inválido. Usa: RECOVERY-XXXX-XXXX-XXXX"}
    res = verificar_online(clave)
    if res.get("activo") is None:
        return {"ok": False, "msg": res["msg"]}
    if not res["activo"]:
        return {"ok": False, "msg": res.get("msg", "Licencia inactiva o expirada")}
    guardar_licencia_local(clave, res)
    return {"ok": True, "msg": f"Licencia {res['plan']} activa. {res['dias_restantes']} días restantes.", "datos": res}

def estado_actual() -> dict:
    """
    Retorna estado de la licencia:
      - Si hay licencia local, verifica online (refresca caché).
      - Si no hay conexión, usa caché local.
    Retorna: {"activo": bool, "plan": str, "dias_restantes": int, "clave": str, ...}
    """
    local = cargar_licencia_local()
    if not local:
        return {"activo": False, "plan": None, "dias_restantes": 0, "clave": None}

    clave = local.get("clave", "")
    # MASTER_KEY: no necesita servidor
    if clave == MASTER_KEY:
        return {**_MASTER_RESP, "clave": clave}
    res   = verificar_online(clave)

    if res.get("activo") is None:
        # Sin conexión: usar caché (gracia de 24h)
        ultimo = local.get("ultimo_check", "")
        try:
            horas_sin_check = (datetime.now() - datetime.fromisoformat(ultimo)).total_seconds() / 3600
        except Exception:
            horas_sin_check = 999
        if horas_sin_check < 24 and local.get("dias_restantes", 0) > 0:
            local["sin_conexion"] = True
            return {**local, "activo": True}
        return {"activo": False, "plan": local.get("plan"), "dias_restantes": 0,
                "clave": clave, "msg": "Sin conexión y caché expirada"}

    if res["activo"]:
        guardar_licencia_local(clave, res)
    return {**res, "clave": clave, "activo": res["activo"]}

def verificar_permiso(accion: str) -> bool:
    """True si el plan activo permite la acción."""
    est = estado_actual()
    if not est.get("activo"):
        return False
    if est.get("plan") == "ADMIN":
        return True
    plan     = est.get("plan", "")
    permisos = PLAN_LIMITES.get(plan, {}).get("permisos", {})
    return permisos.get(accion, False)

def url_pago(plan: str, email: str = "") -> str:
    """URL de pago MercadoPago para el plan dado."""
    base = f"{SERVER_URL}/pagar/{plan}"
    if email:
        base += f"?email={email}"
    return base
