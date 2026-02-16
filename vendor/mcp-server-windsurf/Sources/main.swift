import Darwin
import Foundation
import MCP

// MARK: - Graceful Shutdown

class GracefulShutdown {
    private let shutdownSemaphore = DispatchSemaphore(value: 0)
    private var isShuttingDown = false

    static let shared = GracefulShutdown()

    private init() {}

    func setupSignalHandlers() {
        // Set up signal handling using global function pointers
        signal(SIGTERM, sigtermHandler)
        signal(SIGINT, sigintHandler)
    }

    func initiateShutdown() {
        guard !isShuttingDown else { return }
        isShuttingDown = true
        shutdownSemaphore.signal()
    }

    func waitForShutdown() {
        setupSignalHandlers()
        shutdownSemaphore.wait()
        fputs("log: [windsurf] Graceful shutdown completed\n", stderr)
    }
}

// Global C-compatible signal handlers
private func sigtermHandler(_ sig: Int32) {
    fputs("log: [windsurf] Received SIGTERM, shutting down gracefully...\n", stderr)
    GracefulShutdown.shared.initiateShutdown()
}

private func sigintHandler(_ sig: Int32) {
    fputs("log: [windsurf] Received SIGINT, shutting down gracefully...\n", stderr)
    GracefulShutdown.shared.initiateShutdown()
}

let gracefulShutdown = GracefulShutdown.shared

// MARK: - Configuration

/// Windsurf LS endpoints (Connect-RPC / HTTP)
let LS_RAW_CHAT = "/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
let LS_HEARTBEAT = "/exa.language_server_pb.LanguageServerService/Heartbeat"
let LS_START_CASCADE = "/exa.language_server_pb.LanguageServerService/StartCascade"
let LS_STREAM_CASCADE = "/exa.language_server_pb.LanguageServerService/StreamCascadeReactiveUpdates"
let LS_QUEUE_CASCADE = "/exa.language_server_pb.LanguageServerService/QueueCascadeMessage"
let LS_INTERRUPT_CASCADE = "/exa.language_server_pb.LanguageServerService/InterruptCascade"
let LS_INTERRUPT_WITH_MESSAGE =
    "/exa.language_server_pb.LanguageServerService/InterruptWithQueuedMessage"

/// Configuration constants
let DEFAULT_TIMEOUT: TimeInterval = 30
let CASCADE_TIMEOUT: TimeInterval = 120  // Increased from 90s
let HEARTBEAT_TIMEOUT: TimeInterval = 5
let MAX_RETRY_ATTEMPTS = 3
let RETRY_BASE_DELAY: TimeInterval = 0.5

/// Default IDE metadata
let IDE_VERSION = "1.9552.21"
let EXTENSION_VERSION = "1.48.2"

// MARK: - Health Monitoring

struct HealthMetrics {
    var totalRequests: Int = 0
    var successfulRequests: Int = 0
    var failedRequests: Int = 0
    var chatRequests: Int = 0
    var cascadeRequests: Int = 0
    var lsDetections: Int = 0
    var lsDetectionsFailed: Int = 0
    var averageLatency: Double = 0.0
    var lastRequestTime: Date = Date()
    var startTime: Date = Date()

    mutating func recordRequest(success: Bool, latency: Double, type: String) {
        totalRequests += 1
        lastRequestTime = Date()

        if success {
            successfulRequests += 1
        } else {
            failedRequests += 1
        }

        // Update type-specific counters
        switch type {
        case "chat":
            chatRequests += 1
        case "cascade":
            cascadeRequests += 1
        case "ls_detection":
            lsDetections += 1
            if !success {
                lsDetectionsFailed += 1
            }
        default:
            break
        }

        // Update average latency (simple moving average)
        averageLatency =
            (averageLatency * Double(totalRequests - 1) + latency) / Double(totalRequests)
    }

    func getSuccessRate() -> Double {
        return totalRequests > 0 ? Double(successfulRequests) / Double(totalRequests) : 0.0
    }

    func getUptime() -> TimeInterval {
        return Date().timeIntervalSince(startTime)
    }
}

actor HealthMonitor {
    private var metrics = HealthMetrics()

    func recordRequest(success: Bool, latency: Double, type: String) {
        metrics.recordRequest(success: success, latency: latency, type: type)
    }

    func getMetrics() -> HealthMetrics {
        return metrics
    }

    func getHealthStatus() -> String {
        let uptime = metrics.getUptime()
        let successRate = metrics.getSuccessRate()
        let uptimeFormatted = String(format: "%.0f", uptime / 60)  // minutes

        var status = """
            📊 Windsurf MCP Health Status
            ═════════════════════════════
            ⏱️ Uptime: \(uptimeFormatted) min
            📈 Success Rate: \(String(format: "%.1f", successRate * 100))%
            🔢 Total Requests: \(metrics.totalRequests)
            💬 Chat Requests: \(metrics.chatRequests)
            🌊 Cascade Requests: \(metrics.cascadeRequests)
            🔍 LS Detections: \(metrics.lsDetections)/\(metrics.lsDetectionsFailed) failed
            ⚡ Avg Latency: \(String(format: "%.2f", metrics.averageLatency))s
            """

        // Health indicator based on success rate
        let healthEmoji: String
        if successRate >= 0.9 {
            healthEmoji = "🟢"
        } else if successRate >= 0.7 {
            healthEmoji = "🟡"
        } else {
            healthEmoji = "🔴"
        }

        status += "\n\(healthEmoji) Overall Health: \(String(format: "%.1f", successRate * 100))%"

        return status
    }
}

let healthMonitor = HealthMonitor()

// MARK: - Protobuf Helpers

/// Encode an integer as a protobuf varint
func protoVarint(_ val: Int) -> Data {
    var v = val
    var data = Data()
    while v > 0x7F {
        data.append(UInt8((v & 0x7F) | 0x80))
        v >>= 7
    }
    data.append(UInt8(v))
    return data
}

