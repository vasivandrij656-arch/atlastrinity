import Foundation
import os.log

/// Comprehensive logging and debugging infrastructure for Windsurf MCP
class WindsurfLogger {
    static let shared = WindsurfLogger()
    
    private let cascadeLogger = Logger(subsystem: "com.atlastrinity.windsurf", category: "cascade")
    private let actionPhaseLogger = Logger(subsystem: "com.atlastrinity.windsurf", category: "actionphase")
    private let protobufLogger = Logger(subsystem: "com.atlastrinity.windsurf", category: "protobuf")
    private let fileSystemLogger = Logger(subsystem: "com.atlastrinity.windsurf", category: "filesystem")
    
    private let logDirectory: URL
    private let debugMode: Bool
    
    private init() {
        // Create logs directory in user's config
        let configPath = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        logDirectory = configPath.appendingPathComponent("atlastrinity").appendingPathComponent("logs").appendingPathComponent("windsurf")
        
        try? FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
        
        // Enable debug mode based on environment variable
        debugMode = ProcessInfo.processInfo.environment["WINDSURF_DEBUG"] == "true"
    }
    
    // MARK: - Cascade Logging
    
    func logCascadeStart(message: String, model: String, cascadeId: String) {
        let logEntry = CascadeLogEntry(
            type: .start,
            cascadeId: cascadeId,
            message: message,
            model: model,
            timestamp: Date()
        )
        
        cascadeLogger.info("Cascade started: \(cascadeId) with model: \(model)")
        writeLogEntry(logEntry, to: "cascade.jsonl")
    }
    
    func logCascadeResponse(cascadeId: String, response: String, duration: TimeInterval) {
        let logEntry = CascadeLogEntry(
            type: .response,
            cascadeId: cascadeId,
            response: response,
            duration: duration,
            timestamp: Date()
        )
        
        cascadeLogger.info("Cascade response received: \(cascadeId) in \(String(format: "%.2f", duration))s")
        writeLogEntry(logEntry, to: "cascade.jsonl")
    }
    
    func logCascadeError(cascadeId: String, error: String) {
        let logEntry = CascadeLogEntry(
            type: .error,
            cascadeId: cascadeId,
            error: error,
            timestamp: Date()
        )
        
        cascadeLogger.error("Cascade error: \(cascadeId) - \(error)")
        writeLogEntry(logEntry, to: "cascade.jsonl")
    }
    
    // MARK: - Action Phase Logging
    
    func logActionPhaseStart(cascadeId: String, workspacePath: String) {
        let logEntry = ActionPhaseLogEntry(
            type: .start,
            cascadeId: cascadeId,
            workspacePath: workspacePath,
            timestamp: Date()
        )
        
        actionPhaseLogger.info("Action Phase monitoring started: \(cascadeId)")
        writeLogEntry(logEntry, to: "actionphase.jsonl")
    }
    
    func logFileEvent(cascadeId: String, event: FileSystemMonitor.FileEvent) {
        let logEntry = ActionPhaseLogEntry(
            type: .fileEvent,
            cascadeId: cascadeId,
            filePath: event.path,
            eventType: event.type.description,
            timestamp: event.timestamp
        )
        
        actionPhaseLogger.info("File event: \(event.type.description) - \(event.path)")
        writeLogEntry(logEntry, to: "actionphase.jsonl")
    }
    
    func logActionPhaseComplete(cascadeId: String, result: ActionPhaseResult) {
        let logEntry = ActionPhaseLogEntry(
            type: .complete,
            cascadeId: cascadeId,
            result: result,
            timestamp: Date()
        )
        
        actionPhaseLogger.info("Action Phase completed: \(cascadeId) with \(result.fileEvents.count) events")
        writeLogEntry(logEntry, to: "actionphase.jsonl")
    }
    
    // MARK: - Protobuf Logging
    
    func logProtobufRequest(endpoint: String, payload: Data, cascadeId: String?) {
        guard debugMode else { return }
        
        let logEntry = ProtobufLogEntry(
            type: .request,
            endpoint: endpoint,
            payload: payload.hexString,
            payloadSize: payload.count,
            cascadeId: cascadeId,
            timestamp: Date()
        )
        
        protobufLogger.debug("Protobuf request: \(endpoint) (\(payload.count) bytes)")
        writeLogEntry(logEntry, to: "protobuf.jsonl")
    }
    
