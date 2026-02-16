import Foundation
import Dispatch

/// Real-time streaming support for Cascade responses
class CascadeStreamer {
    private let connection: LSConnection
    private let apiKey: String
    private var streamTask: Task<Void, Never>?
    private let eventHandler: (StreamEvent) -> Void
    private let queue = DispatchQueue(label: "cascade.streamer", qos: .userInitiated)
    
    enum StreamEvent {
        case start(cascadeId: String)
        case chunk(content: String, isDelta: Bool)
        case fileOperation(operation: FileOperation)
        case progress(progress: Float, stage: String)
        case complete(result: CascadeResult)
        case error(error: String)
    }
    
    struct FileOperation {
        let type: OperationType
        let path: String
        let content: String?
        let timestamp: Date
        
        enum OperationType {
            case create
            case modify
            case delete
            case rename
        }
    }
    
    struct CascadeResult {
        let cascadeId: String
        let success: Bool
        let response: String
        let fileOperations: [FileOperation]
        let duration: TimeInterval
        let metadata: [String: Any]
    }
    
    init(connection: LSConnection, apiKey: String, eventHandler: @escaping (StreamEvent) -> Void) {
        self.connection = connection
        self.apiKey = apiKey
        self.eventHandler = eventHandler
    }
    
    deinit {
        stopStreaming()
    }
    
    /// Start streaming Cascade execution with real-time updates
    func startStreaming(message: String, model: String) async throws -> String {
        // Start Cascade
        let sessionId = "streaming-\(UUID().uuidString.prefix(8))"
        let meta = buildMetadataProto(apiKey: apiKey, sessionId: sessionId)
        
        let startPayload = protoMsg(1, meta)
        let startResp = try await sendProto(LS_START_CASCADE, startPayload)
        
        guard let cascadeId = protoExtractString(startResp, 1), !cascadeId.isEmpty else {
            throw StreamError.failedToStartCascade
        }
        
        // Notify start
        DispatchQueue.main.async {
            self.eventHandler(.start(cascadeId: cascadeId))
        }
        
        // Start background streaming
        streamTask = Task {
            await handleStreaming(cascadeId: cascadeId, message: message, model: model)
        }
        
        return cascadeId
    }
    