/// Encode a string field in protobuf binary format
func protoStr(_ fieldNum: Int, _ s: String) -> Data {
    let b = s.data(using: .utf8) ?? Data()
    var data = protoVarint((fieldNum << 3) | 2)
    data.append(protoVarint(b.count))
    data.append(b)
    return data
}

/// Encode an integer field in protobuf binary format
func protoInt(_ fieldNum: Int, _ val: Int) -> Data {
    var data = protoVarint((fieldNum << 3) | 0)
    data.append(protoVarint(val))
    return data
}

/// Encode a sub-message field in protobuf binary format
func protoMsg(_ fieldNum: Int, _ inner: Data) -> Data {
    var data = protoVarint((fieldNum << 3) | 2)
    data.append(protoVarint(inner.count))
    data.append(inner)
    return data
}

/// Build Metadata proto binary (exa.codeium_common_pb.Metadata)
func buildMetadataProto(apiKey: String, sessionId: String) -> Data {
    var data = Data()
    data.append(protoStr(1, "windsurf"))
    data.append(protoStr(2, EXTENSION_VERSION))
    data.append(protoStr(3, apiKey))
    data.append(protoStr(4, "en"))
    data.append(protoStr(7, IDE_VERSION))
    data.append(protoInt(9, 1))
    data.append(protoStr(10, sessionId))
    return data
}

/// Extract string at target field from proto binary
func protoExtractString(_ data: Data, _ targetField: Int) -> String? {
    var offset = 0
    let len = data.count

    while offset < len {
        // Read tag
        var tag = 0
        var shift = 0
        while offset < len {
            let b = data[offset]
            offset += 1
            tag |= (Int(b & 0x7F) << shift)
            shift += 7
            if (b & 0x80) == 0 { break }
        }

        let fieldNum = tag >> 3
        let wireType = tag & 0x07

        if fieldNum == 0 { break }

        if wireType == 0 {  // Varint
            while offset < len {
                let b = data[offset]
                offset += 1
                if (b & 0x80) == 0 { break }
            }
        } else if wireType == 2 {  // Length Delimited
            var length = 0
            var s = 0
            while offset < len {
                let b = data[offset]
                offset += 1
                length |= (Int(b & 0x7F) << s)
                s += 7
                if (b & 0x80) == 0 { break }
            }

            if offset + length > len { break }
            let payload = data.subdata(in: offset..<offset + length)
            offset += length

            if fieldNum == targetField {
                return String(data: payload, encoding: .utf8)
            }
        } else if wireType == 1 {  // 64-bit
            offset += 8
        } else if wireType == 5 {  // 32-bit
            offset += 4
        } else {
            break
        }
    }
    return nil
}

/// Recursively find all strings in proto binary (fallback)
func protoFindStrings(_ data: Data, minLen: Int = 4) -> [String] {
    var results: [String] = []
    var offset = 0
    let len = data.count

    while offset < len {
        // Read tag
        var tag = 0
        var shift = 0
        while offset < len {
            let b = data[offset]
            offset += 1
            tag |= (Int(b & 0x7F) << shift)
            shift += 7
            if (b & 0x80) == 0 { break }
        }

        let fieldNum = tag >> 3
        let wireType = tag & 0x07

        if fieldNum == 0 { break }

        if wireType == 0 {  // Varint
            while offset < len {
                let b = data[offset]
                offset += 1
                if (b & 0x80) == 0 { break }
            }
        } else if wireType == 2 {  // Length Delimited
            var length = 0
            var s = 0
            while offset < len {
                let b = data[offset]
                offset += 1
                length |= (Int(b & 0x7F) << s)
                s += 7
                if (b & 0x80) == 0 { break }
            }

            if offset + length > len { break }
            let payload = data.subdata(in: offset..<offset + length)
            offset += length

            if let text = String(data: payload, encoding: .utf8), text.count >= minLen {
                results.append(text)
            }
            // Recurse
            results.append(contentsOf: protoFindStrings(payload, minLen: minLen))

        } else if wireType == 1 {  // 64-bit
            offset += 8
        } else if wireType == 5 {  // 32-bit
            offset += 4
        } else {
            break
        }
    }
    return results
}

// MARK: - Windsurf Models

struct WindsurfModel {
    let id: String
    let displayName: String
    let protobufId: String
    let tier: String  // "free", "value", "premium"
    let family: String
}

