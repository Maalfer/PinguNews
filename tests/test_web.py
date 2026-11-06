def test_panel_lista_noticias(cliente):
    r = cliente.get("/?dias=30")
    assert r.status_code == 200
    assert "Vulnerabilidad en APT" in r.text and "Ataque a Binance" in r.text


def test_busqueda_filtra_y_escapa(cliente):
    r = cliente.get("/?dias=30&q=debian")
    assert "Vulnerabilidad en APT" in r.text and "Ataque a Binance" not in r.text
    r = cliente.get("/?dias=30&q=<script>alert(1)</script>")
    assert "<script>alert(1)" not in r.text


def test_cabeceras_de_seguridad(cliente):
    r = cliente.get("/")
    assert "nonce-" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"


def test_paginas_legales_y_login(cliente):
    for ruta in ("/aviso-legal", "/privacidad", "/cookies", "/login", "/registro"):
        assert cliente.get(ruta).status_code == 200


def test_guardados_exige_login(cliente):
    r = cliente.get("/guardados", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_post_sin_csrf_rechazado(cliente):
    assert cliente.post("/logout", data={"csrf_token": "falso"}).status_code == 403


def test_404_html(cliente):
    r = cliente.get("/no-existe", headers={"accept": "text/html"})
    assert r.status_code == 404
