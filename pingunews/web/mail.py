"""Envío de correo: verificación de registro, recuperación de contraseña y
cambio de correo.

Usa el mismo Postfix local que ya usa dockerlabs.es en este VPS (relay sin
autenticación en 127.0.0.1:25, firmado DKIM automáticamente por el milter de
OpenDKIM para el dominio del remitente — ver `/etc/opendkim/signing.table`
en el servidor). Sin dependencias nuevas: solo `smtplib` de la librería
estándar, igual que el resto de la app evita dependencias externas de más.
"""
from __future__ import annotations

import logging
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
import smtplib

logger = logging.getLogger("herramienta.web.mail")


def _config_smtp() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST", "127.0.0.1"),
        "port": int(os.environ.get("SMTP_PORT", "25")),
        "usuario": os.environ.get("SMTP_USER", ""),
        "clave": os.environ.get("SMTP_PASS", ""),
        "nombre_remitente": os.environ.get("SMTP_FROM_NAME", "PinguNews"),
        "remitente": os.environ.get("SMTP_FROM", ""),
    }


def smtp_configurado() -> bool:
    return bool(_config_smtp()["remitente"])


def _html_a_texto(html: str) -> str:
    """Alternativa en texto plano simple a partir del HTML, para el
    multipart/alternative (mejora la entregabilidad: los filtros antispam
    penalizan los correos solo-HTML)."""
    texto = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"\2 (\1)", html, flags=re.S | re.I)
    texto = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", texto, flags=re.S | re.I)
    texto = re.sub(r"<br\s*/?>", "\n", texto, flags=re.I)
    texto = re.sub(r"</(p|div|tr|h\d)>", "\n", texto, flags=re.I)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n\n", texto)
    return texto.strip()


