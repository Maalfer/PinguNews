from pingunews.text import coincide_palabra_completa, normalize, strip_html


def test_normalize_quita_acentos_y_pasa_a_minusculas():
    assert normalize("Ciberseguridad ÁÉÍ") == "ciberseguridad aei"


def test_palabra_completa_no_es_subcadena():
    assert not coincide_palabra_completa("diferentes", "ere")
    assert coincide_palabra_completa("nuevo ere en la empresa", "ere")


def test_strip_html():
    assert strip_html("<p>Hola   <b>mundo</b></p>") == "Hola mundo"
