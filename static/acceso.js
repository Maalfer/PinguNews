/* Páginas de acceso: los ojos del pingüino siguen al cursor, se tapa los ojos
     al escribir la contraseña (y asoma si la muestras) y botón de ver/ocultar
     contraseña. Sin JavaScript el formulario funciona igual. */
  (function () {
    var svg = document.querySelector(".auth-pingu .pingu");
    var reducir = window.matchMedia("(prefers-reduced-motion: reduce)");

    document.querySelectorAll(".btn-ojo").forEach(function (b) {
      var inp = document.getElementById(b.getAttribute("data-for"));
      if (!inp) return;
      b.hidden = false;
      b.addEventListener("click", function () {
        var ver = inp.type === "password";
        inp.type = ver ? "text" : "password";
        b.setAttribute("aria-pressed", ver ? "true" : "false");
        inp.focus();
      });
    });

    function actualiza() {
      if (!svg) return;
      var a = document.activeElement;
      svg.classList.toggle("tapa", !!(a && a.hasAttribute("data-pw") && a.type === "password"));
    }
    document.addEventListener("focusin", actualiza);
    document.addEventListener("focusout", function () { setTimeout(actualiza, 0); });

    if (svg && !reducir.matches) {
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
  })();
