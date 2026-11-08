from xml.etree import ElementTree as ET


def _parsear(r):
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/rss+xml")
    return ET.fromstring(r.text)


def test_feed_es_rss_valido_con_las_noticias(cliente):
    r = cliente.get("/feed.xml")
    raiz = _parsear(r)
    assert raiz.tag == "rss"
    canal = raiz.find("channel")
    titulos = {item.find("title").text for item in canal.findall("item")}
    assert {"Vulnerabilidad en APT de Debian", "Ataque a Binance roba millones"} <= titulos


def test_feed_tiene_metadatos_de_canal(cliente):
    r = cliente.get("/feed.xml")
    canal = _parsear(r).find("channel")
    assert canal.find("title").text
    assert canal.find("link").text.startswith("http")
    assert canal.find("language").text == "es"
    assert canal.find("{http://www.w3.org/2005/Atom}link").get("href").endswith("/feed.xml")


def test_feed_filtra_por_categoria(cliente):
    r = cliente.get("/feed.xml?categorias=empleo")
    canal = _parsear(r).find("channel")
    assert canal.findall("item") == []


def test_feed_escapa_contenido_no_confiable(cliente):
    r = cliente.get("/feed.xml")
    assert "<script>" not in r.text
    assert "]]>" not in r.text


def test_feed_respeta_el_limite(cliente):
    r = cliente.get("/feed.xml?limite=1")
    canal = _parsear(r).find("channel")
    assert len(canal.findall("item")) == 1


def test_feed_trae_senal_de_cobertura_propia(cliente):
    r = cliente.get("/feed.xml")
    assert "pingunews:cobertura" in r.text
    assert "pingunews:fuentes" in r.text
