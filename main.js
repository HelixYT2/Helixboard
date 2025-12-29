const { app, BrowserWindow } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let mainWindow;
let apiProcess;

// Adjust paths for dev vs prod
// In dev: python backend/server.py
// In prod: resources/backend/server.exe

const isDev = !app.isPackaged;

function createPyProc() {
  let script = path.join(__dirname, 'backend', 'server.py');
  let cmd = 'python3';
  let args = [script];

  if (!isDev) {
    // In production, use the bundled executable
    // It is in resources/backend/server.exe
    // process.resourcesPath points to resources/
    cmd = path.join(process.resourcesPath, 'backend', 'server.exe');
    args = [];
  }

  console.log(`Starting backend: ${cmd} ${args}`);
  apiProcess = spawn(cmd, args);

  apiProcess.stdout.on('data', (data) => {
    console.log(`[Backend]: ${data}`);
  });

  apiProcess.stderr.on('data', (data) => {
    console.error(`[Backend Error]: ${data}`);
  });

  apiProcess.on('close', (code) => {
      console.log(`Backend exited with code ${code}`);
  });
}

function exitPyProc() {
  if (apiProcess) {
    apiProcess.kill();
    apiProcess = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1366,
    height: 900,
    backgroundColor: '#131314', // Match BG_DARK
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // Simplifying for this migration
    },
    icon: path.join(__dirname, 'helix_logo.png')
  });

  mainWindow.loadFile('index.html');

  mainWindow.on('closed', function () {
    mainWindow = null;
  });
}

app.on('ready', () => {
  createPyProc();
  // Poll backend
  const checkServer = () => {
      const http = require('http');
      http.get('http://127.0.0.1:5000/dms/friends', (res) => { // arbitrary safe endpoint
          if (res.statusCode === 200 || res.statusCode === 400 || res.statusCode === 500) {
              createWindow();
          } else {
              setTimeout(checkServer, 500);
          }
      }).on('error', (e) => {
          setTimeout(checkServer, 500);
      });
  };
  checkServer();
});

app.on('window-all-closed', function () {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  exitPyProc();
});