let WINDSURF_MODELS: [WindsurfModel] = [
    // Cascade Models
    WindsurfModel(
        id: "swe-1.5", displayName: "SWE-1.5", protobufId: "MODEL_SWE_1_5", tier: "free",
        family: "swe"),
    WindsurfModel(
        id: "swe-1", displayName: "SWE-1", protobufId: "MODEL_SWE_1", tier: "free", family: "swe"),
    WindsurfModel(
        id: "swe-1-mini", displayName: "SWE-1-mini", protobufId: "MODEL_SWE_1_MINI", tier: "free",
        family: "swe"),
    WindsurfModel(
        id: "swe-grep", displayName: "SWE-grep", protobufId: "MODEL_SWE_GREP", tier: "free",
        family: "swe"),
    WindsurfModel(
        id: "windsurf-fast", displayName: "Windsurf Fast", protobufId: "MODEL_CHAT_11121",
        tier: "free", family: "windsurf"),

    // Windsurf Premier 🚀
    WindsurfModel(
        id: "llama-3.1-405b", displayName: "Llama 3.1 405B (Premier)",
        protobufId: "MODEL_LLAMA_3_1_405B", tier: "premium", family: "llama-3"),
    WindsurfModel(
        id: "llama-3.1-70b", displayName: "Llama 3.1 70B (Base)", protobufId: "MODEL_LLAMA_3_1_70B",
        tier: "free", family: "llama-3"),

    // Next-Gen Premium (Changelog)
    WindsurfModel(
        id: "claude-4.6-opus", displayName: "Claude 4.6 Opus", protobufId: "MODEL_CLAUDE_4_6_OPUS",
        tier: "premium", family: "claude-4.6-opus"),
    WindsurfModel(
        id: "claude-4.6-opus-fast", displayName: "Claude 4.6 Opus (Fast Mode)",
        protobufId: "MODEL_CLAUDE_4_6_OPUS_FAST", tier: "premium", family: "claude-4.6-opus"),
    WindsurfModel(
        id: "gpt-5.2-codex", displayName: "GPT-5.2 Codex (Reasoning)",
        protobufId: "MODEL_GPT_5_2_CODEX", tier: "premium", family: "gpt-5-codex"),
    WindsurfModel(
        id: "gpt-5.3-codex-spark", displayName: "GPT-5.3 Codex-Spark (Arena)",
        protobufId: "MODEL_GPT_5_3_CODEX_SPARK", tier: "premium", family: "gpt-5-codex"),
    WindsurfModel(
        id: "gemini-3-pro", displayName: "Gemini 3 Pro", protobufId: "MODEL_GEMINI_3_PRO",
        tier: "free", family: "gemini-3"),
    WindsurfModel(
        id: "gemini-3-flash", displayName: "Gemini 3 Flash (3x Fast)",
        protobufId: "MODEL_GEMINI_3_FLASH", tier: "free", family: "gemini-3"),
    WindsurfModel(
        id: "sonnet-4.5", displayName: "Sonnet 4.5 (1M Context)", protobufId: "MODEL_SONNET_4_5",
        tier: "premium", family: "sonnet"),
    WindsurfModel(
        id: "gpt-5.1-codex", displayName: "GPT-5.1 Codex", protobufId: "MODEL_GPT_5_1_CODEX",
        tier: "premium", family: "gpt-5-codex"),
    WindsurfModel(
        id: "gpt-5.1-codex-mini", displayName: "GPT-5.1 Codex Mini",
        protobufId: "MODEL_GPT_5_1_CODEX_MINI", tier: "premium", family: "gpt-5-codex"),

    // Legacy/Standard Premium
    WindsurfModel(
        id: "gpt-4o", displayName: "GPT-4o (Windsurf Premium)", protobufId: "MODEL_GPT_4_O",
        tier: "premium", family: "gpt-4o"),
    WindsurfModel(
        id: "claude-3.5-sonnet", displayName: "Claude 3.5 Sonnet (Windsurf Premium)",
        protobufId: "MODEL_CLAUDE_3_5_SONNET", tier: "premium", family: "claude-3.5-sonnet"),
    WindsurfModel(
        id: "deepseek-v3", displayName: "DeepSeek V3", protobufId: "MODEL_DEEPSEEK_V3",
        tier: "free", family: "deepseek"),
    WindsurfModel(
        id: "deepseek-r1", displayName: "DeepSeek R1", protobufId: "MODEL_DEEPSEEK_R1",
        tier: "free", family: "deepseek"),
    WindsurfModel(
        id: "grok-code-fast-1", displayName: "Grok Code Fast 1",
        protobufId: "MODEL_GROK_CODE_FAST_1", tier: "free", family: "grok"),
    WindsurfModel(
        id: "kimi-k2.5", displayName: "Kimi k2.5", protobufId: "kimi-k2-5", tier: "free",
        family: "kimi"),
]

// MARK: - Language Server Detection

struct LSConnection {
    let port: Int
    let csrfToken: String
}

