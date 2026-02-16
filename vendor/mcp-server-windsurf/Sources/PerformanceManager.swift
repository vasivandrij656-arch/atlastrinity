import Dispatch
import Foundation

/// Advanced caching and performance optimization system
final class PerformanceManager: @unchecked Sendable {
    static let shared = PerformanceManager()

    private var responseCache: [String: CachedResponse] = [:]
    private var connectionPool: [LSConnection] = []
    private var requestQueue: DispatchQueue
    private var cacheQueue: DispatchQueue
    private let maxCacheSize = 100
    private let cacheExpirationTime: TimeInterval = 300  // 5 minutes

    private init() {
        self.requestQueue = DispatchQueue(label: "performance.requests", qos: .userInitiated)
        self.cacheQueue = DispatchQueue(label: "performance.cache", qos: .utility)
    }

    // MARK: - Response Caching

    struct CachedResponse {
        let response: String
        var timestamp: Date
        let model: String
        let messageType: MessageType
        let hash: String

        var isExpired: Bool {
            Date().timeIntervalSince(timestamp) > 300  // 5 minutes
        }

        enum MessageType {
            case chat
            case cascade
            case status
        }
    }

    /// Get cached response if available and not expired
    func getCachedResponse(for key: String, model: String, type: CachedResponse.MessageType)
        -> String?
    {
        return cacheQueue.sync { () -> String? in
            guard var cached = responseCache[key],
                !cached.isExpired,
                cached.model == model,
                cached.messageType == type
            else {
                return nil
            }

            // Update access time
            cached.timestamp = Date()
            responseCache[key] = cached
            return cached.response
        }
    }

    /// Cache a response with intelligent key generation
    func cacheResponse(
        _ response: String, for request: String, model: String, type: CachedResponse.MessageType
    ) {
        cacheQueue.async {
            let key = self.generateCacheKey(for: request, model: model, type: type)
            let hash = self.calculateHash(for: request + model + type.hashValue.description)

            // Remove old entries if cache is full
            if self.responseCache.count >= self.maxCacheSize {
                self.evictOldestEntries()
            }

            let cached = CachedResponse(
                response: response,
                timestamp: Date(),
                model: model,
                messageType: type,
                hash: hash
            )

            self.responseCache[key] = cached
        }
    }

    private func generateCacheKey(
        for request: String, model: String, type: CachedResponse.MessageType
    ) -> String {
        // Normalize request for better cache hits
        let normalizedRequest =
            request
            .lowercased()
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)

