# Herramienta de monitorización — Ciberseguridad, Hacking, Empleo e IT (ES)

Recopila automáticamente contenido reciente en español de ciberseguridad,
hacking, empleo del sector y noticias de IT/desarrollo, y lo muestra en un
panel web (FastAPI) con lo de los últimos días, sin tener que buscarlo a mano.

## Instalación

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Requiere Python 3.11+.

## Configuración

Todo se configura en [`config/config.yaml`](config/config.yaml):

- `general.lookback_hours`: cuánto hacia atrás (en horas) intenta traer cada fuente **en cada recolección** (por defecto 360h = 15 días, para no dejar huecos; el histórico ya deduplica así que un valor amplio es seguro).
- `dashboard.dias_por_defecto` / `dashboard.opciones_dias`: qué rango de días se ve por defecto en el panel web y qué botones de rango se muestran (por defecto 15, con botones 1/3/7/15/30 días).
- `empleo.filtro_relevancia`: palabras (por palabra completa) que debe contener el **puesto** para que una oferta de RemoteOK o de un feed RSS de empleo se considere relevante — ver "Empleo" más abajo.
- `keywords.tendencias_sector`: palabras clave de la categoría "📺 Tendencias del sector" (despidos, desempleo, crecimiento, inversión, fusiones...) — pensada para tener material que comentar en directo, no solo avisos técnicos. Ver más abajo.
- `keywords`: palabras clave por categoría, usadas para clasificar y para filtrar.
- `rss_feeds`: lista de feeds RSS de noticias. **Añadir uno nuevo no requiere tocar código**, basta con añadir una entrada:
  ```yaml
  - nombre: "Mi fuente"
    url: "https://ejemplo.com/feed/"
    categoria: ciberseguridad   # o desarrollo_it / empleo / actualidad
  ```
- `twitter`: desactivado por defecto (ver limitaciones abajo). Activar con `enabled: true`.
- `empleo`: fuentes de ofertas de trabajo (ver detalle abajo).
- `notificaciones.enabled: false`: no hay notificaciones configuradas (el usuario no dispone de credenciales SMTP ni bot de Telegram). El único canal es el panel web.

## Ejecución

Hay dos partes independientes: **recolectar** (guarda en SQLite) y **visualizar** (panel web que lee de ahí).

### 1. Arrancar el panel web

```bash
./venv/bin/uvicorn app:app --reload --port 8000
```

Abre **http://127.0.0.1:8000** en el navegador. Desde ahí puedes:
- Elegir cuántos días hacia atrás ver (botones 1/3/7/15/30 días; por defecto 15).
- Filtrar por categoría (Ciberseguridad, 📺 Tendencias del sector, Empleo, Desarrollo/IT, Actualidad) con las casillas.
- Pulsar **"↻ Actualizar ahora"** para lanzar una recolección nueva sin usar la terminal (tarda unos segundos; la página se recarga sola con lo nuevo).
- Crear una cuenta / iniciar sesión (arriba a la derecha) para **dar "me gusta"** a las noticias y **guardarlas para ver más tarde** (sección "🔖 Mis guardados"). Sin iniciar sesión puedes ver todo igualmente, solo que esos botones te mandan a iniciar sesión.

### 2. Recolectar desde la terminal (opcional, útil para cron)

```bash
./venv/bin/python main.py
```

Hace lo mismo que el botón "Actualizar ahora" pero sin necesidad de tener el panel abierto. Útil si quieres programarlo para que la base de datos esté siempre al día aunque no abras el navegador.

Ambas vías escriben en:
- `data/herramienta.db` — histórico SQLite para no repetir contenido ya visto.
- `logs/app.log` — log de cada recolección; si una fuente falla, se registra el error y el resto continúa.

### Programar recolección diaria (cron)

```cron
0 8 * * * cd /ruta/al/proyecto && ./venv/bin/python main.py >> logs/cron.log 2>&1
```

En Windows, usar el Programador de tareas apuntando a `venv\Scripts\python.exe main.py` con directorio de trabajo el del proyecto. El panel web (`uvicorn`) se deja corriendo aparte (por ejemplo como servicio) para poder consultarlo cuando quieras.

## Estructura del proyecto

