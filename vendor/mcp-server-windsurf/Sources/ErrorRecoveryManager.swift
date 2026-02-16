import Foundation

/// Error recovery and fallback mechanisms for Windsurf MCP
class ErrorRecoveryManager {
    static let shared = ErrorRecoveryManager()

    private var errorHistory: [ErrorRecord] = []
    private var recoveryStrategies: [String: RecoveryStrategy] = [:]
    private let maxErrorHistory = 100

    private init() {
        setupDefaultStrategies()
    }

    // MARK: - Error Recording

    func recordError(_ error: Error, context: ErrorContext) {
        let record = ErrorRecord(
            error: error,
            context: context,
            timestamp: Date(),
            recoveryAttempted: false
        )

        errorHistory.append(record)

        // Keep only recent errors
        if errorHistory.count > maxErrorHistory {
            errorHistory.removeFirst(errorHistory.count - maxErrorHistory)
        }

        // Log the error
        WindsurfLogger.shared.logCascadeError(
            cascadeId: context.cascadeId ?? "unknown",
            error: "\(error.localizedDescription) (Context: \(context.operation))"
        )

        // Attempt recovery
        attemptRecovery(for: record)
    }

    // MARK: - Recovery Strategies

    private func setupDefaultStrategies() {
        // Language server connection errors
        recoveryStrategies["connection_failed"] = RecoveryStrategy(
            name: "Reconnect to Language Server",
            priority: .high,
            maxRetries: 3,
            retryDelay: 2.0,
            action: { [weak self] context in
                self?.handleConnectionFailure(context)
            }
        )

        // Cascade timeout errors
        recoveryStrategies["cascade_timeout"] = RecoveryStrategy(
            name: "Cascade Timeout Recovery",
            priority: .medium,
            maxRetries: 2,
            retryDelay: 5.0,
            action: { [weak self] context in
                self?.handleCascadeTimeout(context)
            }
        )

        // Protobuf parsing errors
        recoveryStrategies["protobuf_error"] = RecoveryStrategy(
            name: "Protobuf Fallback",
            priority: .medium,
            maxRetries: 1,
            retryDelay: 1.0,
            action: { [weak self] context in
                self?.handleProtobufError(context)
            }
        )

        // API key errors
        recoveryStrategies["api_key_error"] = RecoveryStrategy(
            name: "API Key Validation",
            priority: .critical,
            maxRetries: 1,
            retryDelay: 0.0,
            action: { [weak self] context in
                self?.handleAPIKeyError(context)
            }
        )

        // File system errors
        recoveryStrategies["filesystem_error"] = RecoveryStrategy(
            name: "File System Recovery",
            priority: .medium,
            maxRetries: 3,
            retryDelay: 1.0,
            action: { [weak self] context in
                self?.handleFileSystemError(context)
            }
        )
    }

    private func attemptRecovery(for record: ErrorRecord) {
        let errorType = categorizeError(record.error)
        guard let strategy = recoveryStrategies[errorType] else {
            fputs("log: [windsurf] No recovery strategy for error type: \(errorType)\n", stderr)
            return
        }

        // Check if we've exceeded max retries
        let retryCount = errorHistory.filter {
            categorizeError($0.error) == errorType
                && $0.context.operation == record.context.operation
        }.count

        if retryCount > strategy.maxRetries {
            fputs("log: [windsurf] Max retries exceeded for strategy: \(strategy.name)\n", stderr)
            return
        }

        fputs(
            "log: [windsurf] Attempting recovery: \(strategy.name) (attempt \(retryCount)/\(strategy.maxRetries))\n",
            stderr)

        // Wait before retry if specified
        if strategy.retryDelay > 0 {
            Thread.sleep(forTimeInterval: strategy.retryDelay)
        }

        // Execute recovery action
        strategy.action(record.context)
    }

    private func categorizeError(_ error: Error) -> String {
        let errorDescription = error.localizedDescription.lowercased()

        if errorDescription.contains("connection") || errorDescription.contains("network") {
            return "connection_failed"
        }

        if errorDescription.contains("timeout") || errorDescription.contains("timed out") {
            return "cascade_timeout"
        }

        if errorDescription.contains("protobuf") || errorDescription.contains("proto") {
            return "protobuf_error"
        }

        if errorDescription.contains("api key") || errorDescription.contains("authentication") {
            return "api_key_error"
        }

        if errorDescription.contains("file") || errorDescription.contains("directory") {
            return "filesystem_error"
        }

        return "unknown"
    }

