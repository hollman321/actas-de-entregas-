// Data Structure and State Management for Actas
const defaultData = {
  fecha: "5/05/2026",
  sede: "Cali Principal",
  tipoActa: "Entrega",
  glpi: "43560",
  proceso: "progreser2",
  nombre: "Nicoll Asblhey Martinez Caicedo",
  cedula: "1085313154",

  // Usuarios y accesos
  tipoRed: "SI",
  tipoCorreo: "N/A",
  windows: "Nmartinez",
  cuentaCorreo: "N/A",
  helpdesk: "N/A",
  aio: "NO",
  impresora: "N/A",
  controlAcceso: "SI",
  recursoCompartido: "\\\\192.169.149.248\\progreserjuridico2.0\\ejecutivo",
  licenciaOffice: "asesorop.progreserjuridico2.8@synerjoy.com",
  extension: "N/A",
  perfilNavegacion: "Fw_Banco1",
  powerbi: "N/A",
  vpn: "N/A",

  // Desktop / Portatil
  desktop: "SI",
  portatil: "N/A",
  equipoModelo: "HP ProDesk 400 G5 SFF",
  equipoSerial: "MXL909338K",
  equipoSerialDevuelto: "",
  procesador: "Intel(R) Core(TM) i7-8700 CPU @ 3.20GHz",
  ip: "192,169,149,76",
  ram: "8  gb",
  disco: "1Tr",
  so: "windows 11",
  placaInv: "587",

  // Perifericos Adicionales
  diadema: "SI",
  perifCpu: "N.A",
  teclado: "SI",
  movil: "N.A",
  mouse: "SI",
  sim: "N.A",
  otro: "N.A",
  otroCual: "",
  perifMarca: "jabra",
  perifPlaca: "89",
  perifSerial: "00110413217",
  perifSerialDev: "",

  // Monitor
  monitor: "SI",
  monitorMarca: "hp v190",
  monitorPlaca: "no tiene",
  monitorSerial: "1cr8371361",

  // Observaciones
  observaciones: "",

  // Firmas y Responsables
  entregaNombre: "hollman hoyos",
  entregaCargo: "aprendiz",
  revisoNombre: "Carlos A. Sepulveda",
  revisoCargo: "Analista Procesos",
  aproboNombre: "Jaime Chicaiza",
  aproboCargo: "Director Tecnologia",
  recibeNombre: "Nicoll Asblhey Martinez Caicedo",
  recibeCargo: "Asesor de Operacones"
};