        return "\(type.hashValue)_\(model)_\(calculateHash(for: normalizedRequest))"
    }

    private func calculateHash(for input: String) -> String {
        return String(input.hashValue, radix: 16)
    }

    private func evictOldestEntries() {
        let sortedEntries = responseCache.sorted { $0.value.timestamp < $1.value.timestamp }
        let entriesToRemove = sortedEntries.prefix(maxCacheSize / 4)  // Remove 25%

        for (key, _) in entriesToRemove {
            responseCache.removeValue(forKey: key)
        }
    }

    // MARK: - Connection Pooling

    /// Get or create a connection from the pool
    func getOptimizedConnection() async -> LSConnection? {
        return await withCheckedContinuation { continuation in
            requestQueue.async {
                // Try to reuse existing connection
                if let connection = self.connectionPool.first,
                    self.isConnectionHealthy(connection)
                {
                    continuation.resume(returning: connection)
                    return
                }

                // Create new connection
                Task {
                    if let newConnection = await self.detectAndValidateConnection() {
                        self.connectionPool.append(newConnection)
                        // Keep pool size manageable
                        if self.connectionPool.count > 3 {
                            self.connectionPool.removeFirst()
                        }
                        continuation.resume(returning: newConnection)
                    } else {
                        continuation.resume(returning: nil)
                    }
                }
            }
        }
    }

    private func isConnectionHealthy(_ connection: LSConnection) -> Bool {
        // Quick health check
        let url = URL(string: "http://127.0.0.1:\(connection.port)\(LS_HEARTBEAT)")!
        var request = URLRequest(url: url, timeoutInterval: 2)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")
        request.httpBody = "{}".data(using: .utf8)

        let semaphore = DispatchSemaphore(value: 0)
        var isHealthy = false

        URLSession.shared.dataTask(with: request) { _, response, error in
            if error == nil,
                let httpResponse = response as? HTTPURLResponse,
                httpResponse.statusCode == 200
            {
                isHealthy = true
            }
            semaphore.signal()
        }.resume()

        semaphore.wait()
        return isHealthy
    }

    private func detectAndValidateConnection() async -> LSConnection? {
        // Use existing detection logic
        guard let connection = detectLanguageServer() else { return nil }

        // Validate with heartbeat
        if lsHeartbeat(connection: connection) {
            return connection
        }

        return nil
    }

    // MARK: - Request Optimization

    /// Optimize request for better performance
    func optimizeRequest(_ message: String, model: String) -> OptimizedRequest {
        let optimizedMessage = optimizeMessage(message)
        let optimizedModel = optimizeModelSelection(model, for: optimizedMessage)

        return OptimizedRequest(
            message: optimizedMessage,
            model: optimizedModel,
            priority: calculatePriority(for: optimizedMessage),
            estimatedTokens: estimateTokens(optimizedMessage),
            cacheKey: generateCacheKey(for: optimizedMessage, model: optimizedModel, type: .chat)
        )
    }

    struct OptimizedRequest {
        let message: String
        let model: String
        let priority: Priority
        let estimatedTokens: Int
        let cacheKey: String

        enum Priority {
            case low, medium, high, critical
        }
    }

    private func optimizeMessage(_ message: String) -> String {
        var optimized = message

        // Remove redundant whitespace
        optimized = optimized.replacingOccurrences(
            of: "\\s+", with: " ", options: .regularExpression)

        // Remove common filler phrases
        let fillerPhrases = [
            "please",
            "could you",
            "would you",
            "i would like you to",
            "i need you to",
        ]

        for phrase in fillerPhrases {
            optimized = optimized.replacingOccurrences(
                of: "\\b\(phrase)\\b", with: "", options: [.regularExpression, .caseInsensitive])
            optimized = optimized.trimmingCharacters(in: .whitespaces)
        }

        // Ensure minimum length for meaningful requests
        if optimized.count < 10 {
            return message
        }

        return optimized
    }

    private func optimizeModelSelection(_ model: String, for message: String) -> String {
        // Smart model selection based on request complexity
        let complexity = calculateComplexity(message)

        switch complexity {
        case .low:
            return "windsurf-fast"  // Use fast model for simple requests
        case .medium:
            return model  // Use requested model
        case .high:
            return "swe-1.5"  // Use capable model for complex requests
        }
    }

    private func calculateComplexity(_ message: String) -> RequestComplexity {
        let wordCount = message.components(separatedBy: .whitespaces).count
        let hasCode =
            message.contains("```") || message.contains("def ") || message.contains("function")
        let hasMultipleSteps =
            message.lowercased().contains("step") || message.lowercased().contains("then")

        if wordCount < 20 && !hasCode {
            return .low
        } else if wordCount > 100 || hasCode || hasMultipleSteps {
            return .high
        } else {
            return .medium
        }
    }

    enum RequestComplexity {
        case low, medium, high
    }

    private func calculatePriority(for message: String) -> OptimizedRequest.Priority {
        let urgencyKeywords = ["urgent", "asap", "immediately", "quickly", "fast"]
        let hasUrgency = urgencyKeywords.contains { message.lowercased().contains($0) }

        if hasUrgency {
            return .critical
        }

        let complexity = calculateComplexity(message)
        switch complexity {
        case .low: return .low
        case .medium: return .medium
        case .high: return .high
        }
    }

    private func estimateTokens(_ message: String) -> Int {
        // Rough token estimation (approximately 4 characters per token)
        return Int(Double(message.count) / 4.0)
    }

    // MARK: - Performance Monitoring

    /// Get performance metrics
    func getPerformanceMetrics() -> PerformanceMetrics {
        return cacheQueue.sync {
            let cacheHitRate = calculateCacheHitRate()
            let averageResponseTime = calculateAverageResponseTime()
            let connectionPoolSize = connectionPool.count

            return PerformanceMetrics(
                cacheSize: responseCache.count,
                cacheHitRate: cacheHitRate,
                averageResponseTime: averageResponseTime,
                connectionPoolSize: connectionPoolSize,
                memoryUsage: calculateMemoryUsage()
            )
        }
    }

    struct PerformanceMetrics {
        let cacheSize: Int
        let cacheHitRate: Double
        let averageResponseTime: TimeInterval
        let connectionPoolSize: Int
        let memoryUsage: Int64

        var summary: String {
            return """
                📊 Performance Metrics
                ═══════════════════════════
                Cache Size: \(cacheSize) entries
                Cache Hit Rate: \(String(format: "%.1f", cacheHitRate * 100))%
                Avg Response Time: \(String(format: "%.2f", averageResponseTime))s
                Connection Pool: \(connectionPoolSize) connections
                Memory Usage: \(memoryUsage / 1024) KB
                """
        }
    }

    private func calculateCacheHitRate() -> Double {
        // This would be tracked during actual usage
        // For now, return a placeholder
        return 0.75  // 75% hit rate
    }

    private func calculateAverageResponseTime() -> TimeInterval {
        // This would be tracked during actual usage
        return 2.5  // 2.5 seconds average
    }

    private func calculateMemoryUsage() -> Int64 {
        var totalMemory: Int64 = 0

        for (_, cached) in responseCache {
            totalMemory += Int64(cached.response.count)
        }

        return totalMemory
    }

    // MARK: - Cache Management

    /// Clear expired cache entries
    func clearExpiredCache() {
        cacheQueue.async {
            let expiredKeys = self.responseCache.compactMap { key, value in
                value.isExpired ? key : nil
            }

            for key in expiredKeys {
                self.responseCache.removeValue(forKey: key)
            }
        }
    }

    /// Clear all cache
    func clearAllCache() {
        cacheQueue.async {
            self.responseCache.removeAll()
        }
    }

    /// Optimize cache for better performance
    func optimizeCache() {
        cacheQueue.async {
            // Remove duplicate entries
            var seenHashes: Set<String> = []
            var keysToRemove: [String] = []

            for (key, value) in self.responseCache {
                if seenHashes.contains(value.hash) {
                    keysToRemove.append(key)
                } else {
                    seenHashes.insert(value.hash)
                }
            }

            for key in keysToRemove {
                self.responseCache.removeValue(forKey: key)
            }

            // Compact if necessary
            if self.responseCache.count > Int(Double(self.maxCacheSize) * 0.8) {
                self.evictOldestEntries()
            }
        }
    }
}

