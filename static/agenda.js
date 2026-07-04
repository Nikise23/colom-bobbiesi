document.addEventListener("DOMContentLoaded", () => {
  const medicoSelect = document.getElementById("medico");
  const agendaDiv = document.getElementById("agenda-contenido");
  let datosAgenda = {};

  fetch("/api/agenda")
    .then(r => r.json())
    .then(data => {
      datosAgenda = data;
      Object.keys(data).forEach(nombre => {
        const opt = document.createElement("option");
        opt.textContent = nombre;
        medicoSelect.appendChild(opt);
      });
      mostrarAgenda(medicoSelect.value);
    });

  medicoSelect.addEventListener("change", () => {
    mostrarAgenda(medicoSelect.value);
  });

  function mostrarAgenda(medico) {
    agendaDiv.innerHTML = "";
    const dias = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

    dias.forEach(dia => {
      const horarios = datosAgenda[medico][dia] || [];

      const cont = document.createElement("div");
      cont.className = "dia";
      cont.innerHTML = `<h3>${dia}</h3>
        <input type="text" placeholder="Ej: 10:00, 11:30" id="input-${dia}" value="${horarios.join(', ')}" style="width: 60%;">
        <button onclick="guardar('${medico}', '${dia}')">Guardar</button>`;

      agendaDiv.appendChild(cont);
    });
  }

  window.guardar = (medico, dia) => {
    const input = document.getElementById("input-" + dia).value;
    const horarios = input.split(",").map(h => h.trim()).filter(h => h);

    fetch(`/api/agenda/${encodeURIComponent(medico)}/${dia}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(horarios)
    })
    .then(r => r.json())
    .then(res => alert(res.mensaje || res.error));
  };
});
