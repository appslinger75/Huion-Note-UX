# Huion Note Sync

Aplicación de escritorio desarrollada en Python con **PySide6** para sincronizar, conectar y visualizar contenido manuscrito desde un dispositivo **Huion Note** (compatible con macOS y Windows) a través de Bluetooth Low Energy (BLE).

---

## 📦 Paquetes necesarios

Para que la aplicación funcione correctamente, se requieren las siguientes librerías de Python:

* **`bleak`**: Biblioteca multiplataforma estándar para la comunicación mediante Bluetooth Low Energy (BLE).
* **`PySide6`**: Framework oficial de Qt para Python encargado de renderizar la interfaz gráfica de usuario (GUI) y manejar los gráficos vectoriales del lienzo.
* **`qasync`**: Permite integrar de forma nativa el bucle de eventos asíncronos (`asyncio`) con el bucle de eventos de la interfaz gráfica de Qt.
* **`Pillow` (PIL)**: Librería para la manipulación, renderizado y exportación de imágenes rasterizadas en alta calidad (PNG/SVG).

---

## ⚙️ Comandos de instalación

Abre tu terminal o línea de comandos y ejecuta el siguiente comando para instalar todas las dependencias necesarias de una sola vez:

```bash
pip install bleak PySide6 qasync Pillow
```

Si prefieres utilizar un entorno virtual (altamente recomendado), sigue estos pasos antes de instalar los paquetes:

**En macOS / Linux:**
```bash
python -m venv venv
source venv/bin/activate
pip install bleak PySide6 qasync Pillow
```

**En Windows (CMD / PowerShell):**
```bash
python -m venv venv
venv\Scripts\activate
pip install bleak PySide6 qasync Pillow
```

---

## 🚀 Funcionamiento del programa

1. **Escaneo y Conexión BLE:** La aplicación busca activamente en el entorno Bluetooth cercano para localizar el dispositivo Huion Note y establece una conexión segura empleando los UUIDs de servicio específicos (`FFE0`, `FFE1`, `FFE2`).
2. **Autenticación Segura:** Al conectarse, ejecuta un proceso automatizado de desafío-respuesta con el firmware del dispositivo para validar la sesión.
3. **Sincronización Inteligente:** Al pulsar el botón de sincronización, el programa evalúa el estado del dispositivo y contrasta las páginas con la base de datos local para descargar únicamente el contenido nuevo.
4. **Almacenamiento Local:** Las páginas manuscritas se descargan por paquetes, se procesan y se guardan automáticamente en formato **JSON, SVG y PNG** dentro de la carpeta designada por el usuario (por defecto: `Documents/Huion Note/AAAA-MM-DD`).
5. **Visor Gráfico y Navegación Multipágina:** Las trazas del lápiz se renderizan de forma vectorial y fluida en el lienzo principal, permitiendo examinar todas las páginas sincronizadas de forma instantánea mediante los controles integrados.

---

## 🔍 Explicación detallada de las características del archivo Python

### 1. Sincronización optimizada sin duplicados
El script integra una base de datos local basada en **SQLite** (`pages.sqlite3`). Cada vez que se descarga una página, el sistema calcula un hash único (`SHA-256`) a partir de las coordenadas, presiones y estados de los trazos, y comprueba el número de página lógica. Si la página ya se encuentra registrada en la base de datos, el script la omite de forma inteligente. Esto acelera drásticamente las sincronizaciones posteriores y previene por completo la duplicación innecesaria de archivos en el disco duro.

### 2. Solución al problema del cursor del ratón
Uno de los problemas más comunes en herramientas BLE para tabletas de notas es que el sistema operativo intérprete erróneamente los paquetes de datos del lápiz como eventos de un dispositivo HID genérico (movimientos de ratón o tableta), provocando bloqueos o comportamientos extraños en el cursor. Este script soluciona este inconveniente mediante un **bloqueo estricto de E/S (`io_paused` y control de bloqueos BLE)**. Durante los procesos críticos de sincronización, la recepción de eventos en vivo se aísla por completo, garantizando que puedas utilizar tu ratón, trackpad y teclado con absoluta normalidad mientras el programa trabaja en segundo plano.

### 3. Navegación multipágina en la vista previa
A diferencia de los visores estáticos de una sola página, este script cuenta con un sistema de almacenamiento en memoria (`synced_pages`) sincronizado con una barra de navegación interactiva equipada con los botones **◀ Anterior** y **Siguiente ▶**. Esto te permite recorrer libremente y al instante todas las páginas que se han sincronizado del dispositivo físico, consultando el número de página actual, el índice total y la cantidad de puntos analizados sin necesidad de salir de la aplicación o abrir carpetas externas.

### 4. Escucha pasiva segura
El modo de visualización en tiempo real está diseñado bajo un enfoque de **escucha pasiva**. En lugar de enviar comandos de control agresivos o modificar los registros internos del dispositivo de forma intrusiva, la aplicación se suscribe únicamente a las tramas de datos emitidas de forma natural por el hardware (`OP_ONLINE_DATA`). Esto previene conflictos con los controladores nativos del sistema operativo y asegura una estabilidad total durante el uso prolongado.