"""Motor de recuperacion de archivos (stub expandible)."""
import os
from licencias import verificar_permiso

# Tipos de archivo recuperables
TIPOS = {
    "fotos":       [".jpg", ".jpeg", ".png", ".heic", ".raw"],
    "videos":      [".mp4", ".mov", ".avi", ".mkv"],
    "documentos":  [".pdf", ".docx", ".xlsx", ".txt", ".pptx"],
    "audio":       [".mp3", ".wav", ".m4a", ".flac"],
}

def _listar_archivos(ruta: str, extensiones: list[str]) -> list[str]:
    """Lista archivos con las extensiones dadas en la ruta."""
    encontrados = []
    try:
        for root, _, files in os.walk(ruta, onerror=lambda e: None):
            for f in files:
                if any(f.lower().endswith(ext) for ext in extensiones):
                    encontrados.append(os.path.join(root, f))
    except (PermissionError, OSError):
        pass
    return encontrados

def escanear(dispositivo: str, tipo_dispositivo: str, tipos_archivo: list[str]) -> dict:
    """
    Escanea un dispositivo y retorna resultados.
    tipo_dispositivo: 'usb' | 'disco_duro' | 'sd_card' | 'celular'
    tipos_archivo: lista de keys de TIPOS
    """
    if not verificar_permiso(tipo_dispositivo):
        return {
            "ok": False,
            "msg": f"Tu plan no incluye recuperación de '{tipo_dispositivo}'. Actualiza tu licencia.",
            "archivos": [],
        }
    try:
        existe = os.path.exists(dispositivo)
    except (OSError, ValueError):
        existe = False
    if not existe:
        return {"ok": False, "msg": f"Unidad '{dispositivo}' no encontrada o no conectada.", "archivos": []}

    exts = []
    for t in tipos_archivo:
        exts.extend(TIPOS.get(t, []))

    archivos = _listar_archivos(dispositivo, exts)
    return {
        "ok":       True,
        "msg":      f"{len(archivos)} archivos encontrados en {dispositivo}",
        "archivos": archivos,
    }

def recuperar(archivos: list[str], destino: str) -> dict:
    """Copia archivos al destino. Retorna resumen."""
    import shutil
    os.makedirs(destino, exist_ok=True)
    ok, errores = 0, []
    for src in archivos:
        try:
            shutil.copy2(src, destino)
            ok += 1
        except Exception as e:
            errores.append(str(e))
    return {"ok": True, "copiados": ok, "errores": errores}