/// Detect running Windsurf language server port and CSRF token with retry logic.
func detectLanguageServer() -> LSConnection? {
    for attempt in 1...MAX_RETRY_ATTEMPTS {
        if attempt > 1 {
            fputs("log: [windsurf] LS detection retry \(attempt)/\(MAX_RETRY_ATTEMPTS)\n", stderr)
            Thread.sleep(forTimeInterval: RETRY_BASE_DELAY * Double(attempt - 1))
        }

        let psTask = Process()
        psTask.executableURL = URL(fileURLWithPath: "/bin/ps")
        psTask.arguments = ["aux"]
        let psPipe = Pipe()
        psTask.standardOutput = psPipe
        psTask.standardError = FileHandle.nullDevice

        var psOutput = ""
        do {
            try psTask.run()
            let outputData = psPipe.fileHandleForReading.readDataToEndOfFile()
            psTask.waitUntilExit()
            psOutput = String(data: outputData, encoding: .utf8) ?? ""
        } catch {
            fputs("log: [windsurf] ps aux failed (attempt \(attempt)): \(error)\n", stderr)
            continue
        }

        for line in psOutput.components(separatedBy: "\n") {
            if !line.contains("language_server") || line.contains("grep") {
                continue
            }
            // Prioritize Windsurf over Antigravity or others
            if !line.contains("Windsurf") && !line.contains("windsurf") {
                continue
            }

            // Ensure this is the Windsurf IDE's LS, not another editor's (like Antigravity/VSCode)
            guard line.contains("ide_name windsurf") || line.contains("Windsurf.app") else {
                continue
            }

            // Extract CSRF token
            var csrfToken = ""
            if let range = line.range(of: #"--csrf_token\s+(\S+)"#, options: .regularExpression) {
                let match = String(line[range])
                let parts = match.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
                if parts.count >= 2 {
                    csrfToken = parts[1]
                }
            }

            // Extract PID
            let lineParts = line.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
            guard lineParts.count >= 2 else { continue }
            let pid = lineParts[1]

            // Get listening port via lsof
            let lsofTask = Process()
            lsofTask.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
            lsofTask.arguments = ["-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", pid]
            let lsofPipe = Pipe()
            lsofTask.standardOutput = lsofPipe
            lsofTask.standardError = FileHandle.nullDevice

            var lsofOutput = ""
            do {
                try lsofTask.run()
                let outputData = lsofPipe.fileHandleForReading.readDataToEndOfFile()
                lsofTask.waitUntilExit()
                lsofOutput = String(data: outputData, encoding: .utf8) ?? ""
            } catch {
                continue
            }

            var port = 0
            for lsofLine in lsofOutput.components(separatedBy: "\n") {
                guard lsofLine.contains("LISTEN") else { continue }
                if let portRange = lsofLine.range(
                    of: #":(\d+)\s+\(LISTEN\)"#, options: .regularExpression)
                {
                    let portMatch = String(lsofLine[portRange])
                    let digits = portMatch.components(
                        separatedBy: CharacterSet.decimalDigits.inverted
                    )
                    .joined()
                    if let candidate = Int(digits), port == 0 || candidate < port {
                        port = candidate
                    }
                }
            }

            if port > 0 && !csrfToken.isEmpty {
                fputs("log: [windsurf] LS detected on port \(port) (attempt \(attempt))\n", stderr)
                return LSConnection(port: port, csrfToken: csrfToken)
            }

            break
        }
    }

    return nil
}

// MARK: - LS Communication

/// Quick heartbeat check to verify LS is responding.
func lsHeartbeat(connection: LSConnection) -> Bool {
    let url = URL(string: "http://127.0.0.1:\(connection.port)\(LS_HEARTBEAT)")!
    var request = URLRequest(url: url, timeoutInterval: HEARTBEAT_TIMEOUT)
    request.httpMethod = "POST"
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    request.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    request.httpBody = "{}".data(using: .utf8)

    let semaphore = DispatchSemaphore(value: 0)
    var success = false

    URLSession.shared.dataTask(with: request) { _, response, error in
        if error == nil, let httpResponse = response as? HTTPURLResponse,
            httpResponse.statusCode == 200
        {
            success = true
        }
        semaphore.signal()
    }.resume()

    _ = semaphore.wait(timeout: .now() + 5)
    return success
}

/// Build Connect streaming envelope: flags (1 byte) + length (4 bytes big-endian) + JSON data
func makeEnvelope(_ payload: [String: Any]) -> Data {
    guard let jsonData = try? JSONSerialization.data(withJSONObject: payload) else {
        return Data()
    }
    var envelope = Data()
    envelope.append(0x00)  // flags
    var length = UInt32(jsonData.count).bigEndian
    envelope.append(Data(bytes: &length, count: 4))
    envelope.append(jsonData)
    return envelope
}

/// Parse Connect-RPC streaming response frames.
/// Returns (resultText, errorMessage?)
func parseStreamingFrames(_ data: Data) -> (String, String?) {
    var resultText = ""
    var errorMsg: String? = nil
    var offset = 0

    while offset + 5 <= data.count {
        let flags = data[offset]
        let frameLen = Int(
            UInt32(
                bigEndian: data[offset + 1..<offset + 5].withUnsafeBytes {
                    $0.load(as: UInt32.self)
                }))
        let frameData = data[offset + 5..<min(offset + 5 + frameLen, data.count)]
        offset += 5 + frameLen

        guard let json = try? JSONSerialization.jsonObject(with: frameData) as? [String: Any] else {
            continue
        }

        if flags == 0x02 {  // Trailer
            if let err = json["error"] as? [String: Any] {
                let code = err["code"] as? String ?? "unknown"
                let message = err["message"] as? String ?? ""
                errorMsg = "\(code): \(message)"
            }
            continue
        }

        // Data frame
        if let dm = json["deltaMessage"] as? [String: Any] {
            if let isError = dm["isError"] as? Bool, isError {
                errorMsg = dm["text"] as? String ?? "unknown error"
            } else {
                resultText += dm["text"] as? String ?? ""
            }
        } else if let text = json["text"] as? String {
            resultText += text
        } else if let content = json["content"] as? String {
            resultText += content
        } else if let chatMsg = json["chatMessage"] as? [String: Any] {
            resultText += chatMsg["content"] as? String ?? ""
        }
    }

    return (resultText, errorMsg)
}

/// Build LS metadata dict for Connect-RPC requests
func buildLSMetadata(apiKey: String) -> [String: Any] {
    var metadata: [String: Any] = [
        "ideName": "windsurf",
        "ideVersion": IDE_VERSION,
        "extensionVersion": EXTENSION_VERSION,
        "locale": "en",
        "sessionId": "atlastrinity-mcp-\(ProcessInfo.processInfo.processIdentifier)",
        "requestId": String(Int(Date().timeIntervalSince1970)),
        "apiKey": apiKey,
    ]

    if let installId = ProcessInfo.processInfo.environment["WINDSURF_INSTALL_ID"] {
        metadata["installationId"] = installId
    }

    return metadata
}

/// Send chat request via LS RawGetChatMessage
func sendChat(connection: LSConnection, message: String, model: String, apiKey: String) async throws
    -> String
{
    let now = ISO8601DateFormatter().string(from: Date())
    let convId = UUID().uuidString

    let modelProtobufId = WINDSURF_MODELS.first { $0.id == model }?.protobufId ?? model

    let payload: [String: Any] = [
        "chatMessages": [
            [
                "messageId": UUID().uuidString,
                "source": 1,  // USER
                "timestamp": now,
                "conversationId": convId,
                "intent": ["generic": ["text": message]],
            ] as [String: Any]
        ],
        "metadata": buildLSMetadata(apiKey: apiKey),
        "chatModelName": modelProtobufId,
    ]

    let envelope = makeEnvelope(payload)

    let url = URL(string: "http://127.0.0.1:\(connection.port)\(LS_RAW_CHAT)")!
    var request = URLRequest(url: url, timeoutInterval: 300)
    request.httpMethod = "POST"
    request.setValue("application/connect+json", forHTTPHeaderField: "Content-Type")
    request.setValue("1", forHTTPHeaderField: "Connect-Protocol-Version")
    request.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    request.httpBody = envelope

    let (data, response) = try await URLSession.shared.data(for: request)

    guard let httpResponse = response as? HTTPURLResponse else {
        throw MCPError.internalError("Invalid response from Windsurf LS")
    }

    if httpResponse.statusCode != 200 {
        throw MCPError.internalError("Windsurf LS returned HTTP \(httpResponse.statusCode)")
    }

    let (resultText, errorMsg) = parseStreamingFrames(data)
    if let error = errorMsg {
        throw MCPError.internalError("Windsurf LS error: \(error)")
    }

    if resultText.isEmpty {
        return "[No response from Windsurf LS - model may be unavailable or rate-limited]"
    }

    return resultText
}

// MARK: - Active State

actor WindsurfState {
    var activeModel: String = "swe-1.5"
    var cachedConnection: LSConnection? = nil
    var lastCacheUpdate: Date = Date.distantPast
    var cacheValidDuration: TimeInterval = 300  // 5 minutes

    func setModel(_ model: String) {
        activeModel = model
    }

    func getModel() -> String {
        return activeModel
    }

    func getConnection() -> LSConnection? {
        // Check if cache is still valid
        if let conn = cachedConnection,
            Date().timeIntervalSince(lastCacheUpdate) < cacheValidDuration
        {
            return conn
        }
        return nil
    }

    func setConnection(_ conn: LSConnection?) {
        cachedConnection = conn
        lastCacheUpdate = Date()
    }

    func invalidateCache() {
        cachedConnection = nil
        lastCacheUpdate = Date.distantPast
    }

    /// Detect and cache LS connection, with heartbeat validation and caching
    func ensureConnection() -> LSConnection? {
        // First, try cached connection if still valid
        if let cached = getConnection(), lsHeartbeat(connection: cached) {
            return cached
        }

        // Cache miss or invalid - re-detect
        let startTime = Date()
        if let conn = detectLanguageServer() {
            let latency = Date().timeIntervalSince(startTime)
            let success = lsHeartbeat(connection: conn)

            // Record metrics
            Task {
                await healthMonitor.recordRequest(
                    success: success, latency: latency, type: "ls_detection")
            }

            if success {
                setConnection(conn)
                return conn
            }
        }

        // Detection failed
        let latency = Date().timeIntervalSince(startTime)
        Task {
            await healthMonitor.recordRequest(
                success: false, latency: latency, type: "ls_detection")
        }

        invalidateCache()
        return nil
    }
}

let state = WindsurfState()

// MARK: - Tool Schemas

let statusSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([:]),
])

let getModelsSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([
        "tier": .object([
            "type": .string("string"),
            "description": .string("Filter by tier: free, value, premium, or all (default: all)"),
        ])
    ]),
])

let chatSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([
        "message": .object([
            "type": .string("string"),
            "description": .string("Message to send to Windsurf AI"),
        ]),
        "model": .object([
            "type": .string("string"),
            "description": .string(
                "Model to use (default: active model). e.g., swe-1.5, deepseek-r1"),
        ]),
        "system_prompt": .object([
            "type": .string("string"),
            "description": .string("Optional system prompt to prepend"),
        ]),
        "stream": .object([
            "type": .string("boolean"),
            "description": .string("Enable streaming response (default: false)"),
        ]),
    ]),
    "required": .array([.string("message")]),
])

let cascadeSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([
        "message": .object([
            "type": .string("string"),
            "description": .string("Task description for Cascade to execute"),
        ]),
        "model": .object([
            "type": .string("string"),
            "description": .string("Model for Cascade (default: active model)"),
        ]),
    ]),
    "required": .array([.string("message")]),
])

let healthSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([:]),
])

let switchModelSchema: Value = .object([
    "type": .string("object"),
    "properties": .object([
        "model": .object([
            "type": .string("string"),
            "description": .string("Model ID to switch to (e.g., swe-1.5, deepseek-r1, kimi-k2.5)"),
        ])
    ]),
    "required": .array([.string("model")]),
])

// MARK: - Helper Functions

/// Validate Windsurf API key format
func validateAPIKey(_ apiKey: String) -> Bool {
    return apiKey.hasPrefix("sk-ws-") && apiKey.count > 20
}

func getRequiredString(from args: [String: Value]?, key: String) throws -> String {
    guard let val = args?[key]?.stringValue else {
        throw MCPError.invalidParams("Missing required argument: '\(key)'")
    }
    return val
}

func getOptionalString(from args: [String: Value]?, key: String) -> String? {
    return args?[key]?.stringValue
}

// MARK: - Tool Implementations

func handleHealthStatus() async -> String {
    let connection = await state.ensureConnection()
    let healthStatus = await healthMonitor.getHealthStatus()

    var result = """
        🌊 Windsurf MCP Bridge Status
        ═══════════════════════════════════════

        """

    if let conn = connection {
        result += """
            ✅ Windsurf IDE: CONNECTED
               Port: \(conn.port)
               Status: Language Server responding

            """
    } else {
        result += """
            ❌ Windsurf IDE: NOT DETECTED
               Ensure Windsurf is running on this machine.

            """
    }

    let activeModel = await state.getModel()
    result += """
        🤖 Active Model: \(activeModel)
        📦 Available Models: \(WINDSURF_MODELS.count)
        🔧 IDE Version: \(IDE_VERSION)
        📎 Extension: \(EXTENSION_VERSION)

        """

    // Add health monitoring status
    result += healthStatus

    return result
}

func handleGetModels(tier: String?) -> String {
    let filterTier = tier?.lowercased() ?? "all"

    let filtered =
        filterTier == "all"
        ? WINDSURF_MODELS
        : WINDSURF_MODELS.filter { $0.tier == filterTier }

    if filtered.isEmpty {
        return "No models found for tier: \(filterTier)"
    }

    var result = "🌊 Windsurf Models (tier: \(filterTier))\n"
    result += "═══════════════════════════════════════\n\n"

    for model in filtered {
        let tierEmoji: String
        switch model.tier {
        case "free": tierEmoji = "🆓"
        case "value": tierEmoji = "💎"
        case "premium": tierEmoji = "👑"
        default: tierEmoji = "❓"
        }

        result += "\(tierEmoji) \(model.displayName)\n"
        result += "   ID: \(model.id) | Family: \(model.family) | Proto: \(model.protobufId)\n\n"
    }

    return result
}

