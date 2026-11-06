/* Mejora progresiva: el desplegable de categorías se cierra al pulsar
       fuera o con Escape (devolviendo el foco al botón). Sin JS sigue
       funcionando como <details> nativo. */
    (function () {
      var d = document.querySelector("details.dropdown");
      if (!d) return;
      document.addEventListener("click", function (e) {
        if (d.open && !d.contains(e.target)) d.open = false;
      });
      d.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && d.open) {
          d.open = false;
          d.querySelector("summary").focus();
        }
      });
    })();
/* Mascota: reacciona al clic con una animación al azar, sigue el cursor con
       los ojos y, de vez en cuando, hace cosas por su cuenta (bostezar, mirar,
       saltar...). Las acciones automáticas solo ocurren con la pestaña y el
       pingüino visibles, se pueden pausar con el botón y no se ejecutan si el
       sistema pide "reducir movimiento". */
    (function () {
      var btn = document.getElementById("mascota");
      if (!btn) return;
      var svg = btn.querySelector(".pingu");
      var pausaBtn = document.getElementById("mascota-pausa");
      var reducir = window.matchMedia("(prefers-reduced-motion: reduce)");
      var CLIC = [["a-salto", 1150], ["a-giro", 1550], ["a-baile", 1950], ["a-saludo", 2150],
                  ["a-aleteo", 1550], ["a-sorpresa", 1550], ["a-cosquillas", 1450], ["a-corazones", 2400],
                  ["a-bostezo", 2900], ["a-mira", 2500], ["a-saltito", 1050], ["a-contoneo", 2700],
                  ["a-sacude", 1100], ["a-estira", 2300], ["a-dormita", 3400],
                  ["a-curiosa", 2400], ["a-canta", 2900], ["a-rasca", 2700]];
      var SOLO = ["a-bostezo", "a-mira", "a-saltito", "a-contoneo", "a-sacude", "a-estira",
                  "a-dormita", "a-saludo", "a-aleteo", "a-salto", "a-curiosa", "a-canta", "a-rasca"];
      var DUR = {}, todas = ["a-feliz"];
      CLIC.forEach(function (a) { DUR[a[0]] = a[1]; todas.push(a[0]); });
      var tAnim = null, tSolo = null, actual = null, ultima = "", pausado = false, visible = true;

      try { pausado = localStorage.getItem("pingunews-mascota-pausa") === "1"; } catch (e) {}

      function limpiar() { todas.forEach(function (c) { svg.classList.remove(c); }); }
      function activo() { return !pausado && !reducir.matches && visible && !document.hidden; }
      function vivo() { svg.classList.toggle("vivo", activo()); }
      function pintaPausa() {
        if (!pausaBtn) return;
        pausaBtn.setAttribute("aria-pressed", pausado ? "true" : "false");
        pausaBtn.title = pausado ? "Reanudar animaciones automáticas" : "Pausar animaciones automáticas";
      }

      function reproducir(nombre) {
        clearTimeout(tAnim);
        svg.classList.remove("hola"); limpiar();
        void svg.getBoundingClientRect();           /* reinicia la animación */
        svg.classList.add(nombre); actual = nombre; ultima = nombre;
        tAnim = setTimeout(function () { limpiar(); actual = null; programar(); }, DUR[nombre]);
      }
      function programar() {
        clearTimeout(tSolo);
        if (!activo()) return;
        tSolo = setTimeout(solo, 7000 + Math.random() * 9000);
      }
      function solo() {
        if (actual || !activo()) { programar(); return; }
        var n; do { n = SOLO[Math.floor(Math.random() * SOLO.length)]; } while (n === ultima);
        reproducir(n);
      }
      function actualiza() { vivo(); if (activo()) { if (!actual) programar(); } else clearTimeout(tSolo); }

      btn.addEventListener("click", function () {
        clearTimeout(tAnim); clearTimeout(tSolo);
        svg.classList.remove("hola"); limpiar();
        if (reducir.matches) {
          svg.classList.add("a-feliz"); actual = null;
          tAnim = setTimeout(limpiar, 2000);
          return;
        }
        var n; do { n = CLIC[Math.floor(Math.random() * CLIC.length)][0]; } while (n === ultima);
        reproducir(n);
      });

      if (pausaBtn) {
        pausaBtn.addEventListener("click", function () {
          pausado = !pausado;
          try { localStorage.setItem("pingunews-mascota-pausa", pausado ? "1" : "0"); } catch (e) {}
          pintaPausa(); actualiza();
        });
      }

      document.addEventListener("visibilitychange", actualiza);
      if (reducir.addEventListener) reducir.addEventListener("change", actualiza);
      if ("IntersectionObserver" in window) {
        new IntersectionObserver(function (es) { visible = es[0].isIntersecting; actualiza(); }).observe(btn);
      }

      /* ojos que siguen al cursor */
      if (!reducir.matches) {
        var px = 0, py = 0, raf = 0;
        var seguir = function () {
          raf = 0;
          var r = svg.getBoundingClientRect();
          var cx = r.left + r.width / 2, cy = r.top + r.height * 0.33;
          var dx = px - cx, dy = py - cy, d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260);
          svg.style.setProperty("--ox", (dx / d * 2.6 * k).toFixed(2) + "px");
          svg.style.setProperty("--oy", (dy / d * 2.2 * k).toFixed(2) + "px");
        };
        document.addEventListener("pointermove", function (e) {
          px = e.clientX; py = e.clientY;
          if (!raf) raf = requestAnimationFrame(seguir);
        }, { passive: true });
      }

      window.pinguReacciona = function (n) { if (!reducir.matches && DUR[n]) reproducir(n); };
      pintaPausa();
      setTimeout(function () { svg.classList.remove("hola"); actualiza(); }, 4200);
      vivo();
    })();
