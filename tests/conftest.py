from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from pingunews.config import cargar_config
from pingunews.models import Item


@pytest.fixture(autouse=True)
def _ratelimit_limpio():
    """El limitador de intentos (web/ratelimit.py) es estado global en memoria,
    no por app/test: sin esto, los tests de un archivo pueden agotar el cupo
    de intentos de registro/login y hacer fallar con 429 a los de otro."""
    from pingunews.web import ratelimit
    ratelimit._INTENTOS_RECIENTES.clear()
    ratelimit._FALLOS_USUARIO.clear()
    yield
    ratelimit._INTENTOS_RECIENTES.clear()
    ratelimit._FALLOS_USUARIO.clear()


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """App real con una BD y un log temporales (no toca data/ ni logs/)."""
    monkeypatch.setenv("SESSION_SECRET_KEY", "clave-de-test")
    monkeypatch.setattr("pingunews.web.app.ruta_db", lambda c: str(tmp_path / "test.db"))
    monkeypatch.setattr("pingunews.web.app.ruta_log", lambda c: str(tmp_path / "test.log"))
    from pingunews.web.app import create_app

    app = create_app(cargar_config())
    ahora = datetime.now(timezone.utc)
    app.state.db.guardar([
        Item("Vulnerabilidad en APT de Debian", "https://x.test/1", "Segu-Info", "ciberseguridad", ahora,
             resumen="Permite ejecutar código como root", origen_tipo="rss"),
        Item("Ataque a Binance roba millones", "https://x.test/2", "WeLiveSecurity", "ciberseguridad", ahora,
             resumen="Plataforma de criptomonedas", origen_tipo="rss"),
    ])
    return TestClient(app)
