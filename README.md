# Huion Note Sync

[![Python Version](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey.svg)]()

**Huion Note Sync** es una aplicación de escritorio avanzada para sincronizar, visualizar y exportar contenido manuscrito desde cuadernos digitales **Huion Note** a través de Bluetooth Low Energy (BLE). Diseñada en Python con **PySide6**, ofrece captura en tiempo real, sincronización en segundo plano sin duplicación, procesamiento vectorial y motor de **Reconocimiento Óptico de Caracteres (OCR)** nativo e integrado para Windows y macOS.

---

## 🚀 Características principales

* **Sincronización Inteligente:** Base de datos SQLite integrada que utiliza hashes de contenido (`SHA-256`) para evitar la descarga de páginas duplicadas.
* **Aislamiento de E/S BLE:** Aislamiento de eventos durante las transferencias de datos para prevenir interferencias con el ratón o el cursor del sistema operativo.
* **Preprocesado de Trazos para OCR:** Algoritmo geométrico propio que suaviza, orienta, corrige la inclinación y normaliza el tamaño de la letra antes del reconocimiento óptico.
* **OCR Local Nativo:**
  * **Windows:** Integración nativa mediante el motor `Windows.Media.Ocr`.
  * **macOS:** Integración con el framework nativo `Vision` (`VNRecognizeTextRequest`).
* **División de Páginas Mezcladas:** Herramienta interactiva para cortar páginas cuando se escribe en hojas distintas sin presionar el botón físico de función del dispositivo.
* **Escucha Pasiva en Tiempo Real:** Visualización fluida de trazos vectoriales en vivo mediante suscripción BLE sin modificar el firmware del cuaderno.
* **Multi-exportación:** Generación automática de archivos en formato JSON (datos crudos), vectoriales SVG y mapas de bits PNG en la ruta seleccionada.

---

## 📦 Requisitos del sistema

* **Python 3.9** o superior.
* Sistema operativo **Windows 10/11** o **macOS 11+** (Big Sur o posterior).
* Adaptador Bluetooth compatible con **Bluetooth Low Energy (BLE)**.

---

## 💻 Instalación paso a paso

### 1. Clonar o descargar el repositorio
```bash
git clone https://github.com/tu-usuario/huion-note-sync.git
cd huion-note-sync
```

### 2. Configurar el entorno virtual e instalar dependencias

#### 🍎 macOS

Abre la Terminal y ejecuta:

```bash
# Crear entorno virtual
python3 -m venv venv

# Activar entorno virtual
source venv/bin/activate

# Actualizar el gestor de paquetes pip
pip install --upgrade pip

# Instalar dependencias obligatorias
pip install bleak PySide6 qasync Pillow

# (Opcional) Instalar soporte para el motor de OCR nativo de macOS (Vision)
pip install pyobjc-framework-Vision
```

#### 🪟 Windows (PowerShell / CMD)

Abre la línea de comandos o PowerShell y ejecuta:

```powershell
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En PowerShell:
.\venv\Scripts\Activate.ps1
# En CMD:
.\venv\Scripts\activate.bat

# Actualizar pip
python -m pip install --upgrade pip

# Instalar dependencias requeridas
pip install bleak PySide6 qasync Pillow
```

> **Nota para usuarios de Windows:** El motor de OCR utiliza `Windows.Media.Ocr`. Asegúrate de tener instalado el paquete de idioma correspondiente (ej. Español o Inglés) en **Configuración > Hora e idioma > Idioma y región** para habilitar el reconocimiento de texto.

---

## 🛠️ Modo de empleo

### Ejecución de la aplicación

Con el entorno virtual activado, ejecuta el script principal:

```bash
python huion_note_sync.py
```

### Flujo de trabajo principal

1. **Conexión:** Enciende el cuaderno Huion Note y asegúrate de que la aplicación oficial esté cerrada. Haz clic en **Conectar** en la barra superior.
2. **Sincronización:** Pulsa **Sincronizar** para descargar las páginas almacenadas en el cuaderno. La aplicación omitirá automáticamente aquellas descargadas previamente.
3. **Escucha en Vivo:** Activa el modo de tiempo real para ver las trazadas vectoriales en la pantalla a medida que escribes en la libreta.
4. **Dividir Páginas:** Si dos hojas se guardaron en una misma página por no presionar el botón de paso de página del cuaderno, utiliza el botón de **Dividir página** para ajustar el corte cronológico del trazo.
5. **Reconocimiento OCR y Medición:** Selecciona una página sincronizada y procesa el texto manuscrito o utiliza el panel de **Medición** para comparar la precisión del OCR directo frente al OCR preprocesado.

---

## 📐 Estructura del proyecto

```text
.
├── huion_note_sync.py       # Aplicación principal PyQt/PySide6 y cliente BLE
├── README.md                # Documentación del proyecto
└── Documents/Huion Note/    # Carpeta por defecto para exportaciones (configurable)
    └── YYYY-MM-DD/
        ├── pages.sqlite3    # Base de datos local de páginas
        └── page_XXX.png     # Archivos exportados
```

---

## 📄 Licencia

Este proyecto está bajo la Licencia MIT. Consulta el archivo `LICENSE` para obtener más información.