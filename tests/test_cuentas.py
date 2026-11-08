import re

from fastapi.testclient import TestClient


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _con_smtp(monkeypatch):
    """Activa el SMTP (solo para que smtp_configurado() sea True) e intercepta
    el envío real: los tests no deben tocar la red."""
    monkeypatch.setenv("SMTP_FROM", "pingunews@dockerlabs.es")
    enviados = []
    monkeypatch.setattr(
        "pingunews.web.mail._enviar",
        lambda destinatario, asunto, html: (enviados.append((destinatario, asunto, html)), True)[1],
    )
    return enviados


def _registrar(cliente, nombre_usuario="pingu1", email="pingu1@example.test", password="contrasena123"):
    html = cliente.get("/registro").text
    return cliente.post("/registro", data={
        "csrf_token": _csrf(html), "nombre_usuario": nombre_usuario, "email": email,
        "password": password, "password2": password,
    }, follow_redirects=False)


def test_registro_con_smtp_no_crea_usuario_hasta_verificar(cliente, monkeypatch):
    enviados = _con_smtp(monkeypatch)
    r = _registrar(cliente)
    assert r.status_code == 200 and "Revisa tu correo" in r.text
    assert cliente.get("/perfil", follow_redirects=False).status_code == 303  # no hay sesión: no se creó la cuenta
    assert len(enviados) == 1 and enviados[0][0] == "pingu1@example.test"


def test_verificar_correo_crea_la_cuenta_e_inicia_sesion(cliente, monkeypatch):
    enviados = _con_smtp(monkeypatch)
    _registrar(cliente)
    token = re.search(r"token=([\w-]+)", enviados[0][2]).group(1)

    r = cliente.get(f"/verificar-correo?token={token}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert cliente.get("/perfil").status_code == 200  # ya hay sesión

    # El enlace no se puede reutilizar.
    r2 = cliente.get(f"/verificar-correo?token={token}")
    assert "no es válido o ha caducado" in r2.text


def test_login_antes_de_verificar_pide_revisar_el_correo(cliente, monkeypatch):
    _con_smtp(monkeypatch)
    _registrar(cliente, nombre_usuario="pendiente1")
    html = cliente.get("/login").text
    r = cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "pendiente1", "password": "lo-que-sea"})
    assert "todavía no está verificada" in r.text


def test_registro_sin_smtp_crea_la_cuenta_directamente(cliente):
    # Sin SMTP configurado (no se ha llamado a _con_smtp) se cae al
    # comportamiento anterior: cuenta creada al momento.
    r = _registrar(cliente, nombre_usuario="sinsmtp1")
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert cliente.get("/perfil").status_code == 200


def test_olvide_password_mismo_mensaje_exista_o_no_el_correo(cliente, monkeypatch):
    _con_smtp(monkeypatch)
    _registrar(cliente, nombre_usuario="recupera1", email="recupera1@example.test")
    html = cliente.get("/olvide-password").text
    r1 = cliente.post("/olvide-password", data={"csrf_token": _csrf(html), "email": "no-existe@example.test"})
    html2 = cliente.get("/olvide-password").text
    r2 = cliente.post("/olvide-password", data={"csrf_token": _csrf(html2), "email": "recupera1@example.test"})
    assert "Si ese correo está registrado" in r1.text
    assert r1.text.split("Si ese correo")[1] == r2.text.split("Si ese correo")[1]


def test_reset_password_cambia_contrasena_e_invalida_otras_sesiones(cliente, monkeypatch):
    enviados = _con_smtp(monkeypatch)
    _registrar(cliente, nombre_usuario="reset1", email="reset1@example.test", password="claveoriginal1")
    token_verif = re.search(r"token=([\w-]+)", enviados[-1][2]).group(1)
    cliente.get(f"/verificar-correo?token={token_verif}")  # sesión A queda logueada

    otra_sesion = TestClient(cliente.app)  # sesión B: navegador distinto, mismo servidor
    html = otra_sesion.get("/olvide-password").text
    otra_sesion.post("/olvide-password", data={"csrf_token": _csrf(html), "email": "reset1@example.test"})
    token_reset = re.search(r"token=([\w-]+)", enviados[-1][2]).group(1)

    html_reset = otra_sesion.get(f"/restablecer-password?token={token_reset}").text
    r = otra_sesion.post("/restablecer-password", data={
        "csrf_token": _csrf(html_reset), "token": token_reset,
        "password": "clavenueva456", "password2": "clavenueva456",
    }, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?reset=ok"

    # La sesión A (abierta con la contraseña anterior) queda invalidada.
    assert cliente.get("/perfil", follow_redirects=False).status_code == 303

    # La contraseña nueva funciona en un login limpio.
    cliente3 = TestClient(cliente.app)
    html_login = cliente3.get("/login").text
    r_login = cliente3.post("/login", data={
        "csrf_token": _csrf(html_login), "nombre_usuario": "reset1", "password": "clavenueva456",
    }, follow_redirects=False)
    assert r_login.status_code == 303 and r_login.headers["location"] == "/"


def test_perfil_requiere_login(cliente):
    assert cliente.get("/perfil", follow_redirects=False).status_code == 303


def test_perfil_cambia_usuario_exige_password_correcta(cliente):
    _registrar(cliente, nombre_usuario="cambios1", password="contrasena123")
    html = cliente.get("/perfil").text
    r_mal = cliente.post("/perfil/usuario", data={
        "csrf_token": _csrf(html), "nombre_usuario_nuevo": "cambios1-nuevo", "password_actual": "incorrecta",
    })
    assert "no es correcta" in r_mal.text

    html2 = cliente.get("/perfil").text
    r_ok = cliente.post("/perfil/usuario", data={
        "csrf_token": _csrf(html2), "nombre_usuario_nuevo": "cambios1-nuevo", "password_actual": "contrasena123",
    })
    assert "cambios1-nuevo" in r_ok.text and "actualizado" in r_ok.text


def test_perfil_cambia_email_no_se_aplica_sin_confirmar(cliente, monkeypatch):
    enviados = _con_smtp(monkeypatch)
    _registrar(cliente, nombre_usuario="cambioemail1", email="viejo@example.test", password="contrasena123")
    token_verif = re.search(r"token=([\w-]+)", enviados[-1][2]).group(1)
    cliente.get(f"/verificar-correo?token={token_verif}")
    enviados.clear()

    html = cliente.get("/perfil").text
    r = cliente.post("/perfil/email", data={
        "csrf_token": _csrf(html), "email_nuevo": "nuevo@example.test", "password_actual": "contrasena123",
    })
    assert "Te hemos enviado un enlace" in r.text
    assert any(dest == "nuevo@example.test" for dest, _, _ in enviados)
    assert any(dest == "viejo@example.test" for dest, _, _ in enviados)  # aviso a la dirección antigua

    # Sin confirmar, el perfil sigue mostrando el correo antiguo.
    assert "viejo@example.test" in cliente.get("/perfil").text

    token = re.search(r"token=([\w-]+)", [h for d, a, h in enviados if d == "nuevo@example.test"][0]).group(1)
    cliente.get(f"/confirmar-cambio-correo?token={token}")
    assert "nuevo@example.test" in cliente.get("/perfil").text