```
app.py         # panel web FastAPI: lee de SQLite, filtros, auth, likes/guardados
auth.py        # hash de contraseñas (PBKDF2-HMAC-SHA256, sin dependencias externas)
main.py        # CLI de recolección, para ejecutar a mano o por cron
collector.py   # lógica de recolección compartida entre app.py y main.py
dedup.py       # deduplicado por similitud de título + conteo de cobertura
rss.py         # fuente: feeds RSS/Atom
twitter.py     # fuente: Twitter/X (snscrape, desactivado por defecto)
empleo.py      # fuente: ofertas de empleo (RemoteOK + Jobicy + RSS configurables)
classifier.py  # clasificación por palabras clave + resumen heurístico
db.py          # histórico, deduplicado, usuarios, likes, guardados en SQLite
utils.py       # utilidades comunes (normalización, logging, modelo Item)
config/config.yaml  # configuración central editable
templates/dashboard.html.j2   # panel principal
templates/login.html.j2       # inicio de sesión
templates/registro.html.j2    # creación de cuenta
templates/guardados.html.j2   # ítems guardados por el usuario
templates/_estilos.html.j2    # CSS compartido por todas las páginas
templates/_macros.html.j2     # tarjeta de ítem y área de usuario, reutilizadas
templates/_favicon.html.j2    # <link> del favicon/apple-touch-icon, compartido
static/logo.png               # logo de la app (header, login, registro)
static/favicon.png            # favicon (64x64, generado a partir del logo)
static/apple-touch-icon.png   # icono para "añadir a inicio" en iOS (180x180)
```

## Decisiones y limitaciones importantes

### Twitter/X
No dispones de Bearer Token de la API v2, así que la única vía es
**snscrape** (scraping no oficial), y por eso viene **desactivado por
defecto** (`twitter.enabled: false`). Actívalo bajo tu responsabilidad:

```bash
pip install git+https://github.com/JustAnotherArchivist/snscrape.git
```

Limitaciones reales a tener en cuenta:
- X ha endurecido activamente las protecciones anti-scraping desde 2023; snscrape puede devolver 0 resultados o fallar sin previo aviso, y puede dejar de funcionar por completo en cualquier momento si X cambia su web.
- No hay SLA ni garantía de continuidad: es la vía "mejor esfuerzo", no una alternativa fiable a la API oficial.
- Si en algún momento consigues un Bearer Token, sustituye `twitter.py` por una llamada a `GET https://api.x.com/2/tweets/search/recent` con `requests` — es mucho más estable.