    // MARK: - Recovery Actions

    private func handleConnectionFailure(_ context: ErrorContext) {
        fputs("log: [windsurf] Attempting to reconnect to Language Server...\n", stderr)

        // Invalidate cached connection and force re-detection
        Task {
            await globalState.invalidateCache()
            if let newConnection = await globalState.ensureConnection() {
                fputs(
                    "log: [windsurf] Successfully reconnected to Language Server on port \(newConnection.port)\n",
                    stderr)

                // Retry the original operation if possible
                if let originalMessage = context.parameters?["message"] {
                    _ = await handleCascade(
                        message: originalMessage, model: context.parameters?["model"])
                }
            } else {
                fputs("log: [windsurf] Failed to reconnect to Language Server\n", stderr)
            }
        }
    }

    private func handleCascadeTimeout(_ context: ErrorContext) {
        fputs("log: [windsurf] Cascade timeout - attempting with shorter timeout...\n", stderr)

        // Retry with reduced scope and simpler message
        guard let originalMessage = context.parameters?["message"] else { return }

        let simplifiedMessage = simplifyMessage(originalMessage)
        let fallbackModel = context.parameters?["model"] ?? "swe-1.5"

        Task {
            let result = await handleCascade(message: simplifiedMessage, model: fallbackModel)
            fputs("log: [windsurf] Fallback cascade result: \(result.prefix(100))...\n", stderr)
        }
    }

    private func handleProtobufError(_ context: ErrorContext) {
        fputs("log: [windsurf] Protobuf error - falling back to chat API...\n", stderr)

        // Fallback to regular chat API for simple requests
        guard let originalMessage = context.parameters?["message"] else { return }

        let fallbackModel = context.parameters?["model"] ?? "windsurf-fast"

        Task {
            let result = await handleChat(
                message: "Please help with: \(originalMessage)",
                model: fallbackModel,
                systemPrompt: "This is a fallback response due to Cascade issues.",
                stream: false
            )
            fputs("log: [windsurf] Chat fallback result: \(result.prefix(100))...\n", stderr)
        }
    }

    private func handleAPIKeyError(_ context: ErrorContext) {
        fputs("log: [windsurf] API Key error - validating configuration...\n", stderr)

        let apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"] ?? ""

        if apiKey.isEmpty {
            fputs(
                "log: [windsurf] ERROR: WINDSURF_API_KEY environment variable is not set\n", stderr)
            fputs("log: [windsurf] Please set it with: export WINDSURF_API_KEY=sk-ws-...\n", stderr)
        } else if !apiKey.hasPrefix("sk-ws-") || apiKey.count <= 20 {
            fputs(
                "log: [windsurf] ERROR: Invalid API key format. Expected format: sk-ws-...\n",
                stderr)
        } else {
            fputs("log: [windsurf] API key format appears valid, checking connection...\n", stderr)
        }
    }

    private func handleFileSystemError(_ context: ErrorContext) {
        fputs("log: [windsurf] File system error - checking permissions and paths...\n", stderr)

        let currentPath = FileManager.default.currentDirectoryPath
        let isWritable = FileManager.default.isWritableFile(atPath: currentPath)

        fputs("log: [windsurf] Current directory: \(currentPath)\n", stderr)
        fputs("log: [windsurf] Directory writable: \(isWritable)\n", stderr)

        if !isWritable {
            fputs("log: [windsurf] ERROR: Current directory is not writable\n", stderr)
            fputs(
                "log: [windsurf] Please check file permissions or change to a writable directory\n",
                stderr)
        }
    }

    // MARK: - Fallback Mechanisms