/* Botón "otra frase": pide otra al servidor sin recargar la página. */
    (function () {
      var btn = document.getElementById("frase-otra");
      if (!btn) return;
      var fig = document.querySelector(".frase");
      var txt = document.getElementById("frase-texto");
      var aut = document.getElementById("frase-autor");
      var reducir = window.matchMedia("(prefers-reduced-motion: reduce)");
      var ocupado = false;
      btn.hidden = false;

      function termina() {
        setTimeout(function () { ocupado = false; btn.classList.remove("girando"); btn.removeAttribute("aria-busy"); }, 500);
      }
      btn.addEventListener("click", function () {
        if (ocupado) return;
        ocupado = true; btn.classList.add("girando"); btn.setAttribute("aria-busy", "true");
        fetch("/frase?actual=" + encodeURIComponent(txt.textContent), {
          headers: { "Accept": "application/json" }, credentials: "same-origin", cache: "no-store"
        })
          .then(function (r) { if (!r.ok) throw new Error("http " + r.status); return r.json(); })
          .then(function (f) {
            fig.classList.add("cambiando");
            setTimeout(function () {
              txt.textContent = f.texto;
              if (f.autor) { aut.textContent = f.autor; aut.hidden = false; } else { aut.hidden = true; }
              fig.classList.remove("cambiando");
            }, reducir.matches ? 0 : 200);
            if (window.pinguReacciona) {
              var gestos = ["a-saltito", "a-curiosa", "a-saludo", "a-mira"];
              window.pinguReacciona(gestos[Math.floor(Math.random() * gestos.length)]);
            }
          })
          .catch(function () { /* se queda la frase actual */ })
          .then(termina);
      });
    })();
/* "↻ Actualizar ahora": el formulario se envía de forma normal (no es AJAX,
       la página recarga al terminar), pero mientras el servidor recopila
       -puede tardar varios segundos con tantas fuentes- se muestra una capa a
       pantalla completa con el pingüino "investigando" para que quede claro
       que la app está trabajando y no parezca que se ha quedado colgada. */
    (function () {
      var form = document.getElementById("form-actualizar");
      var overlay = document.getElementById("overlay-actualizando");
      if (!form || !overlay) return;
      var boton = form.querySelector("button[type=submit]");
      var enviando = false;

      form.addEventListener("submit", function () {
        if (enviando) return;
        enviando = true;
        if (boton) boton.disabled = true;
        overlay.hidden = false;
        try { document.querySelector("main").inert = true; } catch (e) {}
        requestAnimationFrame(function () { overlay.classList.add("visible"); });
      });

      /* Si el usuario vuelve con el botón "atrás" y el navegador restaura la
         página desde la caché (bfcache), la capa no debe quedarse pegada en
         pantalla ni el botón bloqueado. */
      window.addEventListener("pageshow", function (e) {
        if (!e.persisted) return;
        enviando = false;
        if (boton) boton.disabled = false;
        overlay.classList.remove("visible");
        overlay.hidden = true;
        try { document.querySelector("main").inert = false; } catch (e2) {}
      });
    })();
/* Las fechas de cada noticia llegan del servidor en UTC (es la zona de la
       recolección); se reescriben aquí a la hora local de quien la esté
       viendo, que puede estar en cualquier huso horario. El atributo
       datetime ya trae el ISO-8601 completo con el offset, así que no hace
       falta tocar el servidor. Sin JavaScript se queda la hora UTC original,
       que sigue siendo correcta, solo que no ajustada. */
    (function () {
      var nodos = document.querySelectorAll("time[datetime]");
      if (!nodos.length) return;
      function pad(n) { return n < 10 ? "0" + n : "" + n; }
      nodos.forEach(function (t) {
        var d = new Date(t.getAttribute("datetime"));
        if (isNaN(d.getTime())) return;
        t.textContent = pad(d.getDate()) + "/" + pad(d.getMonth() + 1) + " " + pad(d.getHours()) + ":" + pad(d.getMinutes());
      });
    })();