def _enviar(destinatario: str, asunto: str, html: str) -> bool:
    cfg = _config_smtp()
    if not cfg["remitente"]:
        logger.warning("SMTP no configurado — correo no enviado a %s", destinatario)
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f'{cfg["nombre_remitente"]} <{cfg["remitente"]}>'
    msg["To"] = destinatario
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=cfg["remitente"].split("@")[-1])
    msg.attach(MIMEText(_html_a_texto(html), "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=15) as servidor:
            servidor.ehlo()
            if cfg["usuario"] and cfg["clave"]:
                servidor.starttls()
                servidor.login(cfg["usuario"], cfg["clave"])
            servidor.sendmail(cfg["remitente"], destinatario, msg.as_string())
        logger.info("Correo enviado a %s: %s", destinatario, asunto)
        return True
    except Exception:
        logger.exception("Error al enviar correo a %s", destinatario)
        return False


def _plantilla(titulo: str, saludo: str, cuerpo_html: str, nota: str = "") -> str:
    nota_html = f'<p style="color:#71717a;font-size:12px;margin:20px 0 0;">{nota}</p>' if nota else ""
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>{titulo}</title></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;padding:32px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:14px;overflow:hidden;max-width:560px;width:100%;border:1px solid #d4d4d8;">
        <tr><td style="background:#475569;padding:28px 36px;">
          <span style="color:#ffffff;font-size:22px;font-weight:700;">🐧 PinguNews</span>
        </td></tr>
        <tr><td style="padding:34px 36px;">
          <h1 style="color:#1e293b;font-size:19px;margin:0 0 14px;">{saludo}</h1>
          {cuerpo_html}
          {nota_html}
        </td></tr>
        <tr><td style="background:#f4f4f5;padding:16px 36px;border-top:1px solid #d4d4d8;">
          <p style="color:#a1a1aa;font-size:12px;margin:0;">PinguNews &middot; pingunews.dockerlabs.es</p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _boton(url: str, texto: str) -> str:
    return (
        '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" style="padding:6px 0 26px;">'
        f'<a href="{url}" style="display:inline-block;background:#475569;color:#ffffff;text-decoration:none;'
        'padding:14px 32px;border-radius:10px;font-size:15px;font-weight:600;">'
        f"{texto}</a></td></tr></table>"
        '<p style="color:#71717a;font-size:12px;line-height:1.5;margin:0 0 4px;">'
        "Si el botón no funciona, copia y pega este enlace en tu navegador:</p>"
        f'<p style="color:#475569;font-size:12px;word-break:break-all;margin:0 0 20px;">{url}</p>'
    )


def enviar_verificacion_registro(destinatario: str, nombre_usuario: str, token: str, base_url: str) -> bool:
    url = f"{base_url}/verificar-correo?token={token}"
    cuerpo = (
        f'<p style="color:#52525b;font-size:15px;line-height:1.6;margin:0 0 20px;">'
        f"Gracias por registrarte en PinguNews. Para activar tu cuenta, confirma tu correo:</p>"
        + _boton(url, "Verificar mi cuenta")
    )
    html = _plantilla(
        "Verifica tu cuenta en PinguNews", f"¡Hola, {nombre_usuario}!", cuerpo,
        nota="Este enlace caduca en 24 horas. Si no has solicitado esta cuenta, puedes ignorar este correo.",
    )
    return _enviar(destinatario, "Verifica tu cuenta en PinguNews", html)


def enviar_reset_password(destinatario: str, nombre_usuario: str, token: str, base_url: str) -> bool:
    url = f"{base_url}/restablecer-password?token={token}"
    cuerpo = (
        f'<p style="color:#52525b;font-size:15px;line-height:1.6;margin:0 0 20px;">'
        "Hemos recibido una solicitud para restablecer la contraseña de tu cuenta. "
        "Si has sido tú, crea una nueva contraseña aquí:</p>"
        + _boton(url, "Restablecer contraseña")
    )
    html = _plantilla(
        "Recupera tu contraseña en PinguNews", f"Hola, {nombre_usuario}", cuerpo,
        nota="Este enlace caduca en 1 hora. Si no has sido tú, ignora este correo: tu contraseña no cambiará.",
    )
    return _enviar(destinatario, "Recupera tu contraseña en PinguNews", html)


def enviar_confirmacion_cambio_email(destinatario_nuevo: str, nombre_usuario: str, token: str, base_url: str) -> bool:
    url = f"{base_url}/confirmar-cambio-correo?token={token}"
    cuerpo = (
        f'<p style="color:#52525b;font-size:15px;line-height:1.6;margin:0 0 20px;">'
        f"Hola, <strong>{nombre_usuario}</strong>. Hemos recibido una solicitud para usar esta dirección "
        "como el nuevo correo de tu cuenta en PinguNews. Confírmalo aquí:</p>"
        + _boton(url, "Confirmar nuevo correo")
    )
    html = _plantilla(
        "Confirma tu nuevo correo en PinguNews", "Confirma tu nuevo correo", cuerpo,
        nota="Este enlace caduca en 1 hora. Si no has solicitado este cambio, ignora este correo.",
    )
    return _enviar(destinatario_nuevo, "Confirma tu nuevo correo en PinguNews", html)


def enviar_aviso_cambio_email(destinatario_antiguo: str, nombre_usuario: str, email_nuevo: str) -> bool:
    cuerpo = (
        f'<p style="color:#52525b;font-size:15px;line-height:1.6;margin:0 0 16px;">'
        f"Hola, <strong>{nombre_usuario}</strong>. Se ha solicitado cambiar el correo de tu cuenta en PinguNews "
        f"a <strong>{email_nuevo}</strong>, confirmando tu contraseña actual.</p>"
        '<div style="background:#fef3c7;border-left:3px solid #d97706;border-radius:8px;padding:14px 16px;margin:0 0 18px;">'
        '<p style="color:#92400e;font-size:13px;line-height:1.6;margin:0;">'
        "<strong>¿No has sido tú?</strong> El cambio no se aplicará hasta que se confirme desde la dirección nueva. "
        "Si no reconoces esta solicitud, cambia tu contraseña cuanto antes desde tu perfil.</p></div>"
    )
    html = _plantilla("Aviso de seguridad — PinguNews", "Solicitud de cambio de correo", cuerpo)
    return _enviar(destinatario_antiguo, "Se ha solicitado un cambio de correo en tu cuenta de PinguNews", html)
