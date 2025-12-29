# Build Instructions

## Prerequisites
1.  **Python 3.10+** installed.
2.  **Node.js 18+** installed.
3.  **Git**.

## 1. Setup Python Environment
Create a virtual environment and install dependencies.

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install flask openai requests pillow bcrypt
pip install pyinstaller
```

## 2. Build Backend Executable
Compile the Flask backend into a standalone executable.

```bash
# From the root directory
pyinstaller --onefile --distpath backend_dist --name server backend/server.py
```
This will create `backend_dist/server.exe` (or `server` on Unix).

## 3. Setup Electron
Install Node dependencies.

```bash
npm install
```

## 4. Build & Package Electron App
This uses `electron-builder` to package the app and bundle the Python backend.

```bash
npm run dist
```
The final installer/executable will be in the `dist/` folder.

## Troubleshooting
*   **Missing Imports:** Ensure all python packages used in `server.py` are installed in your venv before running PyInstaller.
*   **Backend not starting:** Check `main.js` paths. In production, it looks for `resources/backend/server.exe`.
*   **Infinite Loop:** The `main.js` spawns the python process once. Ensure `server.py` uses `if __name__ == "__main__": app.run()` to prevent multiprocessing spawn loops (already handled).