    func logProtobufResponse(endpoint: String, response: Data, cascadeId: String?) {
        guard debugMode else { return }
        
        let logEntry = ProtobufLogEntry(
            type: .response,
            endpoint: endpoint,
            payload: response.hexString,
            payloadSize: response.count,
            cascadeId: cascadeId,
            timestamp: Date()
        )
        
        protobufLogger.debug("Protobuf response: \(endpoint) (\(response.count) bytes)")
        writeLogEntry(logEntry, to: "protobuf.jsonl")
    }
    
    // MARK: - Field Experiment Logging
    
    func logFieldExperiment(_ experiment: FieldExperiment) {
        let fieldPairs = experiment.fields.map { FieldValuePair(field: $0.field, value: $0.value) }
        let logEntry = FieldExperimentLogEntry(
            experimentId: experiment.experimentId,
            fields: fieldPairs,
            success: experiment.success,
            responseTime: experiment.responseTime,
            cascadeId: experiment.cascadeId,
            fileCreated: experiment.fileCreated,
            error: experiment.error,
            timestamp: Date()
        )
        
        cascadeLogger.info("Field experiment \(experiment.experimentId): \(experiment.success ? "SUCCESS" : "FAILED")")
        writeLogEntry(logEntry, to: "experiments.jsonl")
    }
    
    // MARK: - Log File Management
    
    private func writeLogEntry<T: Codable>(_ entry: T, to filename: String) {
        let logFile = logDirectory.appendingPathComponent(filename)
        
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            let jsonData = try encoder.encode(entry)
            let jsonString = String(data: jsonData, encoding: .utf8) ?? "{}"
            
            // Append to file
            if FileManager.default.fileExists(atPath: logFile.path) {
                let fileHandle = try FileHandle(forWritingTo: logFile)
                fileHandle.seekToEndOfFile()
                fileHandle.write(jsonString.data(using: .utf8) ?? Data())
                fileHandle.write("\n".data(using: .utf8) ?? Data())
                fileHandle.closeFile()
            } else {
                try jsonString.write(to: logFile, atomically: true, encoding: .utf8)
            }
        } catch {
            fputs("log: [windsurf] Failed to write log entry: \(error)\n", stderr)
        }
    }
    
    // MARK: - Log Analysis
    
    func generateLogReport() -> LogReport {
        let cascadeLogs = readLogs(from: "cascade.jsonl", type: CascadeLogEntry.self)
        let actionPhaseLogs = readLogs(from: "actionphase.jsonl", type: ActionPhaseLogEntry.self)
        let experimentLogs = readLogs(from: "experiments.jsonl", type: FieldExperimentLogEntry.self)
        
        return LogReport(
            cascadeLogs: cascadeLogs,
            actionPhaseLogs: actionPhaseLogs,
            experimentLogs: experimentLogs,
            generatedAt: Date()
        )
    }
    
    private func readLogs<T: Codable>(from filename: String, type: T.Type) -> [T] {
        let logFile = logDirectory.appendingPathComponent(filename)
        guard FileManager.default.fileExists(atPath: logFile.path) else { return [] }
        
        do {
            let content = try String(contentsOfFile: logFile.path)
            let lines = content.components(separatedBy: .newlines).filter { !$0.isEmpty }
            
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            
            var logs: [T] = []
            for line in lines {
                if let data = line.data(using: .utf8),
                   let log = try? decoder.decode(type, from: data) {
                    logs.append(log)
                }
            }
            
            return logs
        } catch {
            fputs("log: [windsurf] Failed to read logs from \(filename): \(error)\n", stderr)
            return []
        }
    }
}

// MARK: - Log Entry Models

struct CascadeLogEntry: Codable {
    let type: String
    let cascadeId: String
    let message: String?
    let model: String?
    let response: String?
    let duration: TimeInterval?
    let error: String?
    let timestamp: Date
    
    init(type: CascadeEventType, cascadeId: String, message: String? = nil, model: String? = nil, response: String? = nil, duration: TimeInterval? = nil, error: String? = nil, timestamp: Date) {
        self.type = type.rawValue
        self.cascadeId = cascadeId
        self.message = message
        self.model = model
        self.response = response
        self.duration = duration
        self.error = error
        self.timestamp = timestamp
    }
}

