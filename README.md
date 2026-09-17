# Sistema de Votación

## Flujo del votante
- El votante entra a `/votar`.
- Primera pantalla: **solamente carnet**.
- Si el carnet existe y está activo, entra a votar sin escribir nombre.
- Si el carnet no existe, el sistema solicita **nombre completo + carnet** y crea el registro.
- Nombre y carnet son únicos.
- El carnet se normaliza quitando espacios y pasando letras a mayúsculas.
- La cookie del votante está separada de la sesión del administrador, por lo que abrir el panel de administración en otra pestaña no reemplaza la sesión del votante.

## Administración
- Elecciones, categorías, candidatos y padrón.
- Edición de votantes funcionando con modal válido fuera de `tbody`.
- Carnet obligatorio y único.
- No se puede modificar identidad de un votante que ya emitió votos.
- No se eliminan candidatos/categorías/votantes que ya tengan información electoral sensible; se recomienda desactivar.
- Resultados incluyen candidatos con cero votos.
- Exportación CSV.
- Registro de auditoría.
- Protección CSRF en formularios POST.

## Instalación en Windows
```powershell
cd backend
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
Si `py` no existe, usar `python -m venv venv`.

Crear `.env` a partir de `.env.example` y configurar MySQL.

## Base de datos
Para una instalación nueva, ejecutar `database/schema.sql`.
Para una base existente, hacer respaldo y revisar `database/upgrade_sistema.sql` antes de aplicar cambios.

## Ejecutar
```powershell
python run.py
```

Después abrir `http://127.0.0.1:5000/votar` para el votante o `/login` para administración.