func handleChat(message: String, model: String?, systemPrompt: String?, stream: Bool?) async
    -> String
{
    let startTime = Date()
    let activeModel = await state.getModel()
    let useModel = model ?? activeModel
    let shouldStream = stream ?? false

    guard let connection = await state.ensureConnection() else {
        let latency = Date().timeIntervalSince(startTime)
        Task {
            await healthMonitor.recordRequest(success: false, latency: latency, type: "chat")
        }
        return "❌ Windsurf IDE not detected. Ensure Windsurf is running."
    }

    // Get API key from environment
    let apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"] ?? ""
    if apiKey.isEmpty {
        return "❌ WINDSURF_API_KEY not set. Set it in the environment."
    }

    if !validateAPIKey(apiKey) {
        return "❌ Invalid WINDSURF_API_KEY format. Expected format: sk-ws-..."
    }

    let fullMessage: String
    if let sys = systemPrompt {
        fullMessage = "[System: \(sys)]\n\n\(message)"
    } else {
        fullMessage = message
    }

    do {
        let response = try await sendChat(
            connection: connection,
            message: fullMessage,
            model: useModel,
            apiKey: apiKey
        )

        let latency = Date().timeIntervalSince(startTime)
        Task {
            await healthMonitor.recordRequest(success: true, latency: latency, type: "chat")
        }

        if shouldStream {
            // Simulate streaming by breaking response into chunks
            let chunkSize = max(1, response.count / 20)  // Split into ~20 chunks
            var streamedResponse = ""
            var index = 0

            while index < response.count {
                let endIndex = min(index + chunkSize, response.count)
                let chunk = String(
                    response[
                        response.index(
                            response.startIndex, offsetBy: index)..<response.index(
                                response.startIndex, offsetBy: endIndex)])
                streamedResponse += chunk

                if endIndex < response.count {
                    streamedResponse += "⏳\n"
                }
                index = endIndex
            }
            return """
                🌊 Windsurf Streaming Response (model: \(useModel))
                ───────────────────────────────────────
                \(streamedResponse)
                """
        } else {
            return """
                🌊 Windsurf Response (model: \(useModel))
                ───────────────────────────────────────
                \(response)
                """
        }
    } catch {
        let latency = Date().timeIntervalSince(startTime)
        Task {
            await healthMonitor.recordRequest(success: false, latency: latency, type: "chat")
        }
        return "❌ Chat error: \(error.localizedDescription)"
    }
}

// MARK: - Stream Buffering
actor StreamAccumulator {
    var data = Data()
    func append(_ d: Data) { data.append(d) }
    func totalCount() -> Int { data.count }
    func getData() -> Data { data }
}

