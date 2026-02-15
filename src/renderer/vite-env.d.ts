/// <reference types="vite/client" />

interface Window {
  electron: {
    readBrainLog: () => Promise<string[]>;
    startLogStream: () => void;
    stopLogStream: () => void;
    onLogUpdate: (callback: (lines: string[]) => void) => () => void;
  };
}
