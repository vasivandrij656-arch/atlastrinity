import Foundation
import MCP

// MARK: - Configuration

/// Windsurf LS endpoints (Connect-RPC / HTTP)
let LS_RAW_CHAT = "/exa.language_server_pb.LanguageServerService/RawGetChatMessage"
let LS_HEARTBEAT = "/exa.language_server_pb.LanguageServerService/Heartbeat"
let LS_START_CASCADE = "/exa.language_server_pb.LanguageServerService/StartCascade"
let LS_STREAM_CASCADE = "/exa.language_server_pb.LanguageServerService/StreamCascadeReactiveUpdates"
let LS_QUEUE_CASCADE = "/exa.language_server_pb.LanguageServerService/QueueCascadeMessage"
let LS_INTERRUPT_CASCADE =
    "/exa.language_server_pb.LanguageServerService/InterruptWithQueuedMessage"

/// Default IDE metadata
let IDE_VERSION = "1.9552.21"
let EXTENSION_VERSION = "1.48.2"

/// Cascade timeout in seconds
let CASCADE_TIMEOUT: TimeInterval = 90

// MARK: - Windsurf Models

struct WindsurfModel {
    let id: String
    let displayName: String
    let protobufId: String
    let tier: String  // "free", "value", "premium"
    let family: String
}

let WINDSURF_MODELS: [WindsurfModel] = [
    WindsurfModel(
        id: "swe-1.5", displayName: "SWE-1.5", protobufId: "MODEL_SWE_1_5", tier: "free",
        family: "swe"),
    WindsurfModel(
        id: "swe-1", displayName: "SWE-1", protobufId: "MODEL_SWE_1", tier: "free", family: "swe"),
    WindsurfModel(
        id: "deepseek-r1", displayName: "DeepSeek R1", protobufId: "MODEL_DEEPSEEK_R1",
        tier: "free", family: "deepseek"),
    WindsurfModel(
        id: "deepseek-v3", displayName: "DeepSeek V3", protobufId: "MODEL_DEEPSEEK_V3",
        tier: "free", family: "deepseek"),
    WindsurfModel(
        id: "grok-code-fast-1", displayName: "Grok Code Fast 1",
        protobufId: "MODEL_GROK_CODE_FAST_1", tier: "free", family: "grok"),
    WindsurfModel(
        id: "kimi-k2.5", displayName: "Kimi k2.5", protobufId: "kimi-k2-5", tier: "free",
        family: "kimi"),
    WindsurfModel(
        id: "windsurf-fast", displayName: "Windsurf Fast", protobufId: "MODEL_CHAT_11121",
        tier: "free", family: "windsurf"),
]

// MARK: - Language Server Detection

struct LSConnection {
    let port: Int
    let csrfToken: String
}

