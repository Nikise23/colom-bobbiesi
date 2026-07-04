(function (global) {
  function formatearFechaInput(valor) {
    const digits = String(valor || "").replace(/\D/g, "").slice(0, 8);
    if (digits.length <= 2) return digits;
    if (digits.length <= 4) return `${digits.slice(0, 2)}/${digits.slice(2)}`;
    return `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
  }

  function parseFechaNacimiento(valor) {
    if (!valor) return null;
    const partes = String(valor).trim().split("/");
    if (partes.length !== 3) return null;
    const [dia, mes, anio] = partes.map(Number);
    if (!dia || !mes || !anio || partes[2].length !== 4) return null;
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

  function aplicarMascaraFecha(input) {
    input.value = formatearFechaInput(input.value);
  }

  function bindFechaNacimientoInput(inputId, edadId) {
    const input = document.getElementById(inputId);
    if (!input || input.dataset.fechaMaskBound === "1") return;
    input.dataset.fechaMaskBound = "1";
    input.setAttribute("inputmode", "numeric");
    input.setAttribute("autocomplete", "bday");

    input.addEventListener("input", function () {
      aplicarMascaraFecha(this);
      if (edadId) {
        const edadEl = document.getElementById(edadId);
        if (edadEl) {
          const edad = calcularEdad(this.value);
          edadEl.value = edad !== "" ? edad + " años" : "";
        }
      }
    });

    input.addEventListener("blur", function () {
      aplicarMascaraFecha(this);
    });
  }

  global.formatearFechaInput = formatearFechaInput;
  global.parseFechaNacimiento = parseFechaNacimiento;
  global.calcularEdad = calcularEdad;
  global.bindFechaNacimientoInput = bindFechaNacimientoInput;
})(window);
