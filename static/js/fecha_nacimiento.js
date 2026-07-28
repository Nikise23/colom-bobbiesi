(function (global) {
  function soloDigitos(valor, maxLen) {
    return String(valor || "").replace(/\D/g, "").slice(0, maxLen);
  }

  function anioNacimientoValido(anio) {
    const actual = new Date().getFullYear();
    return anio >= 1900 && anio <= actual;
  }

  function formatearFechaInput(valor) {
    // Si viene ISO (yyyy-mm-dd), convertir a dd/mm/aaaa
    const texto = String(valor || "").trim();
    const iso = texto.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) {
      return `${iso[3]}/${iso[2]}/${iso[1]}`;
    }

    const digits = soloDigitos(texto, 8);
    if (digits.length <= 2) return digits;
    if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
    return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
  }

  function parseFechaNacimiento(valor) {
    if (!valor) return null;
    const normalizado = formatearFechaInput(valor);
    const partes = String(normalizado).trim().split("/");
    if (partes.length !== 3) return null;
    const [diaTxt, mesTxt, anioTxt] = partes;
    if (anioTxt.length !== 4) return null;
    const dia = Number(diaTxt);
    const mes = Number(mesTxt);
    const anio = Number(anioTxt);
    if (!dia || !mes || !anio || !anioNacimientoValido(anio)) return null;
    const fecha = new Date(anio, mes - 1, dia);
    if (
      fecha.getFullYear() !== anio ||
      fecha.getMonth() !== mes - 1 ||
      fecha.getDate() !== dia
    ) {
      return null;
    }
    return fecha;
  }

  function calcularEdad(fechaNacimiento) {
    const fechaNac = parseFechaNacimiento(fechaNacimiento);
    if (!fechaNac) return "";

    const hoy = new Date();
    let edad = hoy.getFullYear() - fechaNac.getFullYear();
    const mesActual = hoy.getMonth();
    const mesNacimiento = fechaNac.getMonth();

    if (
      mesActual < mesNacimiento ||
      (mesActual === mesNacimiento && hoy.getDate() < fechaNac.getDate())
    ) {
      edad--;
    }

    return edad >= 0 ? edad : "";
  }

  function actualizarEdadCampo(fechaValor, edadId) {
    if (!edadId) return;
    const edadEl = document.getElementById(edadId);
    if (!edadEl) return;
    const edad = calcularEdad(fechaValor);
    const texto = edad !== "" ? `${edad} años` : "";
    if (edadEl.tagName === "INPUT" || edadEl.tagName === "TEXTAREA") {
      edadEl.value = texto || "";
      if (!texto) {
        edadEl.placeholder = "Se calcula al completar la fecha";
      }
    } else {
      edadEl.textContent = texto
        ? `Edad: ${texto}`
        : "La edad se calcula al completar la fecha";
      edadEl.className = texto ? "form-text text-success" : "form-text text-muted";
    }
  }

  function aplicarMascaraFecha(input) {
    const anterior = input.value;
    const formateado = formatearFechaInput(anterior);
    if (formateado !== anterior) {
      input.value = formateado;
    } else {
      input.value = formateado;
    }
  }

  function bindFechaNacimientoInput(inputId, edadId) {
    const input = document.getElementById(inputId);
    if (!input) return;
    if (input.dataset.fechaMaskBound === "1") {
      // Reaplicar edad por si el valor ya estaba cargado
      aplicarMascaraFecha(input);
      actualizarEdadCampo(input.value, edadId);
      return;
    }
    input.dataset.fechaMaskBound = "1";
    input.setAttribute("inputmode", "numeric");
    // Es un formulario administrativo, no conviene que el navegador
    // autocomplemente con la fecha de nacimiento del perfil del usuario.
    input.setAttribute("autocomplete", "off");
    input.setAttribute("maxlength", "10");
    input.setAttribute("placeholder", input.getAttribute("placeholder") || "dd/mm/aaaa");

    function onChange() {
      aplicarMascaraFecha(input);
      actualizarEdadCampo(input.value, edadId);
      if (input.value.length === 10 && !parseFechaNacimiento(input.value)) {
        input.setCustomValidity("La fecha debe ser válida y tener formato dd/mm/aaaa");
      } else {
        input.setCustomValidity("");
      }
    }

    input.addEventListener("input", onChange);
    input.addEventListener("keyup", onChange);
    input.addEventListener("change", onChange);
    input.addEventListener("blur", onChange);
    input.addEventListener("paste", function () {
      setTimeout(onChange, 0);
    });

    // Si ya hay valor al bind (edición), formatear y mostrar edad
    onChange();
  }

  function bindDniInput(inputId, mensajeId) {
    const input = document.getElementById(inputId);
    if (!input || input.dataset.dniBound === "1") return;
    input.dataset.dniBound = "1";
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("maxlength", "8");
    input.setAttribute("autocomplete", "off");

    function syncMensaje() {
      const mensajeEl = mensajeId ? document.getElementById(mensajeId) : null;
      if (!mensajeEl) return;
      const valor = input.value;
      if (!valor) {
        mensajeEl.textContent = "7 u 8 dígitos (sin puntos ni espacios)";
        mensajeEl.className = "form-text text-muted";
        return;
      }
      if (!/^\d+$/.test(valor)) {
        mensajeEl.textContent = "Solo números";
        mensajeEl.className = "form-text text-danger";
        return;
      }
      if (valor.length > 8) {
        mensajeEl.textContent = "Máximo 8 dígitos";
        mensajeEl.className = "form-text text-danger";
        return;
      }
      if (valor.length < 7) {
        mensajeEl.textContent = `Faltan ${7 - valor.length} dígito(s) (mínimo 7)`;
        mensajeEl.className = "form-text text-warning";
        return;
      }
      mensajeEl.textContent = "DNI válido";
      mensajeEl.className = "form-text text-success";
    }

    input.addEventListener("input", function () {
      input.value = soloDigitos(input.value, 8);
      syncMensaje();
    });
    input.addEventListener("blur", syncMensaje);
    input.addEventListener("paste", function () {
      setTimeout(function () {
        input.value = soloDigitos(input.value, 8);
        syncMensaje();
      }, 0);
    });
    syncMensaje();
  }

  function validarDni(valor) {
    const dni = soloDigitos(valor, 8);
    return /^\d{7,8}$/.test(dni) ? dni : null;
  }

  global.formatearFechaInput = formatearFechaInput;
  global.parseFechaNacimiento = parseFechaNacimiento;
  global.calcularEdad = calcularEdad;
  global.actualizarEdadCampo = actualizarEdadCampo;
  global.bindFechaNacimientoInput = bindFechaNacimientoInput;
  global.bindDniInput = bindDniInput;
  global.validarDni = validarDni;
})(window);