/// Detect running Windsurf language server port and CSRF token.
func detectLanguageServer() -> LSConnection? {
    let psTask = Process()
    psTask.executableURL = URL(fileURLWithPath: "/bin/ps")
    psTask.arguments = ["aux"]
    let psPipe = Pipe()
    psTask.standardOutput = psPipe
    psTask.standardError = FileHandle.nullDevice

    do {
        try psTask.run()
        psTask.waitUntilExit()
    } catch {
        fputs("log: [windsurf] ps aux failed: \(error)\n", stderr)
        return nil
    }

    let psOutput =
        String(data: psPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""

    for line in psOutput.components(separatedBy: "\n") {
        guard line.contains("language_server_macos_arm"), !line.contains("grep") else { continue }

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

        do {
            try lsofTask.run()
            lsofTask.waitUntilExit()
        } catch {
            continue
        }

        let lsofOutput =
            String(data: lsofPipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""

        var port = 0
        for lsofLine in lsofOutput.components(separatedBy: "\n") {
            guard lsofLine.contains("LISTEN") else { continue }
            if let portRange = lsofLine.range(
                of: #":(\d+)\s+\(LISTEN\)"#, options: .regularExpression)
            {
                let portMatch = String(lsofLine[portRange])
                let digits = portMatch.components(separatedBy: CharacterSet.decimalDigits.inverted)
                    .joined()
                if let candidate = Int(digits), port == 0 || candidate < port {
                    port = candidate
                }
            }
        }

        if port > 0 && !csrfToken.isEmpty {
            return LSConnection(port: port, csrfToken: csrfToken)
        }

        break
    }

    return nil
}

// MARK: - LS Communication

/// Quick heartbeat check to verify LS is responding.
func lsHeartbeat(connection: LSConnection) -> Bool {
    let url = URL(string: "http://127.0.0.1:\(connection.port)\(LS_HEARTBEAT)")!
    var request = URLRequest(url: url, timeoutInterval: 3)
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
    return [
        "ideName": "windsurf",
        "ideVersion": IDE_VERSION,
        "extensionVersion": EXTENSION_VERSION,
        "locale": "en",
        "sessionId": "atlastrinity-mcp-\(ProcessInfo.processInfo.processIdentifier)",
        "requestId": String(Int(Date().timeIntervalSince1970)),
        "apiKey": apiKey,
    ]
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

    func setModel(_ model: String) {
        activeModel = model
    }

    func getModel() -> String {
        return activeModel
    }

    func getConnection() -> LSConnection? {
        return cachedConnection
    }

    func setConnection(_ conn: LSConnection?) {
        cachedConnection = conn
    }

    /// Detect and cache LS connection, with heartbeat validation
    func ensureConnection() -> LSConnection? {
        if let conn = cachedConnection, lsHeartbeat(connection: conn) {
            return conn
        }
        // Re-detect
        if let conn = detectLanguageServer(), lsHeartbeat(connection: conn) {
            cachedConnection = conn
            return conn
        }
        cachedConnection = nil
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

func handleStatus() async -> String {
    let connection = await state.ensureConnection()
    let activeModel = await state.getModel()

    var result = """
        🌊 Windsurf MCP Bridge Status
        ═══════════════════════════════════════

        """

    if let conn = connection {
        result += """
            ✅ Windsurf IDE: CONNECTED
               Port: \(conn.port)
               CSRF: \(String(conn.csrfToken.prefix(8)))...

            """
    } else {
        result += """
            ❌ Windsurf IDE: NOT DETECTED
               Ensure Windsurf is running on this machine.

            """
    }

    result += """
        🤖 Active Model: \(activeModel)
        📦 Available Models: \(WINDSURF_MODELS.count)
        🔧 IDE Version: \(IDE_VERSION)
        📎 Extension: \(EXTENSION_VERSION)
        """

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

func handleChat(message: String, model: String?, systemPrompt: String?) async -> String {
    let activeModel = await state.getModel()
    let useModel = model ?? activeModel
    guard let connection = await state.ensureConnection() else {
        return "❌ Windsurf IDE not detected. Ensure Windsurf is running."
    }

    // Get API key from environment
    let apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"] ?? ""
    if apiKey.isEmpty {
        return "❌ WINDSURF_API_KEY not set. Set it in the environment."
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
        return """
            🌊 Windsurf Response (model: \(useModel))
            ───────────────────────────────────────
            \(response)
            """
    } catch {
        return "❌ Chat error: \(error.localizedDescription)"
    }
}

func handleCascade(message: String, model: String?) async -> String {
    let activeModel = await state.getModel()
    let useModel = model ?? activeModel
    guard let connection = await state.ensureConnection() else {
        return "❌ Windsurf IDE not detected. Ensure Windsurf is running."
    }

    let apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"] ?? ""
    if apiKey.isEmpty {
        return "❌ WINDSURF_API_KEY not set."
    }

    let modelProtobufId = WINDSURF_MODELS.first { $0.id == useModel }?.protobufId ?? useModel

    // Step 1: StartCascade
    let startPayload: [String: Any] = [
        "metadata": buildLSMetadata(apiKey: apiKey)
    ]
    let startEnvelope = makeEnvelope(startPayload)

    let startUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_START_CASCADE)")!
    var startRequest = URLRequest(url: startUrl, timeoutInterval: 30)
    startRequest.httpMethod = "POST"
    startRequest.setValue("application/connect+json", forHTTPHeaderField: "Content-Type")
    startRequest.setValue("1", forHTTPHeaderField: "Connect-Protocol-Version")
    startRequest.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    startRequest.httpBody = startEnvelope

    var cascadeId: String = ""

    do {
        let (startData, _) = try await URLSession.shared.data(for: startRequest)
        // Parse cascadeId from response
        if let json = try? JSONSerialization.jsonObject(with: startData) as? [String: Any] {
            cascadeId = json["cascadeId"] as? String ?? ""
        }
        // Try parsing from streaming frames
        if cascadeId.isEmpty {
            let (text, _) = parseStreamingFrames(startData)
            if let data = text.data(using: .utf8),
                let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            {
                cascadeId = json["cascadeId"] as? String ?? ""
            }
        }
    } catch {
        return "❌ Failed to start Cascade: \(error.localizedDescription)"
    }

    if cascadeId.isEmpty {
        cascadeId = UUID().uuidString
        fputs("log: [windsurf] Using generated cascadeId\n", stderr)
    }

    fputs("log: [windsurf] Cascade started: \(cascadeId)\n", stderr)

    // Step 2: Stream reactive updates (background listener)
    let streamUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_STREAM_CASCADE)")!
    let streamPayload: [String: Any] = [
        "metadata": buildLSMetadata(apiKey: apiKey),
        "cascadeId": cascadeId,
        "protocolVersion": 1,
    ]
    let streamEnvelope = makeEnvelope(streamPayload)

    var streamRequest = URLRequest(url: streamUrl, timeoutInterval: CASCADE_TIMEOUT)
    streamRequest.httpMethod = "POST"
    streamRequest.setValue("application/connect+json", forHTTPHeaderField: "Content-Type")
    streamRequest.setValue("1", forHTTPHeaderField: "Connect-Protocol-Version")
    streamRequest.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    streamRequest.httpBody = streamEnvelope

    // Start stream in background, collect response
    let streamTask = Task<Data, Error> {
        let (data, _) = try await URLSession.shared.data(for: streamRequest)
        return data
    }

    // Step 3: Queue message
    try? await Task.sleep(nanoseconds: 500_000_000)  // 0.5s delay for stream setup

    let queueUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_QUEUE_CASCADE)")!
    let queuePayload: [String: Any] = [
        "metadata": buildLSMetadata(apiKey: apiKey),
        "cascadeId": cascadeId,
        "items": [
            [
                "humanMessage": [
                    "text": message
                ]
            ] as [String: Any]
        ],
        "cascadeConfig": [
            "model": modelProtobufId
        ] as [String: Any],
    ]
    let queueEnvelope = makeEnvelope(queuePayload)

    var queueRequest = URLRequest(url: queueUrl, timeoutInterval: 30)
    queueRequest.httpMethod = "POST"
    queueRequest.setValue("application/connect+json", forHTTPHeaderField: "Content-Type")
    queueRequest.setValue("1", forHTTPHeaderField: "Connect-Protocol-Version")
    queueRequest.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    queueRequest.httpBody = queueEnvelope

    do {
        let (_, _) = try await URLSession.shared.data(for: queueRequest)
    } catch {
        streamTask.cancel()
        return "❌ Failed to queue Cascade message: \(error.localizedDescription)"
    }

    // Step 4: Trigger processing
    let interruptUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_INTERRUPT_CASCADE)")!
    let interruptPayload: [String: Any] = [
        "metadata": buildLSMetadata(apiKey: apiKey),
        "cascadeId": cascadeId,
    ]
    let interruptEnvelope = makeEnvelope(interruptPayload)

    var interruptRequest = URLRequest(url: interruptUrl, timeoutInterval: 30)
    interruptRequest.httpMethod = "POST"
    interruptRequest.setValue("application/connect+json", forHTTPHeaderField: "Content-Type")
    interruptRequest.setValue("1", forHTTPHeaderField: "Connect-Protocol-Version")
    interruptRequest.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
    interruptRequest.httpBody = interruptEnvelope

    do {
        let (_, _) = try await URLSession.shared.data(for: interruptRequest)
    } catch {
        fputs("log: [windsurf] Interrupt failed (non-fatal): \(error)\n", stderr)
    }

    // Step 5: Collect response from stream
    do {
        let streamData = try await streamTask.value
        let (responseText, errorMsg) = parseStreamingFrames(streamData)

        if let err = errorMsg {
            return """
                ❌ Cascade Error
                ───────────────────
                \(err)
                """
        }

        if responseText.isEmpty {
            return """
                ⚠️ Cascade completed but returned no text.
                This may indicate: rate limit, model unavailable, or empty response.
                CascadeId: \(cascadeId)
                """
        }

        return """
            🌊 Windsurf Cascade Response (model: \(useModel))
            ═══════════════════════════════════════════════════
            \(responseText)
            """
    } catch {
        return "❌ Cascade stream error: \(error.localizedDescription)"
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
                result = await handleStatus()

            case "windsurf_get_models":
                let tier = getOptionalString(from: args, key: "tier")
                result = handleGetModels(tier: tier)

            case "windsurf_chat":
                let message = try getRequiredString(from: args, key: "message")
                let model = getOptionalString(from: args, key: "model")
                let systemPrompt = getOptionalString(from: args, key: "system_prompt")
                result = await handleChat(
                    message: message, model: model, systemPrompt: systemPrompt)

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

        // Keep running until terminated
        await withCheckedContinuation { (_: CheckedContinuation<Void, Never>) in
            // Server runs indefinitely via stdio
        }
    }
}