func handleCascade(message: String, model: String?) async -> String {
    let activeModel = await state.getModel()
    let useModel = model ?? activeModel
    guard let connection = await state.ensureConnection() else {
        return "❌ Windsurf IDE not detected. Ensure Windsurf is running."
    }

    let apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"] ?? ""
    if apiKey.isEmpty { return "❌ WINDSURF_API_KEY not set." }

    // Map model name to internal UID
    let modelUid = {
        if let m = WINDSURF_MODELS.first(where: { $0.id == useModel }) { return m.protobufId }
        let map: [String: String] = [
            "swe-1.5": "MODEL_SWE_1_5",
            "deepseek-v3": "MODEL_DEEPSEEK_V3",
            "swe-1": "MODEL_SWE_1",
            "windsurf-fast": "MODEL_CHAT_11121",
        ]
        return map[useModel] ?? useModel
    }()

    // Gen Session ID
    let sessionId = "atlastrinity-mcp-\(getpid())-\(UUID().uuidString.prefix(8))"
    let meta = buildMetadataProto(apiKey: apiKey, sessionId: sessionId)

    // Helper: Send Proto Request
    func sendProto(_ endpoint: String, _ payload: Data) async throws -> Data {
        let url = URL(string: "http://127.0.0.1:\(connection.port)\(endpoint)")!
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = "POST"
        req.setValue("application/grpc", forHTTPHeaderField: "Content-Type")
        req.setValue("trailers", forHTTPHeaderField: "TE")
        req.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")

        // Envelope
        var env = Data()
        env.append(0)
        var len = UInt32(payload.count).bigEndian
        env.append(Data(bytes: &len, count: 4))
        env.append(payload)
        req.httpBody = env

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 else {
            throw MCPError.internalError("HTTP Error for \(endpoint)")
        }

        // Unwrap Envelope
        if data.count >= 5 {
            let len = UInt32(
                bigEndian: data.subdata(in: 1..<5).withUnsafeBytes { $0.load(as: UInt32.self) })
            if data.count >= 5 + Int(len) {
                return data.subdata(in: 5..<5 + Int(len))
            }
        }
        return Data()
    }

    do {
        // Step 1: StartCascade
        let startPayload = protoMsg(1, meta)
        let startResp = try await sendProto(LS_START_CASCADE, startPayload)

        guard let cascadeId = protoExtractString(startResp, 1), !cascadeId.isEmpty else {
            fputs(
                "log: [windsurf] Failed to start Cascade. Raw Resp (\(startResp.count) bytes): \(startResp.map { String(format: "%02x", $0) }.joined())\n",
                stderr)
            return "❌ Failed to start Cascade (No ID returned)"
        }
        fputs("log: [windsurf] Cascade started: \(cascadeId)\n", stderr)

        // Step 2: StreamCascadeReactiveUpdates (Background)
        let streamPayload = protoInt(1, 1) + protoStr(2, cascadeId)

        let streamUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_STREAM_CASCADE)")!
        var streamReq = URLRequest(url: streamUrl, timeoutInterval: CASCADE_TIMEOUT)
        streamReq.httpMethod = "POST"
        streamReq.setValue("application/grpc", forHTTPHeaderField: "Content-Type")
        streamReq.setValue("trailers", forHTTPHeaderField: "TE")
        streamReq.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")

        // Envelope
        var streamEnv = Data()
        streamEnv.append(0)
        var sLen = UInt32(streamPayload.count).bigEndian
        streamEnv.append(Data(bytes: &sLen, count: 4))
        streamEnv.append(streamPayload)
        streamReq.httpBody = streamEnv

        // Use streaming bytes
        let accumulator = StreamAccumulator()
        let streamTask = Task {
            do {
                if #available(macOS 12.0, *) {
                    let (bytes, resp) = try await URLSession.shared.bytes(for: streamReq)
                    guard let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 else {
                        fputs("log: [windsurf] Stream failed to start\n", stderr)
                        return
                    }
                    for try await byte in bytes {
                        await accumulator.append(Data([byte]))
                    }
                } else {
                    fputs("log: [windsurf] Streaming requires macOS 12+\n", stderr)
                }
            } catch {
                // Ignore cancellation
                let nsErr = error as NSError
                if nsErr.domain == NSURLErrorDomain && nsErr.code == NSURLErrorCancelled {
                    return
                }
                fputs("log: [windsurf] Stream finished/error: \(error)\n", stderr)
            }
        }

        try await Task.sleep(nanoseconds: 300_000_000)

        // Step 3: QueueCascadeMessage
        // Items is a repeated field of TextOrScopeItem (Field 3)
        // TextOrScopeItem: oneof chunk { f1: text, f2: scope }
        var itemsProto = Data()

        // 1. User Message Item
        var textItem = Data()
        textItem.append(protoStr(1, message))  // Text
        // Optional: intent (Field 2) inside text item?
        // Or is it field 2 of TextOrScopeItem?
        // Let's keep it consistent with the existing working pattern but add Scope.
        let intentInner = protoStr(1, message)
        let intentProto = protoMsg(1, intentInner)
        textItem.append(protoMsg(2, intentProto))  // intent
        textItem.append(protoInt(4, 1))  // submitted
        textItem.append(protoStr(15, UUID().uuidString))

        itemsProto.append(protoMsg(3, textItem))

        // 2. Scope Item (to provide workspace context)
        // Scope message: f1: path, f2: uri, f3: repoName, f4: repoUrl
        let currentPath = "/Users/dev/Documents/GitHub/atlastrinity"
        let currentUri = "file://" + currentPath

        var scopeMsg = Data()
        scopeMsg.append(protoStr(1, currentPath))
        scopeMsg.append(protoStr(2, currentUri))
        scopeMsg.append(protoStr(3, "solagurma/atlastrinity"))
        // repo_url might be used for git context
        scopeMsg.append(protoStr(4, "https://github.com/solagurma/atlastrinity.git"))

        var scopeItem = Data()
        scopeItem.append(protoMsg(2, scopeMsg))  // TextOrScopeItem.scope

        itemsProto.append(protoMsg(3, scopeItem))

        // Step 4: Cascade Config (Field 5)
        // PlannerConfig (Field 1): f34: plan_model, f35: requested_model
        // Adding potential ability/action triggers (Field numbers are experimental)
        var plannerProto = Data()
        plannerProto.append(protoStr(34, modelUid))
        plannerProto.append(protoStr(35, modelUid))

        // High-entropy guess: Field 11 or 12 might enable tool use/abilities
        plannerProto.append(protoInt(11, 1))
        plannerProto.append(protoInt(12, 1))

        let configProto = protoMsg(5, protoMsg(1, plannerProto))

        let queuePayload =
            protoMsg(1, meta) + protoStr(2, cascadeId) + itemsProto + configProto
            + protoInt(11, 1)  // Request submitted: true

        fputs(
            "log: [windsurf] Sending InterruptWithQueuedMessage (consolidated trigger)...\n", stderr
        )
        let _ = try await sendProto(LS_INTERRUPT_WITH_MESSAGE, queuePayload)

        // Step 5: Wait for response stability
        var lastCount = 0
        var stableTicks = 0
        // Wait up to 180s max
        for _ in 0..<180 {
            try await Task.sleep(nanoseconds: 1_000_000_000)
            let currentCount = await accumulator.totalCount()
            if currentCount > 0 && currentCount == lastCount {
                stableTicks += 1
                // Wait for 3 seconds of silence
                if stableTicks >= 3 { break }
            } else {
                stableTicks = 0
            }
            lastCount = currentCount
        }

        streamTask.cancel()
        let streamData = await accumulator.getData()
        fputs("log: [windsurf] Stream stable at \(streamData.count) bytes\n", stderr)

        // Parse gRPC Envelopes first
        var strings: [String] = []
        var offset = 0

        while offset + 5 <= streamData.count {
            // Read length (bytes 1-4)
            let lenData = streamData.subdata(in: offset + 1..<offset + 5)
            let len = Int(UInt32(bigEndian: lenData.withUnsafeBytes { $0.load(as: UInt32.self) }))

            if offset + 5 + len > streamData.count {
                break
            }

            let payload = streamData.subdata(in: offset + 5..<offset + 5 + len)
            let foundStrings = protoFindStrings(payload, minLen: 5)
            for s in foundStrings {
                fputs(
                    "log: [windsurf] Stream string (\(s.count) chars): \(s.prefix(100).replacingOccurrences(of: "\n", with: " "))\n",
                    stderr)
            }
            strings.append(contentsOf: foundStrings)

            offset += 5 + len
        }

        // Filter heuristic: remove system prompts and metadata
        let filtered = strings.filter {
            !$0.contains(cascadeId) && !$0.contains(modelUid)  // && !$0.contains(message)
                && !$0.contains(apiKey) && !$0.contains("windsurf")  // && !$0.contains("swe-1.5")
                && !$0.contains("CRITICAL:") && !$0.contains("IMPORTANT:")
                && !$0.contains("JSON FORMAT") && !$0.contains("WARNING:")
                && !$0.contains("jsonrpc") && !$0.contains("markdown_formatting")
                && !$0.contains("additional_guidelines")
                && !$0.contains("No acknowledgment phrases")
                && !$0.contains("Direct responses:") && !$0.contains("Be terse and direct")
                && !$0.contains("file:///") && !$0.contains("https://")
        }

        // Prefer the longest remaining string that looks like a natural response
        if let longest = filtered.max(by: { $0.count < $1.count }) {
            return """
                🌊 Cascade Response (\(useModel))
                ──────────────────────
                \(longest)
                """
        }
        return "❌ No response text found in stream. (Raw bytes: \(streamData.count))"

    } catch {
        return "❌ Cascade Error: \(error.localizedDescription)"
    }
}

