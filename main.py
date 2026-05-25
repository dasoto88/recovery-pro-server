"""Recovery Pro — Aplicación cliente (Streamlit)."""
import streamlit as st
from licencias import (
    estado_actual, activar, verificar_permiso,
    url_pago, cargar_licencia_local, PLAN_LIMITES
)
from recovery_engine import escanear, recuperar

st.set_page_config(page_title="Recovery Pro", page_icon="💾", layout="centered")

# CSS
st.markdown("""
<style>
[data-testid="stAppViewContainer"]{background:#0f0f1a}
[data-testid="stSidebar"]{background:#16213e}
.st-emotion-cache-1wivap2{color:#fff}
.badge-plan{display:inline-block;background:#6C63FF;color:#fff;
            border-radius:8px;padding:4px 14px;font-size:.85rem;font-weight:700}
.dias-ok{color:#22c55e;font-weight:700}
.dias-warn{color:#f59e0b;font-weight:700}
.dias-exp{color:#ef4444;font-weight:700}
</style>
""", unsafe_allow_html=True)

# ── ESTADO DE LICENCIA ────────────────────────────────────────────────────────
est = estado_actual()
MODO_ADMIN = est.get("plan") == "ADMIN"

# ── SIN LICENCIA: PANTALLA DE ACTIVACIÓN ─────────────────────────────────────
if not est["activo"] and not est.get("clave"):
    st.title("💾 Recovery Pro")
    st.warning("No tienes una licencia activa. Activa tu clave o adquiere una.")

    tab_act, tab_comprar = st.tabs(["🔑 Tengo una clave", "💳 Quiero comprar"])

    with tab_act:
        with st.form("form_activar"):
            clave = st.text_input("Clave de licencia", placeholder="RECOVERY-XXXX-XXXX-XXXX",
                                  max_chars=22)
            if st.form_submit_button("✅ Activar", type="primary", use_container_width=True):
                res = activar(clave)
                if res["ok"]:
                    st.success(res["msg"])
                    st.rerun()
                else:
                    st.error(res["msg"])

    with tab_comprar:
        st.markdown("### Elige tu plan")
        col1, col2, col3 = st.columns(3)
        for col, plan_key in zip([col1, col2, col3], ["BASICO", "PRO", "PREMIUM"]):
            info = PLAN_LIMITES[plan_key]
            with col:
                st.markdown(f"**{info['nombre']}**")
                st.markdown(f"### ${info['precio']}/mes")
                st.caption(info["descripcion"])
                link = url_pago(plan_key)
                st.link_button(f"💳 Comprar {info['nombre']}", link,
                               use_container_width=True, type="primary")
    st.stop()

# ── LICENCIA EXPIRADA: RENOVACIÓN ─────────────────────────────────────────────
if not est["activo"] and est.get("clave"):
    local = cargar_licencia_local()
    email = local.get("email", "") if local else ""
    plan  = est.get("plan", "PRO")
    st.title("💾 Recovery Pro")
    st.error(f"⏰ Tu licencia **{PLAN_LIMITES.get(plan,{}).get('nombre',plan)}** ha expirado.")
    st.markdown("Renueva para seguir recuperando tus archivos:")
    link = url_pago(plan, email)
    st.link_button("🔄 Renovar licencia — MercadoPago", link, type="primary", use_container_width=True)
    st.caption("Al renovar, los días se suman automáticamente a tu licencia anterior.")

    st.divider()
    with st.expander("Usar otra clave o cambiar plan"):
        with st.form("form_cambiar"):
            nueva = st.text_input("Nueva clave", placeholder="RECOVERY-XXXX-XXXX-XXXX")
            if st.form_submit_button("Activar"):
                r = activar(nueva)
                if r["ok"]:
                    st.success(r["msg"]); st.rerun()
                else:
                    st.error(r["msg"])
    st.stop()

# ── PANEL PRINCIPAL (LICENCIA ACTIVA) ─────────────────────────────────────────
plan      = est.get("plan", "")
# MODO ADMIN: permisos totales, sin plan_limites
if MODO_ADMIN:
    info_plan = {"nombre": "🔐 Admin", "precio": 0, "permisos": {k: True for k in ["usb","disco_duro","sd_card","celular"]}, "descripcion": "Acceso total"}
    permisos  = info_plan["permisos"]
else:
    info_plan = PLAN_LIMITES.get(plan, {})
    permisos  = info_plan.get("permisos", {})
dias      = est.get("dias_restantes", 0)
email     = est.get("email", "")
clave     = est.get("clave", "")

