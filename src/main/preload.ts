import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electron', {
  readBrainLog: () => ipcRenderer.invoke('read-brain-log'),
  startLogStream: () => ipcRenderer.send('start-log-stream'),
  stopLogStream: () => ipcRenderer.send('stop-log-stream'),
  onLogUpdate: (callback: (lines: string[]) => void) => {
    const subscription = (_event: import('electron').IpcRendererEvent, lines: string[]) =>
      callback(lines);
    ipcRenderer.on('log-update', subscription);

    return () => ipcRenderer.removeListener('log-update', subscription);
  },
});