// Field Mapping Dictionary (Form Field ID <-> Data Key <-> Doc Element ID)
const fieldMap = [
  { formId: "form-fecha", key: "fecha", docId: "doc-fecha" },
  { formId: "form-sede", key: "sede", docId: "doc-sede" },
  { formId: "form-glpi", key: "glpi", docId: "doc-glpi" },
  { formId: "form-proceso", key: "proceso", docId: "doc-proceso" },
  { formId: "form-nombre", key: "nombre", docId: "doc-nombre" },
  { formId: "form-cedula", key: "cedula", docId: "doc-cedula" },
  { formId: "form-tipo-red", key: "tipoRed", docId: "doc-tipo-red" },
  { formId: "form-tipo-correo", key: "tipoCorreo", docId: "doc-tipo-correo" },
  { formId: "form-windows", key: "windows", docId: "doc-windows" },
  { formId: "form-cuenta-correo", key: "cuentaCorreo", docId: "doc-cuenta-correo" },
  { formId: "form-helpdesk", key: "helpdesk", docId: "doc-helpdesk" },
  { formId: "form-aio", key: "aio", docId: "doc-aio" },
  { formId: "form-impresora", key: "impresora", docId: "doc-impresora" },
  { formId: "form-control-acceso", key: "controlAcceso", docId: "doc-control-acceso" },
  { formId: "form-recurso-compartido", key: "recursoCompartido", docId: "doc-recurso-compartido" },
  { formId: "form-licencia-office", key: "licenciaOffice", docId: "doc-licencia-office" },
  { formId: "form-extension", key: "extension", docId: "doc-extension" },
  { formId: "form-perfil-navegacion", key: "perfilNavegacion", docId: "doc-perfil-navegacion" },
  { formId: "form-powerbi", key: "powerbi", docId: "doc-powerbi" },
  { formId: "form-vpn", key: "vpn", docId: "doc-vpn" },
  { formId: "form-desktop", key: "desktop", docId: "doc-desktop" },
  { formId: "form-portatil", key: "portatil", docId: "doc-portatil" },
  { formId: "form-equipo-modelo", key: "equipoModelo", docId: "doc-equipo-modelo" },
  { formId: "form-equipo-serial", key: "equipoSerial", docId: "doc-equipo-serial" },
  { formId: "form-equipo-serial-devuelto", key: "equipoSerialDevuelto", docId: "doc-equipo-serial-devuelto" },
  { formId: "form-procesador", key: "procesador", docId: "doc-procesador" },
  { formId: "form-ip", key: "ip", docId: "doc-ip" },
  { formId: "form-ram", key: "ram", docId: "doc-ram" },
  { formId: "form-disco", key: "disco", docId: "doc-disco" },
  { formId: "form-so", key: "so", docId: "doc-so" },
  { formId: "form-placa-inv", key: "placaInv", docId: "doc-placa-inv" },
  { formId: "form-diadema", key: "diadema", docId: "doc-diadema" },
  { formId: "form-perif-cpu", key: "perifCpu", docId: "doc-perif-cpu" },
  { formId: "form-teclado", key: "teclado", docId: "doc-teclado" },
  { formId: "form-movil", key: "movil", docId: "doc-movil" },
  { formId: "form-mouse", key: "mouse", docId: "doc-mouse" },
  { formId: "form-sim", key: "sim", docId: "doc-sim" },
  { formId: "form-otro", key: "otro", docId: "doc-otro" },
  { formId: "form-otro-cual", key: "otroCual", docId: "doc-otro-cual" },
  { formId: "form-perif-marca", key: "perifMarca", docId: "doc-perif-marca" },
  { formId: "form-perif-placa", key: "perifPlaca", docId: "doc-perif-placa" },
  { formId: "form-perif-serial", key: "perifSerial", docId: "doc-perif-serial" },
  { formId: "form-perif-serial-dev", key: "perifSerialDev", docId: "doc-perif-serial-dev" },
  { formId: "form-monitor", key: "monitor", docId: "doc-monitor" },
  { formId: "form-monitor-marca", key: "monitorMarca", docId: "doc-monitor-marca" },
  { formId: "form-monitor-placa", key: "monitorPlaca", docId: "doc-monitor-placa" },
  { formId: "form-monitor-serial", key: "monitorSerial", docId: "doc-monitor-serial" },
  { formId: "form-observaciones", key: "observaciones", docId: "doc-observaciones" },
  { formId: "form-entrega-nombre", key: "entregaNombre", docId: "doc-entrega-nombre" },
  { formId: "form-entrega-cargo", key: "entregaCargo", docId: "doc-entrega-cargo" },
  { formId: "form-reviso-nombre", key: "revisoNombre", docId: "doc-reviso-nombre" },
  { formId: "form-reviso-cargo", key: "revisoCargo", docId: "doc-reviso-cargo" },
  { formId: "form-aprobo-nombre", key: "aproboNombre", docId: "doc-aprobo-nombre" },
  { formId: "form-aprobo-cargo", key: "aproboCargo", docId: "doc-aprobo-cargo" },
  { formId: "form-recibe-nombre", key: "recibeNombre", docId: "doc-recibe-nombre" },
  { formId: "form-recibe-cargo", key: "recibeCargo", docId: "doc-recibe-cargo" }
];

let currentData = { ...defaultData };

// Initialize App
document.addEventListener("DOMContentLoaded", () => {
  // Try loading saved data from localStorage, or load default
  const saved = localStorage.getItem("synerjoy_acta_data");
  if (saved) {
    try {
      currentData = JSON.parse(saved);
    } catch (e) {
      currentData = { ...defaultData };
    }
  } else {
    currentData = { ...defaultData };
  }

  populateForm(currentData);
  updateDocument(currentData);
  bindEvents();
});

