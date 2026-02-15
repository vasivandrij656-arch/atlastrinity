/// <reference types="vite/client" />

interface Window {
  electron: {
    readBrainLog: () => Promise<string[]>;
  };
}