func handleSwitchModel(model: String) async -> String {
    let available = WINDSURF_MODELS.map { $0.id }
    if !available.contains(model) {
        return """
            ❌ Unknown model: \(model)
            Available: \(available.joined(separator: ", "))
            """
    }

    await state.setModel(model)
    let tier = WINDSURF_MODELS.first { $0.id == model }?.tier ?? "unknown"
    return """
        ✅ Active model switched to: \(model)
        Tier: \(tier)
        All subsequent windsurf_chat and windsurf_cascade calls will use this model.
        """
}

// MARK: - Server Setup

func setupAndStartServer() async throws -> Server {
    fputs("log: Starting Windsurf MCP Bridge Server...\n", stderr)

    // Auto-detect LS on startup
    if let conn = detectLanguageServer() {
        if lsHeartbeat(connection: conn) {
            await state.setConnection(conn)
            fputs("log: [windsurf] IDE detected at port \(conn.port)\n", stderr)
        } else {
            fputs("log: [windsurf] IDE found but heartbeat failed\n", stderr)
        }
    } else {
        fputs("log: [windsurf] IDE not detected (will retry on tool calls)\n", stderr)
    }

    // Define tools
    let tools: [Tool] = [
        Tool(
            name: "windsurf_status",
            description: "Get Windsurf IDE connection status, active model, and server health",
            inputSchema: statusSchema
        ),
        Tool(
            name: "windsurf_health",
            description: "Get detailed health monitoring metrics and performance statistics",
            inputSchema: healthSchema
        ),
        Tool(
            name: "windsurf_get_models",
            description: "List all available Windsurf models with tier info (free/value/premium)",
            inputSchema: getModelsSchema
        ),
        Tool(
            name: "windsurf_chat",
            description:
                "Send a chat message to Windsurf AI via the local language server (uses Chat API quota)",
            inputSchema: chatSchema
        ),
        Tool(
            name: "windsurf_cascade",
            description:
                "Execute a Cascade flow in Windsurf (uses Cascade Actions quota). Best for complex multi-step tasks",
            inputSchema: cascadeSchema
        ),
        Tool(
            name: "windsurf_switch_model",
            description: "Switch the active Windsurf model for subsequent chat/cascade calls",
            inputSchema: switchModelSchema
        ),
    ]

    // Create server
    let server = Server(
        name: "mcp-server-windsurf",
        version: "1.0.0",
        capabilities: .init(
            prompts: nil,
            resources: nil,
            tools: .init(listChanged: false)
        )
    )

    // Register tools list handler
    await server.withMethodHandler(ListTools.self) { _ in
        return .init(tools: tools)
    }

    // Register tool call handler
    await server.withMethodHandler(CallTool.self) { params in
        let args = params.arguments

        do {
            let result: String
            switch params.name {
            case "windsurf_status":
                result = await handleHealthStatus()

            case "windsurf_health":
                result = await healthMonitor.getHealthStatus()

            case "windsurf_get_models":
                let tier = getOptionalString(from: args, key: "tier")
                result = handleGetModels(tier: tier)

            case "windsurf_chat":
                let message = try getRequiredString(from: args, key: "message")
                let model = getOptionalString(from: args, key: "model")
                let systemPrompt = getOptionalString(from: args, key: "system_prompt")
                let stream = getOptionalString(from: args, key: "stream").map {
                    $0.lowercased() == "true"
                }
                result = await handleChat(
                    message: message, model: model, systemPrompt: systemPrompt, stream: stream)

            case "windsurf_cascade":
                let message = try getRequiredString(from: args, key: "message")
                let model = getOptionalString(from: args, key: "model")
                result = await handleCascade(message: message, model: model)

            case "windsurf_switch_model":
                let model = try getRequiredString(from: args, key: "model")
                result = await handleSwitchModel(model: model)

            default:
                return .init(content: [.text("Unknown tool: \(params.name)")], isError: true)
            }

            return .init(content: [.text(result)], isError: false)

        } catch let error as MCPError {
            return .init(content: [.text("Error: \(error)")], isError: true)
        } catch {
            return .init(content: [.text("Error: \(error.localizedDescription)")], isError: true)
        }
    }

    // Start server with stdio transport
    let transport = StdioTransport()
    try await server.start(transport: transport)

    fputs("log: Windsurf MCP Bridge Server started successfully!\n", stderr)
    return server
}

// MARK: - Entry Point

@main
struct WindsurfMCPServer {
    static func main() async throws {
        let _ = try await setupAndStartServer()

        // Start graceful shutdown monitor in background
        Task {
            gracefulShutdown.waitForShutdown()
            exit(0)
        }

        // Keep running until terminated
        try await Task.sleep(nanoseconds: UInt64.max)
    }
}