# Header
st.title("💾 Recovery Pro")
c1, c2 = st.columns([3, 1])
with c1:
    st.markdown(f'<span class="badge-plan">{info_plan.get("nombre","")}</span>', unsafe_allow_html=True)
    clase_dias = "dias-ok" if dias > 7 else ("dias-warn" if dias > 0 else "dias-exp")
    st.markdown(f'<span class="{clase_dias}">⏳ {dias} días restantes</span> &nbsp;'
                f'<span style="color:#888;font-size:.85rem">| {email}</span>',
                unsafe_allow_html=True)
with c2:
    link_renov = url_pago(plan, email)
    st.link_button("🔄 Renovar", link_renov, use_container_width=True)

if est.get("sin_conexion"):
    st.warning("⚠️ Modo sin conexión — usando caché local (máx 24h)")

st.divider()

# Advertencia próximo a expirar
if 0 < dias <= 5:
    st.warning(f"⚠️ Tu licencia vence en **{dias} días**. Renueva ahora para no perder acceso.")
    st.link_button("💳 Renovar ahora", link_renov, type="primary")

# ── TABS PRINCIPALES ──────────────────────────────────────────────────────────
tab_scan, tab_mi_lic = st.tabs(["🔍 Recuperar Archivos", "🔑 Mi Licencia"])

with tab_scan:
    st.subheader("Selecciona dispositivo")

    dispositivos = {
        "usb":        "🔌 USB",
        "disco_duro": "💿 Disco Duro",
        "sd_card":    "📂 Tarjeta SD",
        "celular":    "📱 Celular Android",
    }

    disp_options = list(dispositivos.keys())
    disp_labels  = [
        dispositivos[k] + ("" if permisos.get(k) else " 🔒 (upgrade)")
        for k in disp_options
    ]

    tipo_disp = st.radio("Dispositivo", disp_options,
                         format_func=lambda k: dispositivos[k] + ("" if permisos.get(k) else " 🔒"),
                         horizontal=True)

    if not permisos.get(tipo_disp):
        planes_superiores = {
            "disco_duro": "PRO o PREMIUM", "sd_card": "PRO o PREMIUM", "celular": "PREMIUM"
        }
        req = planes_superiores.get(tipo_disp, "superior")
        st.error(f"Tu plan **{info_plan.get('nombre','')}** no incluye este dispositivo. "
                 f"Necesitas plan **{req}**.")
        st.link_button(f"💳 Actualizar plan", url_pago("PRO", email), type="primary")
        st.stop()

    ruta    = st.text_input("Ruta del dispositivo", placeholder="D:\\ o /media/usb")
    tipos   = st.multiselect("Tipos de archivo a buscar",
                             ["fotos", "videos", "documentos", "audio"],
                             default=["fotos", "documentos"])
    destino = st.text_input("Carpeta destino para guardar recuperados",
                            placeholder="C:\\Recuperados")

    if st.button("🚀 Iniciar Escaneo", type="primary", use_container_width=True):
        if not ruta or not tipos:
            st.warning("Completa la ruta y selecciona al menos un tipo.")
        else:
            with st.spinner("Escaneando dispositivo..."):
                res = escanear(ruta, tipo_disp, tipos)
            if res["ok"]:
                st.success(res["msg"])
                st.session_state["arch"] = res["archivos"]
            else:
                st.error(res["msg"])

    if st.session_state.get("arch"):
        arch = st.session_state["arch"]
        st.dataframe({"Archivo": arch}, use_container_width=True, hide_index=True)
        if destino:
            if st.button(f"💾 Recuperar {len(arch)} archivos", use_container_width=True):
                r = recuperar(arch, destino)
                st.success(f"✅ {r['copiados']} archivos recuperados en: {destino}")
                if r["errores"]:
                    st.warning(f"{len(r['errores'])} errores: {r['errores'][:3]}")

with tab_mi_lic:
    st.markdown("### 🔑 Datos de tu licencia")
    col_a, col_b = st.columns(2)
    col_a.metric("Plan",           info_plan.get("nombre", plan))
    col_b.metric("Días restantes", dias)
    st.code(clave, language=None)
    st.caption(f"Válida hasta: {est.get('fecha_fin','—')}  |  Email: {email}")

    st.markdown("---")
    st.markdown("### 🔄 Renovar / Cambiar plan")
    for pk, pi in PLAN_LIMITES.items():
        cc1, cc2 = st.columns([3, 1])
        cc1.markdown(f"**{pi['nombre']}** — ${pi['precio']}/mes · {pi['descripcion']}")
        cc2.link_button("Pagar", url_pago(pk, email), use_container_width=True,
                        type="primary" if pk == plan else "secondary")

    st.markdown("---")
    if st.button("⚠️ Olvidar licencia de este equipo", type="secondary"):
        import os as _os
        _lf = _os.path.join(_os.path.dirname(__file__), "licencia.json")
        if _os.path.exists(_lf):
            _os.remove(_lf)
        st.rerun()

    st.caption("💬 Soporte: wa.me/526331124596  |  dasoto88122911@gmail.com")