    private func simplifyMessage(_ message: String) -> String {
        // Extract the core request from complex messages
        let sentences = message.components(separatedBy: ". ").filter { !$0.isEmpty }

        if sentences.count > 3 {
            // Take first sentence for simplicity
            return sentences.first ?? message
        }

        // Remove complex formatting and instructions
        let simplified =
            message
            .replacingOccurrences(of: "Please create", with: "Create")
            .replacingOccurrences(of: "I would like you to", with: "")
            .replacingOccurrences(of: "Could you please", with: "")
            .replacingOccurrences(of: "Make sure to", with: "")

        return simplified.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    // MARK: - Health Monitoring

    func getSystemHealth() -> SystemHealth {
        let recentErrors = errorHistory.filter {
            Date().timeIntervalSince($0.timestamp) < 300  // Last 5 minutes
        }

        let errorCounts = recentErrors.reduce(into: [String: Int]()) { counts, record in
            let errorType = categorizeError(record.error)
            counts[errorType, default: 0] += 1
        }

        let overallHealth: HealthStatus
        if recentErrors.count > 10 {
            overallHealth = .critical
        } else if recentErrors.count > 5 {
            overallHealth = .warning
        } else {
            overallHealth = .healthy
        }

        return SystemHealth(
            status: overallHealth,
            recentErrorCount: recentErrors.count,
            errorTypes: errorCounts,
            lastError: recentErrors.last,
            recommendations: generateRecommendations(errorCounts: errorCounts)
        )
    }

    private func generateRecommendations(errorCounts: [String: Int]) -> [String] {
        var recommendations: [String] = []

        if errorCounts["connection_failed", default: 0] > 2 {
            recommendations.append(
                "Multiple connection failures detected. Check if Windsurf IDE is running.")
        }

        if errorCounts["cascade_timeout", default: 0] > 2 {
            recommendations.append(
                "Frequent timeouts detected. Consider using simpler requests or different models.")
        }

        if errorCounts["api_key_error", default: 0] > 0 {
            recommendations.append(
                "API key issues detected. Verify your WINDSURF_API_KEY environment variable.")
        }

        if errorCounts["filesystem_error", default: 0] > 1 {
            recommendations.append(
                "File system errors detected. Check directory permissions and disk space.")
        }

        return recommendations
    }
}

// MARK: - Supporting Models

struct ErrorRecord {
    let error: Error
    let context: ErrorContext
    let timestamp: Date
    var recoveryAttempted: Bool
}

struct ErrorContext {
    let operation: String
    let cascadeId: String?
    let parameters: [String: String]?

    init(operation: String, cascadeId: String? = nil, parameters: [String: String]? = nil) {
        self.operation = operation
        self.cascadeId = cascadeId
        self.parameters = parameters
    }
}

struct RecoveryStrategy {
    let name: String
    let priority: Priority
    let maxRetries: Int
    let retryDelay: TimeInterval
    let action: (ErrorContext) -> Void

    enum Priority {
        case critical, high, medium, low
    }
}

enum HealthStatus: String, Codable {
    case healthy = "healthy"
    case warning = "warning"
    case critical = "critical"
}

struct SystemHealth {
    let status: HealthStatus
    let recentErrorCount: Int
    let errorTypes: [String: Int]
    let lastError: ErrorRecord?
    let recommendations: [String]

    var summary: String {
        var summary = """
            🏥 Windsurf MCP System Health
            ════════════════════════════
            Status: \(statusEmoji) \(status.rawValue.uppercased())
            Recent Errors (5 min): \(recentErrorCount)
            """

        if !errorTypes.isEmpty {
            summary += "\n\nError Types:\n"
            for (type, count) in errorTypes.sorted(by: { $0.value > $1.value }) {
                summary += "  • \(type): \(count)\n"
            }
        }

        if !recommendations.isEmpty {
            summary += "\nRecommendations:\n"
            for recommendation in recommendations {
                summary += "  • \(recommendation)\n"
            }
        }

        return summary
    }

    private var statusEmoji: String {
        switch status {
        case .healthy: return "🟢"
        case .warning: return "🟡"
        case .critical: return "🔴"
        }
    }
}

// MARK: - Integration Extensions

extension ErrorRecoveryManager {

    func handleCascadeWithErrorRecovery(message: String, model: String?) async -> String {
        let context = ErrorContext(
            operation: "cascade",
            parameters: ["message": message, "model": model ?? ""]
        )

        do {
            let result = try await performCascadeWithTimeout(message: message, model: model)
            return result
        } catch {
            recordError(error, context: context)
            return "❌ Cascade failed: \(error.localizedDescription)"
        }
    }

    private func performCascadeWithTimeout(message: String, model: String?) async throws -> String {
        // Implement with timeout and error handling
        return try await withThrowingTaskGroup(of: String.self) { group in
            group.addTask {
                return await handleCascade(message: message, model: model)
            }

            // Add timeout task
            group.addTask {
                try await Task.sleep(nanoseconds: 180_000_000_000)  // 3 minutes
                throw NSError(
                    domain: "WindsurfMCP", code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Cascade operation timed out"])
            }

            let result = try await group.next()!
            group.cancelAll()
            return result
        }
    }
}