enum CascadeEventType: String, Codable {
    case start = "start"
    case response = "response"
    case error = "error"
}

struct ActionPhaseLogEntry: Codable {
    let type: String
    let cascadeId: String
    let workspacePath: String?
    let filePath: String?
    let eventType: String?
    let result: ActionPhaseResult?
    let timestamp: Date
    
    init(type: ActionPhaseEventType, cascadeId: String, workspacePath: String? = nil, filePath: String? = nil, eventType: String? = nil, result: ActionPhaseResult? = nil, timestamp: Date) {
        self.type = type.rawValue
        self.cascadeId = cascadeId
        self.workspacePath = workspacePath
        self.filePath = filePath
        self.eventType = eventType
        self.result = result
        self.timestamp = timestamp
    }
}

enum ActionPhaseEventType: String, Codable {
    case start = "start"
    case fileEvent = "file_event"
    case complete = "complete"
}

struct ProtobufLogEntry: Codable {
    let type: String
    let endpoint: String
    let payload: String
    let payloadSize: Int
    let cascadeId: String?
    let timestamp: Date
    
    init(type: ProtobufLogType, endpoint: String, payload: String, payloadSize: Int, cascadeId: String?, timestamp: Date) {
        self.type = type.rawValue
        self.endpoint = endpoint
        self.payload = payload
        self.payloadSize = payloadSize
        self.cascadeId = cascadeId
        self.timestamp = timestamp
    }
}

enum ProtobufLogType: String, Codable {
    case request = "request"
    case response = "response"
}

struct FieldExperimentLogEntry: Codable {
    let experimentId: Int
    let fields: [FieldValuePair]
    let success: Bool
    let responseTime: TimeInterval
    let cascadeId: String?
    let fileCreated: Bool?
    let error: String?
    let timestamp: Date
}

struct FieldValuePair: Codable {
    let field: Int
    let value: Int
}

struct LogReport {
    let cascadeLogs: [CascadeLogEntry]
    let actionPhaseLogs: [ActionPhaseLogEntry]
    let experimentLogs: [FieldExperimentLogEntry]
    let generatedAt: Date
    
    var summary: String {
        var summary = """
        📊 Windsurf MCP Log Report
        ═══════════════════════════
        🕒 Generated: \(generatedAt)
        
        📈 Cascade Operations: \(cascadeLogs.count)
        """
        
        let successfulCascades = cascadeLogs.filter { $0.type == "response" }.count
        let failedCascades = cascadeLogs.filter { $0.type == "error" }.count
        
        summary += "\n   ✅ Successful: \(successfulCascades)"
        summary += "\n   ❌ Failed: \(failedCascades)"
        
        summary += "\n\n🎯 Action Phase Events: \(actionPhaseLogs.count)"
        let fileEvents = actionPhaseLogs.filter { $0.type == "file_event" }.count
        summary += "\n   📁 File Events: \(fileEvents)"
        
        summary += "\n\n🧪 Field Experiments: \(experimentLogs.count)"
        let successfulExperiments = experimentLogs.filter { $0.success }.count
        summary += "\n   ✅ Successful: \(successfulExperiments)"
        
        return summary
    }
}

// MARK: - Data Extensions

extension Data {
    var hexString: String {
        return map { String(format: "%02x", $0) }.joined()
    }
}

// MARK: - ActionPhaseResult Codable Extension

extension ActionPhaseResult: Codable {
    enum CodingKeys: String, CodingKey {
        case duration, fileEvents, success
    }
    
    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        duration = try container.decode(TimeInterval.self, forKey: .duration)
        
        let eventsData = try container.decode([FileEventCodable].self, forKey: .fileEvents)
        fileEvents = eventsData.map { FileSystemMonitor.FileEvent(path: $0.path, type: $0.type, timestamp: $0.timestamp) }
        
        success = try container.decode(Bool.self, forKey: .success)
    }
    
    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(duration, forKey: .duration)
        
        let eventsCodable = fileEvents.map { FileEventCodable(path: $0.path, type: $0.type, timestamp: $0.timestamp) }
        try container.encode(eventsCodable, forKey: .fileEvents)
        
        try container.encode(success, forKey: .success)
    }
}

struct FileEventCodable: Codable {
    let path: String
    let type: FileSystemMonitor.FileEvent.EventType
    let timestamp: Date
}