    private func handleStreaming(cascadeId: String, message: String, model: String) async {
        let startTime = Date()
        var fileOperations: [FileOperation] = []
        var accumulatedContent = ""
        
        do {
            // Start stream monitoring
            let streamPayload = protoInt(1, 1) + protoStr(2, cascadeId)
            
            let streamUrl = URL(string: "http://127.0.0.1:\(connection.port)\(LS_STREAM_CASCADE)")!
            var streamReq = URLRequest(url: streamUrl, timeoutInterval: 300)
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
            
            if #available(macOS 12.0, *) {
                let (bytes, resp) = try await URLSession.shared.bytes(for: streamReq)
                guard let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 else {
                    throw StreamError.failedToStartStream
                }
                
                var lastProgress: Float = 0.0
                var currentStage = "Initializing"
                
                for try await byte in bytes {
                    await accumulator.append(Data([byte]))
                    
                    // Parse accumulated data for real-time updates
                    let currentData = await accumulator.getData()
                    if let updates = parseStreamUpdates(currentData, previousData: accumulatedContent) {
                        for update in updates {
                            switch update {
                            case .content(let content, let isDelta):
                                accumulatedContent += content
                                DispatchQueue.main.async {
                                    self.eventHandler(.chunk(content: content, isDelta: isDelta))
                                }
                                
                                // Update progress based on content patterns
                                let newProgress = calculateProgress(from: accumulatedContent)
                                if newProgress > lastProgress {
                                    lastProgress = newProgress
                                    currentStage = inferStage(from: accumulatedContent)
                                    DispatchQueue.main.async {
                                        self.eventHandler(.progress(progress: newProgress, stage: currentStage))
                                    }
                                }
                                
                            case .fileOperation(let operation):
                                fileOperations.append(operation)
                                DispatchQueue.main.async {
                                    self.eventHandler(.fileOperation(operation: operation))
                                }
                            }
                        }
                    }
                    
                    // Check for completion
                    if isStreamComplete(currentData) {
                        break
                    }
                }
            } else {
                throw StreamError.unsupportedPlatform
            }
            
            // Send the actual message
            try await sendCascadeMessage(cascadeId: cascadeId, message: message, model: model)
            
            // Wait for completion
            try await Task.sleep(nanoseconds: 2_000_000_000)
            
            let finalData = await accumulator.getData()
            let finalResponse = extractFinalResponse(from: finalData)
            let duration = Date().timeIntervalSince(startTime)
            
            let result = CascadeResult(
                cascadeId: cascadeId,
                success: !finalResponse.isEmpty,
                response: finalResponse,
                fileOperations: fileOperations,
                duration: duration,
                metadata: [
                    "model": model,
                    "messageLength": message.count,
                    "responseLength": finalResponse.count,
                    "fileOperationsCount": fileOperations.count
                ]
            )
            
            DispatchQueue.main.async {
                self.eventHandler(.complete(result: result))
            }
            
        } catch {
            DispatchQueue.main.async {
                self.eventHandler(.error(error: error.localizedDescription))
            }
        }
    }
    
    private func sendCascadeMessage(cascadeId: String, message: String, model: String) async throws {
        let sessionId = "streaming-\(UUID().uuidString.prefix(8))"
        let meta = buildMetadataProto(apiKey: apiKey, sessionId: sessionId)
        
        // Build message items
        var itemsProto = Data()
        var textItem = Data()
        textItem.append(protoStr(1, message))
        textItem.append(protoInt(4, 1))
        textItem.append(protoStr(15, UUID().uuidString))
        itemsProto.append(protoMsg(3, textItem))
        
        // Add workspace scope
        let scopeMsg = WorkspaceManager.shared.enhanceScopeForCurrentWorkspace()
        var scopeItem = Data()
        scopeItem.append(protoMsg(2, scopeMsg))
        itemsProto.append(protoMsg(3, scopeItem))
        
        // Build config
        let modelUid = WINDSURF_MODELS.first { $0.id == model }?.protobufId ?? model
        var plannerProto = Data()
        plannerProto.append(protoStr(34, modelUid))
        plannerProto.append(protoStr(35, modelUid))
        plannerProto.append(protoInt(11, 1))  // enable_cortex_reasoning
        plannerProto.append(protoInt(12, 1))  // enable_action_phase
        plannerProto.append(protoInt(13, 1))  // enable_tool_execution
        plannerProto.append(protoInt(14, 1))  // enable_file_operations
        plannerProto.append(protoInt(15, 1))  // enable_autonomous_execution
        
        let configProto = protoMsg(5, protoMsg(1, plannerProto))
        
        let queuePayload = protoMsg(1, meta) + protoStr(2, cascadeId) + itemsProto + configProto + protoInt(11, 1)
        let _ = try await sendProto(LS_INTERRUPT_WITH_MESSAGE, queuePayload)
    }
    
    private func parseStreamUpdates(_ data: Data, previousData: String) -> [StreamUpdate]? {
        // Parse gRPC envelopes and look for streaming updates
        var updates: [StreamUpdate] = []
        var offset = 0
        
        while offset + 5 <= data.count {
            let lenData = data.subdata(in: offset + 1..<offset + 5)
            let len = Int(UInt32(bigEndian: lenData.withUnsafeBytes { $0.load(as: UInt32.self) }))
            
            if offset + 5 + len > data.count {
                break
            }
            
            let payload = data.subdata(in: offset + 5..<offset + 5 + len)
            
            // Look for content updates
            if let content = extractContentFromPayload(payload) {
                let isNewContent = !previousData.contains(content)
                updates.append(.content(content: content, isDelta: isNewContent))
            }
            
            // Look for file operation indicators
            if let fileOp = extractFileOperationFromPayload(payload) {
                updates.append(.fileOperation(operation: fileOp))
            }
            
            offset += 5 + len
        }
        
        return updates.isEmpty ? nil : updates
    }
    
    private func extractContentFromPayload(_ payload: Data) -> String? {
        let strings = protoFindStrings(payload, minLen: 10)
        
        // Look for meaningful content (not system messages)
        for string in strings {
            if !string.contains("cascadeId") && 
               !string.contains("windsurf") && 
               !string.contains("CRITICAL") &&
               string.count > 20 {
                return string
            }
        }
        return nil
    }
    
    private func extractFileOperationFromPayload(_ payload: Data) -> FileOperation? {
        let strings = protoFindStrings(payload, minLen: 5)
        
        // Look for file operation signatures
        for string in strings {
            if string.lowercased().contains("created") {
                return FileOperation(
                    type: .create,
                    path: extractFilePath(from: string) ?? "unknown",
                    content: nil,
                    timestamp: Date()
                )
            } else if string.lowercased().contains("modified") {
                return FileOperation(
                    type: .modify,
                    path: extractFilePath(from: string) ?? "unknown",
                    content: nil,
                    timestamp: Date()
                )
            }
        }
        return nil
    }
    
    private func extractFilePath(from string: String) -> String? {
        // Extract file path from operation message
        let patterns = [
            #"(?:created|modified|deleted)\s+([^\s]+)"#,
            #"file\s+([^\s]+)"#,
            #"([^\s]+\.(py|js|ts|json|md|txt))"#
        ]
        
        for pattern in patterns {
            if let range = string.range(of: pattern, options: .regularExpression) {
                let match = String(string[range])
                let components = match.components(separatedBy: .whitespaces)
                return components.last
            }
        }
        return nil
    }
    
    private func calculateProgress(from content: String) -> Float {
        // Simple heuristic based on content patterns
        let totalPatterns = [
            "analyzing", "planning", "creating", "implementing", "testing", "finalizing"
        ]
        
        var completedPatterns = 0
        for pattern in totalPatterns {
            if content.lowercased().contains(pattern) {
                completedPatterns += 1
            }
        }
        
        return Float(completedPatterns) / Float(totalPatterns.count)
    }
    
    private func inferStage(from content: String) -> String {
        let stages = [
            ("analyzing", "Analyzing requirements"),
            ("planning", "Planning approach"),
            ("creating", "Creating files"),
            ("implementing", "Implementing solution"),
            ("testing", "Testing implementation"),
            ("finalizing", "Finalizing results")
        ]
        
        for (keyword, stage) in stages {
            if content.lowercased().contains(keyword) {
                return stage
            }
        }
        
        return "Processing"
    }
    
    private func isStreamComplete(_ data: Data) -> Bool {
        // Check for completion indicators in the stream
        let strings = protoFindStrings(data, minLen: 5)
        
        for string in strings {
            if string.lowercased().contains("complete") ||
               string.lowercased().contains("finished") ||
               string.lowercased().contains("done") {
                return true
            }
        }
        
        return false
    }
    
    private func extractFinalResponse(from data: Data) -> String {
        let strings = protoFindStrings(data, minLen: 20)
        
        // Filter and find the best response
        let filtered = strings.filter {
            !$0.contains("cascadeId") && 
            !$0.contains("windsurf") && 
            !$0.contains("CRITICAL") &&
            !$0.contains("IMPORTANT") &&
            $0.count > 50
        }
        
        return filtered.max(by: { $0.count < $1.count }) ?? ""
    }
    
    func stopStreaming() {
        streamTask?.cancel()
        streamTask = nil
    }
    
    // MARK: - Helper Methods
    
    private func sendProto(_ endpoint: String, _ payload: Data) async throws -> Data {
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
            throw NSError(domain: "CascadeStreamer", code: 1, userInfo: [NSLocalizedDescriptionKey: "HTTP Error"])
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
    
    enum StreamError: Error {
        case failedToStartCascade
        case failedToStartStream
        case unsupportedPlatform
    }
}

// MARK: - Stream Update Types

enum StreamUpdate {
    case content(content: String, isDelta: Bool)
    case fileOperation(operation: CascadeStreamer.FileOperation)
}

// MARK: - Stream Accumulator (from main.swift)

actor StreamAccumulator {
    var data = Data()
    func append(_ d: Data) { data.append(d) }
    func totalCount() -> Int { data.count }
    func getData() -> Data { data }
}