// Populate Form Inputs with Data Object
function populateForm(data) {
  // Tipo Acta Select
  const tipoActaSelect = document.getElementById("form-tipo-acta");
  if (tipoActaSelect) tipoActaSelect.value = data.tipoActa || "Entrega";

  fieldMap.forEach(item => {
    const el = document.getElementById(item.formId);
    if (el) {
      el.value = data[item.key] !== undefined ? data[item.key] : "";
    }
  });
}

// Read Form Inputs into Data Object
function readForm() {
  const data = {};
  const tipoActaSelect = document.getElementById("form-tipo-acta");
  data.tipoActa = tipoActaSelect ? tipoActaSelect.value : "Entrega";

  fieldMap.forEach(item => {
    const el = document.getElementById(item.formId);
    if (el) {
      data[item.key] = el.value;
    }
  });

  return data;
}

// Update Document Live Preview
function updateDocument(data) {
  // Update Tipo Acta Badges in Doc Header
  const docEntrega = document.getElementById("doc-acta-entrega");
  const docCambio = document.getElementById("doc-acta-cambio");

  if (docEntrega && docCambio) {
    if (data.tipoActa === "Entrega") {
      docEntrega.textContent = "SI";
      docEntrega.className = "font-bold underline text-blue-900";
      docCambio.textContent = "N.A";
      docCambio.className = "font-bold text-slate-500";
    } else if (data.tipoActa === "Cambio") {
      docEntrega.textContent = "N.A";
      docEntrega.className = "font-bold text-slate-500";
      docCambio.textContent = "SI";
      docCambio.className = "font-bold underline text-blue-900";
    } else {
      docEntrega.textContent = "NO";
      docEntrega.className = "font-bold";
      docCambio.textContent = "NO";
      docCambio.className = "font-bold";
    }
  }

  // Update fields
  fieldMap.forEach(item => {
    const docEl = document.getElementById(item.docId);
    if (docEl) {
      docEl.textContent = data[item.key] !== undefined && data[item.key] !== "" ? data[item.key] : "";
    }
  });

  // Save to localStorage
  localStorage.setItem("synerjoy_acta_data", JSON.stringify(data));
}