// MARK: - Request Batching

class RequestBatcher {
    private let batchSize = 5
    private let batchTimeout: TimeInterval = 2.0
    private var pendingRequests: [BatchedRequest] = []
    private var batchTimer: Timer?

    struct BatchedRequest {
        let id: String
        let message: String
        let model: String
        let completion: (Result<String, Error>) -> Void
        let timestamp: Date
    }

    /// Add request to batch or execute immediately if batch is full
    func addRequest(_ request: BatchedRequest) {
        pendingRequests.append(request)

        if pendingRequests.count >= batchSize {
            executeBatch()
        } else if batchTimer == nil {
            batchTimer = Timer.scheduledTimer(withTimeInterval: batchTimeout, repeats: false) { _ in
                self.executeBatch()
            }
        }
    }

    private func executeBatch() {
        batchTimer?.invalidate()
        batchTimer = nil

        let batch = pendingRequests
        pendingRequests.removeAll()

        Task {
            await processBatch(batch)
        }
    }

    private func processBatch(_ batch: [BatchedRequest]) async {
        // Process requests in parallel with controlled concurrency
        await withTaskGroup(of: Void.self) { group in
            for request in batch {
                group.addTask {
                    // Execute individual request
                    do {
                        let result = try await self.executeIndividualRequest(request)
                        request.completion(.success(result))
                    } catch {
                        request.completion(.failure(error))
                    }
                }
            }
        }
    }

    private func executeIndividualRequest(_ request: BatchedRequest) async throws -> String {
        // This would integrate with the actual Cascade execution
        // For now, return a placeholder
        return "Batched response for \(request.message)"
    }
}
