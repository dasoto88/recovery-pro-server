"""
Recovery Pro — Servidor de Licencias + Pagos MercadoPago
Desplegar en Railway / Render / VPS con las variables de entorno:
  MP_ACCESS_TOKEN   → token de producción MercadoPago
  APP_URL           → URL pública de este servidor (sin / al final)
  ADMIN_PASS        → contraseña panel admin
  SMTP_USER / SMTP_PASS → Gmail para enviar claves por correo
"""
import sqlite3, os, uuid, smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import Flask, request, jsonify, redirect, render_template_string

app = Flask(__name__)

# ── CONFIG ────────────────────────────────────────────────────────────────────
MP_TOKEN   = os.environ.get("MP_ACCESS_TOKEN", "")
APP_URL    = os.environ.get("APP_URL", "http://localhost:5000").rstrip("/")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "adminrecovery88")
SMTP_USER  = os.environ.get("SMTP_USER", "")
SMTP_PASS  = os.environ.get("SMTP_PASS", "")
DB_PATH    = os.path.join(os.path.dirname(__file__), "licencias.db")

PLANES = {
    "BASICO":   {"precio": 299,  "dias": 30, "nombre": "Básico"},
    "PRO":      {"precio": 599,  "dias": 30, "nombre": "Pro"},
    "PREMIUM":  {"precio": 999,  "dias": 30, "nombre": "Premium"},
}

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS licencias(
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            clave        TEXT UNIQUE NOT NULL,
            email        TEXT NOT NULL,
            plan         TEXT NOT NULL,
            fecha_inicio TEXT,
            fecha_fin    TEXT,
            activo       INTEGER DEFAULT 1,
            created_at   TEXT DEFAULT (datetime('now','localtime'))
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS pagos(
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id TEXT UNIQUE,
            email      TEXT,
            plan       TEXT,
            monto      REAL,
            status     TEXT,
            clave      TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS logs_verificacion(
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            clave      TEXT,
            ip         TEXT,
            resultado  TEXT,
            fecha      TEXT DEFAULT (datetime('now','localtime'))
        )""")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def _nueva_clave():
    partes = uuid.uuid4().hex.upper()
    return f"RECOVERY-{partes[0:4]}-{partes[4:8]}-{partes[8:12]}"

def _enviar_clave(email, clave, plan, fecha_fin):
    if not SMTP_USER or not SMTP_PASS:
        return
    msg = MIMEMultipart()
    msg["From"]    = SMTP_USER
    msg["To"]      = email
    msg["Subject"] = "✅ Tu licencia Recovery Pro está activa"
    dias_restantes = (datetime.fromisoformat(fecha_fin) - datetime.now()).days
    cuerpo = f"""
    <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;background:#0f0f1a;
                color:#fff;border-radius:16px;padding:2rem;border:1px solid #6C63FF">
      <h2 style="color:#00d4ff;text-align:center">💾 Recovery Pro</h2>
      <h3 style="color:#fff;text-align:center">¡Tu licencia está activa!</h3>
      <div style="background:#16213e;border-radius:12px;padding:1.5rem;margin:1.5rem 0;text-align:center">
        <p style="color:#aaa;margin:0 0 .5rem">Tu clave de licencia:</p>
        <p style="font-size:1.4rem;font-weight:900;color:#6C63FF;letter-spacing:2px">{clave}</p>
        <p style="color:#aaa;margin:.5rem 0 0">Plan: <b style="color:#fff">{PLANES[plan]['nombre']}</b></p>
        <p style="color:#aaa;margin:.2rem 0 0">Válida hasta: <b style="color:#fff">{fecha_fin[:10]}</b> ({dias_restantes} días)</p>
      </div>
      <p style="color:#aaa;font-size:.9rem;text-align:center">
        Ingresa esta clave en Recovery Pro para activar tu acceso.<br>
        Si tienes dudas escríbenos: <a href="https://wa.me/526331124596" style="color:#25D366">WhatsApp 633 112 4596</a>
      </p>
    </div>
    """
    msg.attach(MIMEText(cuerpo, "html"))
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_USER, email, msg.as_string())
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")

def _procesar_pago(payment_id: str):
    """Verifica pago con MP y activa/extiende licencia."""
    if not MP_TOKEN:
        return
    import mercadopago
    sdk  = mercadopago.SDK(MP_TOKEN)
    resp = sdk.payment().get(payment_id)
    p    = resp.get("response", {})
    if p.get("status") != "approved":
        return

    ext_ref = p.get("external_reference", "")  # formato: "PLAN|email"
    if "|" not in ext_ref:
        return
    plan, email = ext_ref.split("|", 1)
    if plan not in PLANES:
        return

    dias = PLANES[plan]["dias"]
    now  = datetime.now()

    with get_db() as db:
        # Evitar procesar el mismo pago dos veces
        if db.execute("SELECT id FROM pagos WHERE payment_id=?", (payment_id,)).fetchone():
            return

        lic = db.execute("SELECT * FROM licencias WHERE email=?", (email,)).fetchone()
        if lic:
            # Renovación: sumar días desde donde termina (o desde hoy si ya expiró)
            try:
                fin_actual = datetime.fromisoformat(lic["fecha_fin"])
                base = fin_actual if fin_actual > now else now
            except Exception:
                base = now
            nueva_fin = (base + timedelta(days=dias)).isoformat()
            clave = lic["clave"]
            db.execute("UPDATE licencias SET fecha_fin=?, plan=?, activo=1 WHERE email=?",
                       (nueva_fin, plan, email))
        else:
            # Alta nueva
            clave     = _nueva_clave()
            nueva_fin = (now + timedelta(days=dias)).isoformat()
            db.execute("""INSERT INTO licencias(clave,email,plan,fecha_inicio,fecha_fin,activo)
                          VALUES(?,?,?,?,?,1)""",
                       (clave, email, plan, now.isoformat(), nueva_fin))

        db.execute("""INSERT INTO pagos(payment_id,email,plan,monto,status,clave)
                      VALUES(?,?,?,?,?,?)""",
                   (payment_id, email, plan,
                    p.get("transaction_amount", 0), "approved", clave))

    _enviar_clave(email, clave, plan, nueva_fin)
    print(f"[PAGO OK] {email} → {plan} hasta {nueva_fin[:10]}")

# ── RUTAS DE PAGO ─────────────────────────────────────────────────────────────
@app.route("/pagar/<plan>")
def pagar(plan):
    """Redirige al checkout de MercadoPago."""
    email = request.args.get("email", "").strip()
    if plan not in PLANES:
        return "Plan inválido", 400
    if not email or "@" not in email:
        return render_template_string("""
        <html><body style="font-family:Arial;background:#0f0f1a;color:#fff;text-align:center;padding:4rem">
        <h2>💾 Recovery Pro — {{plan}}</h2>
        <p style="color:#aaa">Ingresa tu email para continuar con el pago:</p>
        <form method="get">
          <input name="email" type="email" placeholder="tu@email.com" required
                 style="padding:.8rem;border-radius:8px;border:1px solid #6C63FF;background:#16213e;
                        color:#fff;font-size:1rem;width:300px">
          <br><br>
          <button type="submit"
                  style="background:#6C63FF;color:#fff;border:none;border-radius:8px;
                         padding:.9rem 2rem;font-size:1rem;font-weight:700;cursor:pointer">
            💳 Continuar con el pago →
          </button>
        </form>
        </body></html>
        """, plan=PLANES[plan]["nombre"])

    if not MP_TOKEN:
        return "MP_ACCESS_TOKEN no configurado", 500

    import mercadopago
    sdk  = mercadopago.SDK(MP_TOKEN)
    info = PLANES[plan]
    pref = sdk.preference().create({
        "items": [{
            "title":       f"Recovery Pro — {info['nombre']}",
            "quantity":    1,
            "currency_id": "MXN",
            "unit_price":  float(info["precio"]),
        }],
        "payer":              {"email": email},
        "back_urls": {
            "success": f"{APP_URL}/pago_exitoso?plan={plan}&email={email}",
            "failure": f"{APP_URL}/pago_fallido",
            "pending": f"{APP_URL}/pago_pendiente",
        },
        "auto_return":        "approved",
        "external_reference": f"{plan}|{email}",
        "notification_url":   f"{APP_URL}/webhook",
    })
    link = pref["response"].get("init_point", "")
    if not link:
        return f"Error MP: {pref['response']}", 500
    return redirect(link)

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json or {}
    if data.get("type") == "payment":
        pid = data.get("data", {}).get("id")
        if pid:
            _procesar_pago(str(pid))
    return jsonify({"ok": True})

@app.route("/pago_exitoso")
def pago_exitoso():
    pid   = request.args.get("payment_id", "")
    plan  = request.args.get("plan", "")
    email = request.args.get("email", "")
    if pid:
        _procesar_pago(pid)
    return render_template_string("""
    <html><body style="font-family:Arial;background:#0f0f1a;color:#fff;text-align:center;padding:4rem">
      <div style="max-width:480px;margin:0 auto;background:#16213e;border-radius:20px;
                  padding:3rem;border:2px solid #22c55e">
        <div style="font-size:4rem">✅</div>
        <h2 style="color:#22c55e;margin:.5rem 0">¡Pago exitoso!</h2>
        <p style="color:#aaa">Revisa tu correo <b style="color:#fff">{{email}}</b>.<br>
        Recibirás tu clave de licencia en los próximos minutos.</p>
        <p style="margin-top:1.5rem;color:#aaa;font-size:.9rem">
          ¿No llega el correo? Escríbenos:
          <a href="https://wa.me/526331124596" style="color:#25D366">WhatsApp 633 112 4596</a>
        </p>
      </div>
    </body></html>
    """, email=email)

@app.route("/pago_fallido")
def pago_fallido():
    return render_template_string("""
    <html><body style="font-family:Arial;background:#0f0f1a;color:#fff;text-align:center;padding:4rem">
      <h2 style="color:#FF6584">❌ Pago no completado</h2>
      <p style="color:#aaa">Puedes intentarlo de nuevo o contactarnos.</p>
      <a href="https://wa.me/526331124596" style="color:#25D366">💬 WhatsApp 633 112 4596</a>
    </body></html>
    """)

@app.route("/test")
def test():
    return jsonify({"status": "OK", "server": "Recovery Pro", "ts": datetime.now().isoformat()})

# ── API DE VERIFICACIÓN (el cliente llama esto) ───────────────────────────────
@app.route("/api/verificar/<clave>")
def api_verificar(clave):
    with get_db() as db:
        lic = db.execute("SELECT * FROM licencias WHERE clave=?", (clave.strip().upper(),)).fetchone()
    if not lic:
        return jsonify({"activo": False, "msg": "Clave no encontrada"})
    try:
        fin        = datetime.fromisoformat(lic["fecha_fin"])
        dias_rest  = (fin - datetime.now()).days
    except Exception:
        dias_rest = 0
    resultado = "expirada" if (dias_rest < 0 or not lic["activo"]) else "ok"
    with get_db() as db:
        db.execute("INSERT INTO logs_verificacion(clave,ip,resultado) VALUES(?,?,?)",
                   (clave.upper(), request.remote_addr, resultado))
    if resultado == "expirada":
        return jsonify({"activo": False, "plan": lic["plan"], "dias_restantes": 0,
                        "email": lic["email"], "msg": "Licencia expirada"})
    return jsonify({
        "activo": True, "plan": lic["plan"],
        "dias_restantes": dias_rest,
        "fecha_fin": lic["fecha_fin"][:10],
        "email": lic["email"], "msg": "OK",
    })

# ── ADMIN PANEL ───────────────────────────────────────────────────────────────
ADMIN_HTML = """
<!DOCTYPE html><html lang="es">
<head><meta charset="UTF-8"><title>Admin — Recovery Pro</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Arial,sans-serif;background:#0f0f1a;color:#fff;padding:2rem}
h1{color:#6C63FF;margin-bottom:1rem}
table{width:100%;border-collapse:collapse;margin-top:.8rem}
th{background:#6C63FF;padding:.5rem .6rem;text-align:left;font-size:.82rem}
td{padding:.45rem .6rem;border-bottom:1px solid #1e1e2e;font-size:.82rem;vertical-align:middle}
tr:hover td{background:#16213e}
.badge{padding:.15rem .55rem;border-radius:5px;font-size:.72rem;font-weight:700}
.ok{background:#16a34a;color:#fff}.exp{background:#dc2626;color:#fff}
input,select{background:#16213e;color:#fff;border:1px solid #6C63FF;
             border-radius:7px;padding:.45rem .7rem;margin:.25rem}
.btn{border:none;border-radius:6px;padding:.3rem .7rem;cursor:pointer;
     font-weight:700;font-size:.78rem;margin:1px}
.btn-p{background:#6C63FF;color:#fff}
.btn-g{background:#16a34a;color:#fff}
.btn-y{background:#d97706;color:#fff}
.btn-r{background:#dc2626;color:#fff}
.card{background:#16213e;border-radius:12px;padding:1.2rem 1.5rem;margin-bottom:1.2rem;
      border:1px solid rgba(255,255,255,.07)}
.tabs{display:flex;gap:.5rem;margin-bottom:1.2rem}
.tab{padding:.5rem 1.2rem;border-radius:8px 8px 0 0;cursor:pointer;
     font-weight:700;background:#16213e;border:1px solid #333;border-bottom:none}
.tab.active{background:#6C63FF;border-color:#6C63FF;color:#fff}
.tab-content{display:none}.tab-content.active{display:block}
a{color:#6C63FF;text-decoration:none}
</style>
<script>
function showTab(id){
  document.querySelectorAll('.tab-content').forEach(e=>e.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(e=>e.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  document.querySelector('[data-tab="'+id+'"]').classList.add('active');
}
</script>
</head><body>
<h1>💾 Recovery Pro — Admin</h1>
{% if not autenticado %}
  <div class="card" style="max-width:320px">
    <h3 style="margin-bottom:1rem">Acceso admin</h3>
    <form method="post" action="/admin">
      <input type="password" name="pass" placeholder="Contraseña" style="width:100%"><br>
      <button type="submit" class="btn btn-p" style="margin-top:.5rem;width:100%;padding:.6rem">Entrar</button>
    </form>
  </div>
{% else %}
  <div class="card">
    <b>Crear / extender licencia manual</b>
    <form method="post" action="/admin/crear" style="display:flex;flex-wrap:wrap;align-items:center;gap:.2rem;margin-top:.5rem">
      <input type="email" name="email" placeholder="email cliente" required style="flex:1;min-width:200px">
      <select name="plan">
        <option value="BASICO">Básico $299</option>
        <option value="PRO" selected>Pro $599</option>
        <option value="PREMIUM">Premium $999</option>
      </select>
      <input type="number" name="dias" value="30" min="1" max="365" style="width:70px"> días
      <button type="submit" class="btn btn-g">✅ Crear / Extender</button>
    </form>
    {% if msg %}<p style="color:#22c55e;margin-top:.5rem">{{msg}}</p>{% endif %}
  </div>

  <div class="tabs">
    <div class="tab active" data-tab="tab-lic" onclick="showTab('tab-lic')">Licencias ({{licencias|length}})</div>
    <div class="tab" data-tab="tab-pagos" onclick="showTab('tab-pagos')">Pagos</div>
    <div class="tab" data-tab="tab-trafico" onclick="showTab('tab-trafico')">Tráfico</div>
  </div>

  <div id="tab-lic" class="tab-content active">
    <table>
      <tr><th>Clave</th><th>Email</th><th>Plan</th><th>Hasta</th><th>Días</th><th>Estado</th><th>Acciones</th></tr>
      {% for l in licencias %}
      <tr>
        <td style="font-family:monospace;font-size:.78rem">{{l.clave}}</td>
        <td>{{l.email}}</td><td>{{l.plan}}</td>
        <td>{{l.fecha_fin[:10]}}</td>
        <td>{{l.dias}}</td>
        <td><span class="badge {{'ok' if l.dias > 0 and l.activo else 'exp'}}">
          {{'ACTIVA' if l.dias > 0 and l.activo else 'EXPIRADA'}}
        </span></td>
        <td>
          <form method="post" action="/admin/accion/{{l.id}}" style="display:inline">
            <button name="accion" value="extender" class="btn btn-g" title="+30 días">+30d</button>
            <button name="accion" value="pro"      class="btn btn-p" title="Cambiar a PRO">PRO</button>
            <button name="accion" value="toggle"   class="btn btn-y"
              title="{{'Desactivar' if l.activo else 'Activar'}}">{{'❌' if l.activo else '✅'}}</button>
            <button name="accion" value="eliminar" class="btn btn-r"
              onclick="return confirm('¿Eliminar licencia de {{l.email}}?')">🗑</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div id="tab-pagos" class="tab-content">
    <table>
      <tr><th>Payment ID</th><th>Email</th><th>Plan</th><th>Monto</th><th>Fecha</th></tr>
      {% for p in pagos %}
      <tr>
        <td style="font-size:.75rem">{{p.payment_id}}</td>
        <td>{{p.email}}</td><td>{{p.plan}}</td>
        <td>${{p.monto}}</td><td>{{p.created_at[:16]}}</td>
      </tr>
      {% endfor %}
    </table>
  </div>

  <div id="tab-trafico" class="tab-content">
    <table>
      <tr><th>Fecha</th><th>Verificaciones</th><th>OK</th><th>Expiradas</th><th>No encontradas</th></tr>
      {% for t in trafico %}
      <tr>
        <td>{{t.fecha}}</td><td>{{t.total}}</td>
        <td style="color:#22c55e">{{t.ok}}</td>
        <td style="color:#f59e0b">{{t.expiradas}}</td>
        <td style="color:#ef4444">{{t.no_encontradas}}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
  <div style="margin-top:1.5rem"><a href="/admin/logout">🔓 Cerrar sesión</a></div>
{% endif %}
</body></html>
"""

@app.route("/admin", methods=["GET", "POST"])
def admin():
    from flask import session
    autenticado = session.get("admin", False)
    if request.method == "POST":
        if request.form.get("pass") == ADMIN_PASS:
            session["admin"] = True
            autenticado = True
    licencias, pagos, trafico = [], [], []
    if autenticado:
        now = datetime.now()
        with get_db() as db:
            rows = db.execute("SELECT * FROM licencias ORDER BY id DESC").fetchall()
            for r in rows:
                d = dict(r)
                try:
                    d["dias"] = (datetime.fromisoformat(d["fecha_fin"]) - now).days
                except Exception:
                    d["dias"] = 0
                licencias.append(d)
            pagos = [dict(p) for p in
                     db.execute("SELECT * FROM pagos ORDER BY id DESC LIMIT 50").fetchall()]
            try:
                rows_t = db.execute("""
                    SELECT DATE(fecha) as fecha,
                           COUNT(*) as total,
                           SUM(resultado='ok') as ok,
                           SUM(resultado='expirada') as expiradas,
                           SUM(resultado='no_encontrada') as no_encontradas
                    FROM logs_verificacion
                    WHERE fecha >= datetime('now','-30 days','localtime')
                    GROUP BY DATE(fecha) ORDER BY fecha DESC
                """).fetchall()
                trafico = [dict(r) for r in rows_t]
            except Exception:
                trafico = []
    return render_template_string(ADMIN_HTML, autenticado=autenticado,
                                  licencias=licencias, pagos=pagos,
                                  trafico=trafico, msg="")

@app.route("/admin/crear", methods=["POST"])
def admin_crear():
    from flask import session
    if not session.get("admin"):
        return redirect("/admin")
    email = request.form.get("email", "").strip()
    plan  = request.form.get("plan", "PRO")
    dias  = int(request.form.get("dias", 30))
    if not email or plan not in PLANES:
        return redirect("/admin")
    clave     = _nueva_clave()
    fecha_fin = (datetime.now() + timedelta(days=dias)).isoformat()
    with get_db() as db:
        lic = db.execute("SELECT * FROM licencias WHERE email=?", (email,)).fetchone()
        if lic:
            now = datetime.now()
            try:
                base = datetime.fromisoformat(lic["fecha_fin"])
                base = base if base > now else now
            except Exception:
                base = now
            fecha_fin = (base + timedelta(days=dias)).isoformat()
            clave = lic["clave"]
            db.execute("UPDATE licencias SET fecha_fin=?,plan=?,activo=1 WHERE email=?",
                       (fecha_fin, plan, email))
        else:
            db.execute("""INSERT INTO licencias(clave,email,plan,fecha_inicio,fecha_fin,activo)
                          VALUES(?,?,?,?,?,1)""",
                       (clave, email, plan, datetime.now().isoformat(), fecha_fin))
    _enviar_clave(email, clave, plan, fecha_fin)
    return redirect("/admin")

@app.route("/admin/accion/<int:lic_id>", methods=["POST"])
def admin_accion(lic_id):
    from flask import session
    if not session.get("admin"):
        return redirect("/admin")
    accion = request.form.get("accion", "")
    with get_db() as db:
        lic = db.execute("SELECT * FROM licencias WHERE id=?", (lic_id,)).fetchone()
        if not lic:
            return redirect("/admin")
        if accion == "extender":
            now = datetime.now()
            try:
                base = datetime.fromisoformat(lic["fecha_fin"])
                base = base if base > now else now
            except Exception:
                base = now
            nueva_fin = (base + timedelta(days=30)).isoformat()
            db.execute("UPDATE licencias SET fecha_fin=?,activo=1 WHERE id=?", (nueva_fin, lic_id))
        elif accion == "pro":
            db.execute("UPDATE licencias SET plan='PRO' WHERE id=?", (lic_id,))
        elif accion == "toggle":
            db.execute("UPDATE licencias SET activo=? WHERE id=?",
                       (0 if lic["activo"] else 1, lic_id))
        elif accion == "eliminar":
            db.execute("DELETE FROM licencias WHERE id=?", (lic_id,))
    return redirect("/admin")

@app.route("/admin/logout")
def admin_logout():
    from flask import session
    session.pop("admin", None)
    return redirect("/admin")

app.secret_key = os.environ.get("SECRET_KEY", "recovery_secret_2026")
init_db()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
