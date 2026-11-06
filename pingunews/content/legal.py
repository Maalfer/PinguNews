"""Datos del titular que aparecen en las páginas legales (aviso legal,
privacidad y cookies) y en el pie de página.

EDITA ESTE FICHERO para completar tu identidad y un medio de contacto.
Tras cambiarlo, reinicia el servicio:  systemctl restart pingunews
"""

LEGAL = {
    # Nombre o alias del titular/responsable del tratamiento.
    "titular": "Maalfer",
    # Dominio del sitio.
    "dominio": "pingunews.dockerlabs.es",
    # Repositorio público del código (enlace del pie de página).
    "repo": "https://github.com/Maalfer/PinguNews",
    # Correo de contacto para ejercer derechos RGPD y comunicaciones legales.
    # Si lo dejas vacío, las páginas ofrecen las incidencias públicas de GitHub
    # (menos recomendable: son públicas). Ejemplo: "contacto@tudominio.es"
    "email": "",
    # Fecha de la última revisión de los textos legales.
    "actualizado": "5 de noviembre de 2026",
}
