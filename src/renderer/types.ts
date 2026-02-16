export type AgentName = 'ATLAS' | 'TETYANA' | 'GRISHA' | 'SYSTEM' | 'USER';
export type SystemState = 'IDLE' | 'PROCESSING' | 'EXECUTING' | 'VERIFYING' | 'ERROR' | 'PAUSED';

export interface LogEntry {
  id: string;
  timestamp: Date;
  agent: AgentName;
  message: string;
  type: 'info' | 'action' | 'success' | 'warning' | 'error' | 'voice';
}

export interface ChatMessage {
  id?: string;
  agent: AgentName;
  text: string;
  timestamp: Date;
  type?: 'text' | 'voice';
}

export interface SystemMetrics {
  cpu: string;
  memory: string;
  net_up_val: string;
  net_up_unit: string;
  net_down_val: string;
  net_down_unit: string;
}

export interface MapData {
  url?: string;
  type: 'STREET' | 'STATIC' | 'INTERACTIVE';
  location?: string;
  agentView?: {
    heading: number;
    pitch: number;
    fov: number;
    timestamp: string;
    lat?: number;
    lng?: number;
  } | null;
  distanceInfo?: {
    distance?: string;
    duration?: string;
    origin?: string;
    destination?: string;
  } | null;
}

export interface Session {
  id: string;
  theme: string;
  saved_at: string;
}