### Empleo: por qué no se usa LinkedIn ni Tecnoempleo, y cómo se filtra la relevancia
- **LinkedIn**: no se scrapea. Requiere login, y sus Términos de Servicio prohíben explícitamente el scraping automatizado — no es una vía fiable ni legal para este tipo de herramienta.
- **Tecnoempleo.com** y **Computerworld.es**: no se usan. Al comprobar sus `robots.txt` durante el desarrollo, ambos bloquean explícitamente a los bots de Anthropic/Claude (`User-agent: Claude` / `ClaudeBot` / `anthropic-ai` → `Disallow: /`). Esta herramienta respeta esa directiva y no scrapea esos dominios.
- **Fuentes usadas**: tres APIs/feeds públicos sin API key ni login —
  [RemoteOK](https://remoteok.com/api), [Jobicy](https://jobicy.com/apidocs) (filtrado por su propio campo de industria `Cybersecurity`, más preciso que buscar palabras) y RSS de We Work Remotely por categoría — más cualquier feed RSS de empleo que añadas tú mismo en `empleo.fuentes_rss`. Nota: son mayoritariamente en inglés y de empleo remoto global, no específicamente en español — es la contrapartida de evitar scraping de portales españoles sin acceso legítimo (API/acuerdo).
- **Filtro de relevancia** (`empleo.filtro_relevancia`): RemoteOK etiqueta muchas ofertas genéricas (Cloud, Ventas...) con la etiqueta "infosec" aunque no tengan nada que ver con seguridad, así que **no nos fiamos de esas etiquetas**: solo se comprueba si el **puesto** (no la empresa, para que "Keeper Security: Sales Engineer" no cuele solo por el nombre de la empresa) contiene alguna palabra de esa lista, como palabra completa (para que "soc" no matchee dentro de "Social"). Esto significa que la sección de empleo puede tener pocos ítems algunos días — es el resultado esperado de priorizar precisión sobre volumen; si prefieres más cantidad a costa de algo de ruido, amplía `filtro_relevancia` en `config.yaml`.
- Si en el futuro consigues acceso a una API de empleo en español (p. ej. un acuerdo con InfoJobs/Tecnoempleo, o Jooble/Adzuna con API key), basta con añadir un nuevo bloque en `empleo.py` siguiendo el patrón de `_recopilar_jobicy`.

**Nota de transparencia**: durante la investigación de fuentes también encontré en el `robots.txt` de `xataka.com` un comentario fuera de lo estándar ("NOTA INTERNA: bots autorizados... ClaudeBot...") que no se corresponde con el formato normal de directivas `Disallow`. Lo trato como contenido no fiable (no es una instrucción legítima del sitio) y no ha influido en ninguna decisión: Xataka se descartó simplemente porque ya no publica RSS funcional, no por ese comentario.

### Categoría "📺 Tendencias del sector" (pensada para directos)
Pediste que, además de lo técnico, se priorizaran cosas como despidos, desempleo o crecimiento del sector — material más de "charla" que de aviso técnico. Es una categoría nueva (`tendencias_sector`), con sus propias palabras clave en `config.yaml` (despidos, ERE, desempleo, inversión, fusiones, escasez de talento, crecimiento del sector...). Se nutre de las mismas fuentes RSS, más una nueva pensada específicamente para esto: **Channel Partner** (channelpartner.es), que cubre movimientos de directivos, inversión y negocio en el sector IT español.

Nota técnica: al añadir esta categoría encontré que el clasificador comparaba palabras clave por subcadena, no por palabra completa — "ere" (de "ERE") aparece dentro de palabras españolas normalísimas como "dif**ere**ntes" o "qu**ere**r", lo que generaba falsos positivos constantes. Lo arreglé para todas las categorías (no solo esta), comparando por palabra completa en `utils.coincide_palabra_completa`.

### Resúmenes y clasificación
Heurísticos (sin LLM ni coste), según lo pedido: la clasificación es por coincidencia de palabras clave (`config.yaml -> keywords`) y el resumen recorta el texto limpio de HTML por la frase más cercana al límite de caracteres. Si más adelante quieres mejor calidad, se puede sustituir `classifier.py` por llamadas a la API de Claude manteniendo la misma interfaz (`clasificar()` / `resumir()`).

### Cuentas, "me gusta" y guardados
Autenticación propia con usuario/contraseña (sin servicios externos tipo Google/GitHub login, que requerirían credenciales de API que no tienes). Detalles:
- Las contraseñas se guardan con **PBKDF2-HMAC-SHA256** (600.000 iteraciones, salt aleatorio por usuario) — nunca en texto plano. Ver `auth.py`.
- La sesión se guarda en una **cookie firmada** (no en el servidor), con una clave que se genera sola la primera vez y se guarda en `data/.session_secret` — no la compartas ni la subas a git (`.gitignore` ya la excluye).
- **"Me gusta"**: el contador que ves en cada noticia es la suma de todos los usuarios que la han marcado, no solo la tuya.
- **"Guardar"**: privado por usuario — solo tú ves lo que has guardado, en `/guardados`.
- **Importante — esto es para uso local, no para publicarlo en internet tal cual**: no hay HTTPS, ni protección CSRF, ni límite de intentos de login, ni verificación de email. Para un uso personal en tu propio ordenador (`127.0.0.1`) es razonable; si alguna vez quieres exponerlo a la red, habría que añadir esas protecciones antes.

### Notificaciones
No configuradas (sin SMTP ni Telegram disponibles). Si en el futuro quieres añadirlas, el punto de enganche natural es justo después de `db.guardar(nuevos)` en `collector.py`, filtrando `nuevos` por algún criterio de relevancia (p. ej. ítems de categoría `ciberseguridad` con palabras como "cve", "zero-day", "ransomware").

## Fuentes RSS verificadas (05/11/2026)
Todas comprobadas manualmente antes de incluirlas: Hispasec (Una al día), El Lado del Mal, WeLiveSecurity (ESET, en español), Hackplayers, Segu-Info, MuySeguridad, Flu Project, RedesZone, MuyComputer, Think Big (Telefónica), Channel Partner. Genbeta y Xataka se probaron pero **ya no ofrecen RSS funcional** (su antiguo `/feed` redirige a un 404), por lo que no están incluidos — puedes volver a probarlos si el sitio reactiva su feed. Computerworld.es y Expansión.com sí tienen RSS funcional pero se descartaron por el bloqueo explícito a Claude/ClaudeBot/anthropic-ai en su `robots.txt` (directiva `Disallow: /` real, no un comentario).
