import re


def _csrf(html: str) -> str:
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _registrar(cliente, nombre_usuario, email=None, password="contrasena123"):
    html = cliente.get("/registro").text
    return cliente.post("/registro", data={
        "csrf_token": _csrf(html), "nombre_usuario": nombre_usuario, "email": email or f"{nombre_usuario}@example.test",
        "password": password, "password2": password,
    }, follow_redirects=False)


def _hacer_admin(cliente, nombre_usuario):
    # Simula el ascenso manual que hace el propietario del VPS la primera
    # vez (no hay UI para el primer admin: alguien ya admin asciende al
    # siguiente desde /usuarios-registrados, o se pone a mano en la BD).
    db = cliente.app.state.db
    usuario = db.obtener_usuario_por_nombre(nombre_usuario)
    db.actualizar_rol(usuario["id"], "admin")


def test_usuario_nuevo_tiene_rol_usuario_por_defecto(cliente):
    _registrar(cliente, "normal1", password="contrasena123")
    usuario = cliente.app.state.db.obtener_usuario_por_nombre("normal1")
    assert usuario["rol"] == "usuario"


def test_usuarios_registrados_requiere_login(cliente):
    assert cliente.get("/usuarios-registrados", follow_redirects=False).status_code == 303


def test_usuarios_registrados_prohibido_para_no_admin(cliente):
    _registrar(cliente, "normal2", password="contrasena123")
    r = cliente.get("/usuarios-registrados")
    assert r.status_code == 403


def test_admin_ve_la_lista_de_usuarios(cliente):
    _registrar(cliente, "admin1", password="contrasena123")
    _hacer_admin(cliente, "admin1")
    _registrar(cliente, "otro1", password="contrasena123")  # pisa la sesión; se vuelve a loguear como admin1 abajo

    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin1", "password": "contrasena123"})

    r = cliente.get("/usuarios-registrados")
    assert r.status_code == 200
    assert "admin1" in r.text and "otro1" in r.text


def test_admin_cambia_password_de_otro_usuario(cliente):
    _registrar(cliente, "admin2", password="contrasena123")
    _hacer_admin(cliente, "admin2")
    _registrar(cliente, "victima1", password="claveoriginal1")

    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin2", "password": "contrasena123"})
    objetivo = cliente.app.state.db.obtener_usuario_por_nombre("victima1")

    html2 = cliente.get("/usuarios-registrados").text
    r_mal = cliente.post(f"/usuarios-registrados/{objetivo['id']}/password", data={
        "csrf_token": _csrf(html2), "password_nueva": "clavenueva456", "password_nueva2": "clavenueva456",
        "password_admin": "incorrecta",
    })
    assert "no es correcta" in r_mal.text

    html3 = cliente.get("/usuarios-registrados").text
    r_ok = cliente.post(f"/usuarios-registrados/{objetivo['id']}/password", data={
        "csrf_token": _csrf(html3), "password_nueva": "clavenueva456", "password_nueva2": "clavenueva456",
        "password_admin": "contrasena123",
    })
    assert "actualizada" in r_ok.text

    # La contraseña nueva funciona para la víctima.
    from fastapi.testclient import TestClient
    victima = TestClient(cliente.app)
    html_v = victima.get("/login").text
    r_login = victima.post("/login", data={
        "csrf_token": _csrf(html_v), "nombre_usuario": "victima1", "password": "clavenueva456",
    }, follow_redirects=False)
    assert r_login.status_code == 303 and r_login.headers["location"] == "/"


def test_admin_no_puede_cambiarse_el_propio_rol(cliente):
    _registrar(cliente, "admin3", password="contrasena123")
    _hacer_admin(cliente, "admin3")
    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin3", "password": "contrasena123"})
    yo = cliente.app.state.db.obtener_usuario_por_nombre("admin3")

    html2 = cliente.get("/usuarios-registrados").text
    r = cliente.post(f"/usuarios-registrados/{yo['id']}/rol", data={
        "csrf_token": _csrf(html2), "rol_nuevo": "usuario", "password_admin": "contrasena123",
    })
    assert "No puedes cambiar tu propio rol" in r.text
    assert cliente.app.state.db.obtener_usuario_por_id(yo["id"])["rol"] == "admin"


def test_admin_asciende_a_otro_usuario(cliente):
    _registrar(cliente, "admin4", password="contrasena123")
    _hacer_admin(cliente, "admin4")
    _registrar(cliente, "ascenderme1", password="contrasena123")

    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin4", "password": "contrasena123"})
    objetivo = cliente.app.state.db.obtener_usuario_por_nombre("ascenderme1")

    html2 = cliente.get("/usuarios-registrados").text
    r = cliente.post(f"/usuarios-registrados/{objetivo['id']}/rol", data={
        "csrf_token": _csrf(html2), "rol_nuevo": "admin", "password_admin": "contrasena123",
    })
    assert "actualizado a admin" in r.text
    assert cliente.app.state.db.obtener_usuario_por_id(objetivo["id"])["rol"] == "admin"


def test_admin_panel_requiere_login(cliente):
    assert cliente.get("/admin", follow_redirects=False).status_code == 303


def test_admin_panel_prohibido_para_no_admin(cliente):
    _registrar(cliente, "normal3", password="contrasena123")
    assert cliente.get("/admin").status_code == 403


def test_admin_panel_enlaza_a_gestion_usuarios(cliente):
    _registrar(cliente, "admin5", password="contrasena123")
    _hacer_admin(cliente, "admin5")
    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin5", "password": "contrasena123"})

    r = cliente.get("/admin")
    assert r.status_code == 200
    assert "Gestión Usuarios" in r.text
    assert 'href="/usuarios-registrados"' in r.text


def test_header_admin_enlaza_al_panel_de_admin(cliente):
    _registrar(cliente, "admin6", password="contrasena123")
    _hacer_admin(cliente, "admin6")
    html = cliente.get("/login").text
    cliente.post("/login", data={"csrf_token": _csrf(html), "nombre_usuario": "admin6", "password": "contrasena123"})

    r = cliente.get("/")
    assert 'href="/admin"' in r.text
    assert re.search(r'href="/admin"[^<]*<svg.*?</svg>\s*Admin\s*</a>', r.text, re.S)
