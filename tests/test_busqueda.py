from pingunews.web import busqueda

ITEMS = [
    {"titulo": "Vulnerabilidad en APT de Debian", "resumen": "root", "fuente": "Segu-Info", "autor": None},
    {"titulo": "Ataque a Binance", "resumen": "criptomonedas", "fuente": "WeLiveSecurity", "autor": "Ana"},
]


def test_sin_consulta_devuelve_todo():
    assert busqueda.filtrar(ITEMS, "") == ITEMS


def test_ignora_mayusculas_y_acentos():
    assert busqueda.filtrar(ITEMS, "VULNERABILIDÁD") == [ITEMS[0]]


def test_todas_las_palabras_deben_aparecer():
    assert busqueda.filtrar(ITEMS, "debian apt") == [ITEMS[0]]
    assert busqueda.filtrar(ITEMS, "debian binance") == []


def test_busca_en_fuente_y_autor():
    assert busqueda.filtrar(ITEMS, "welivesecurity") == [ITEMS[1]]
    assert busqueda.filtrar(ITEMS, "ana") == [ITEMS[1]]


def test_limpiar_consulta_recorta_y_colapsa_espacios():
    assert busqueda.limpiar_consulta("  a   b ") == "a b"
    assert len(busqueda.limpiar_consulta("x" * 500)) == busqueda.BUSQUEDA_MAX_CHARS
