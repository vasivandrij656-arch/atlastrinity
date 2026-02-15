import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('electron', {
  readBrainLog: () => ipcRenderer.invoke('read-brain-log'),
});