// Bind Event Listeners
function bindEvents() {
  const form = document.getElementById("acta-form");
  if (form) {
    form.addEventListener("input", () => {
      currentData = readForm();
      updateDocument(currentData);
    });
    form.addEventListener("change", () => {
      currentData = readForm();
      updateDocument(currentData);
    });
  }

  // Load Sample Button
  document.getElementById("btn-load-sample")?.addEventListener("click", () => {
    currentData = { ...defaultData };
    populateForm(currentData);
    updateDocument(currentData);
    showToast("Datos de caso Nicoll Martinez (GLPI 43560) cargados exitosamente.");
  });

  // Clear Button
  document.getElementById("btn-clear")?.addEventListener("click", () => {
    const emptyData = {};
    Object.keys(defaultData).forEach(k => emptyData[k] = "");
    emptyData.tipoActa = "Entrega";
    emptyData.tipoRed = "N/A";
    emptyData.tipoCorreo = "N/A";
    emptyData.desktop = "N/A";
    emptyData.portatil = "N/A";
    emptyData.diadema = "N.A";
    emptyData.perifCpu = "N.A";
    emptyData.teclado = "N.A";
    emptyData.movil = "N.A";
    emptyData.mouse = "N.A";
    emptyData.sim = "N.A";
    emptyData.otro = "N.A";
    emptyData.monitor = "N/A";

    currentData = emptyData;
    populateForm(currentData);
    updateDocument(currentData);
    showToast("Formulario limpiado.");
  });

  // Export JSON Button
  document.getElementById("btn-export-json")?.addEventListener("click", () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(currentData, null, 2));
    const downloadAnchor = document.createElement("a");
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `Acta_GLPI_${currentData.glpi || "entrega"}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
    showToast("JSON exportado correctamente.");
  });

  // Import JSON Input
  document.getElementById("input-import-json")?.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const importedData = JSON.parse(event.target.result);
        currentData = { ...defaultData, ...importedData };
        populateForm(currentData);
        updateDocument(currentData);
        showToast("JSON importado con éxito.");
      } catch (err) {
        showToast("Error al leer archivo JSON.");
      }
    };
    reader.readAsText(file);
  });

  // Copy TXT Button
  document.getElementById("btn-copy-txt")?.addEventListener("click", () => {
    const txt = generateFormattedText(currentData);
    navigator.clipboard.writeText(txt).then(() => {
      showToast("Texto resumido copiado al portapapeles.");
    }).catch(() => {
      showToast("Error al copiar texto.");
    });
  });

  // Print / PDF Button
  document.getElementById("btn-print")?.addEventListener("click", () => {
    window.print();
  });
}

// Generate Plain Text Summary
function generateFormattedText(data) {
  return `ACTA DE ENTREGA Y/O CAMBIO DE ACTIVOS TECNOLÓGICOS
Versión: 1.0 | Fecha: 24/02/2026 | Clasificación: Privado

FECHA: ${data.fecha} | SEDE: ${data.sede}
ACTA: Entrega: ${data.tipoActa === 'Entrega' ? 'SI' : 'N.A'} | Cambio: ${data.tipoActa === 'Cambio' ? 'SI' : 'N.A'}
N° CASO GLPI: ${data.glpi} | PROCESO/PORTAFOLIO: ${data.proceso}
NOMBRE COMPLETO: ${data.nombre} | CÉDULA: ${data.cedula}

USUARIOS
TIPO: Red ${data.tipoRed} | Correo ${data.tipoCorreo}
Windows: ${data.windows} | Cuenta de Correo: ${data.cuentaCorreo}
Acceso a HelpDesk (GLPI): ${data.helpdesk} | Novedades AIO: ${data.aio}
Impresora: ${data.impresora} | Control de Acceso: ${data.controlAcceso}
Recurso Compartido: ${data.recursoCompartido} | Licencia Office365: ${data.licenciaOffice}
Extensión: ${data.extension} | Perfil de Navegación: ${data.perfilNavegacion}
Power BI: ${data.powerbi} | VPN: ${data.vpn}

DESKTOP / PORTATIL
DESKTOP: ${data.desktop} | PORTATIL: ${data.portatil}
Equipo/Modelo: ${data.equipoModelo} | Serial: ${data.equipoSerial} | Serial Devuelto: ${data.equipoSerialDevuelto || 'N/A'}
Procesador: ${data.procesador} | Dirección IP: ${data.ip} | Memoria RAM: ${data.ram}
Disco Duro: ${data.disco} | Sistema Operativo: ${data.so} | Placa Inventario: ${data.placaInv}

PERIFERICOS ADICIONALES
DIADEMA: ${data.diadema} | CPU: ${data.perifCpu} | TECLADO: ${data.teclado} | MOVIL: ${data.movil}
MOUSE: ${data.mouse} | SIM: ${data.sim} | OTRO: ${data.otro} ${data.otroCual ? '(' + data.otroCual + ')' : ''}
Marca/Modelo: ${data.perifMarca} | Placa Inventario GLPI: ${data.perifPlaca}
Serial: ${data.perifSerial} | Serial Devuelto: ${data.perifSerialDev || 'N/A'}

MONITOR
MONITOR: ${data.monitor}
Marca/Modelo: ${data.monitorMarca} | Placa Inventario GLPI: ${data.monitorPlaca}
Serial: ${data.monitorSerial}

OBSERVACIONES:
${data.observaciones || 'Ninguna.'}

RESPONSABLES:
Entrega: ${data.entregaNombre} (${data.entregaCargo})
Revisó: ${data.revisoNombre} (${data.revisoCargo})
Aprobó: ${data.aproboNombre} (${data.aproboCargo})
Recibe: ${data.recibeNombre} (${data.recibeCargo})
`;
}

// Toast Helper
function showToast(msg) {
  const toast = document.getElementById("toast");
  const toastMsg = document.getElementById("toast-msg");
  if (!toast || !toastMsg) return;

  toastMsg.textContent = msg;
  toast.classList.remove("opacity-0", "pointer-events-none");
  toast.classList.add("opacity-100");

  setTimeout(() => {
    toast.classList.remove("opacity-100");
    toast.classList.add("opacity-0", "pointer-events-none");
  }, 3000);
}
