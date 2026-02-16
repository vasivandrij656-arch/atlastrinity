import Foundation
import Combine

/// Plugin system for custom extensions
class PluginManager {
    static let shared = PluginManager()
    
    private var plugins: [String: Plugin] = [:]
    private var pluginStates: [String: PluginState] = [:]
    private let pluginsDirectory: URL
    private let eventBus = EventBus()
    
    private init() {
        // Store plugins in user's application support
        let configPath = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        pluginsDirectory = configPath.appendingPathComponent("atlastrinity")
            .appendingPathComponent("windsurf_plugins")
        
        try? FileManager.default.createDirectory(at: pluginsDirectory, withIntermediateDirectories: true)
        
        loadPlugins()
    }
    
    // MARK: - Plugin Protocol
    
    protocol Plugin: AnyObject {
        var metadata: PluginMetadata { get }
        var state: PluginState { get set }
        
        func initialize(context: PluginContext) throws
        func execute(request: PluginRequest) async throws -> PluginResponse
        func shutdown() throws
    }
    
    struct PluginMetadata: Codable {
        let name: String
        let version: String
        let description: String
        let author: String
        let dependencies: [String]
        let permissions: [PluginPermission]
        let supportedModels: [String]
        let category: PluginCategory
        
        enum PluginCategory: String, Codable, CaseIterable {
            case cascade = "cascade"
            case workspace = "workspace"
            case monitoring = "monitoring"
            case utility = "utility"
            case integration = "integration"
            case experimental = "experimental"
        }
        
        enum PluginPermission: String, Codable, CaseIterable {
            case fileRead = "file_read"
            case fileWrite = "file_write"
            case networkAccess = "network_access"
            case systemInfo = "system_info"
            case configuration = "configuration"
            case cascadeControl = "cascade_control"
        }
    }
    
    enum PluginState: Equatable {
        case unloaded
        case loading
        case loaded
        case active
        case error(Error)
        case disabled
        
        static func == (lhs: PluginState, rhs: PluginState) -> Bool {
            switch (lhs, rhs) {
            case (.unloaded, .unloaded), (.loading, .loading), (.loaded, .loaded), (.active, .active), (.disabled, .disabled):
                return true
            case (.error(let lhsError), .error(let rhsError)):
                return lhsError.localizedDescription == rhsError.localizedDescription
            default:
                return false
            }
        }
    }
    
    struct PluginContext {
        let workspacePath: String
        let config: ConfigurationManager.WindsurfConfig
        let eventBus: EventBus
        let logger: PluginLogger
    }
    
    struct PluginRequest: Codable {
        let id: String
        let type: String
        let parameters: [String: String]  // Changed from [String: Any] to [String: String]
        let metadata: [String: String]
    }
    
    struct PluginResponse: Codable {
        let success: Bool
        let data: [String: String]  // Changed from [String: Any] to [String: String]
        let error: String?
        let metadata: [String: String]
    }
    
    // MARK: - Plugin Management
    
    func loadPlugins() {
        let pluginFiles = discoverPluginFiles()
        
        for pluginFile in pluginFiles {
            do {
                let plugin = try loadPlugin(from: pluginFile)
                plugins[plugin.metadata.name] = plugin
                pluginStates[plugin.metadata.name] = .loaded
                
                print("🔌 Loaded plugin: \(plugin.metadata.name) v\(plugin.metadata.version)")
            } catch {
                print("❌ Failed to load plugin from \(pluginFile.lastPathComponent): \(error)")
                pluginStates[pluginFile.lastPathComponent] = .error(error)
            }
        }
    }
    
    private func discoverPluginFiles() -> [URL] {
        guard let enumerator = FileManager.default.enumerator(at: pluginsDirectory, includingPropertiesForKeys: nil) else {
            return []
        }
        
        return enumerator.compactMap { element in
            if let url = element as? URL, url.pathExtension == "windsurf-plugin" {
                return url
            }
            return nil
        }
    }
    
    private func loadPlugin(from url: URL) throws -> Plugin {
        let data = try Data(contentsOf: url)
        let decoder = JSONDecoder()
        let pluginInfo = try decoder.decode(PluginInfo.self, from: data)
        
        // Create plugin instance based on type
        let plugin: Plugin
        
        switch pluginInfo.type {
        case "cascade":
            plugin = try CascadePlugin(info: pluginInfo)
        case "workspace":
            plugin = try WorkspacePlugin(info: pluginInfo)
        case "monitoring":
            plugin = try MonitoringPlugin(info: pluginInfo)
        case "utility":
            plugin = try UtilityPlugin(info: pluginInfo)
        case "integration":
            plugin = try IntegrationPlugin(info: pluginInfo)
        case "experimental":
            plugin = try ExperimentalPlugin(info: pluginInfo)
        default:
            throw PluginError.unknownPluginType(pluginInfo.type)
        }
        
        return plugin
    }
    
    // MARK: - Plugin Execution
    
    func executePlugin(_ pluginName: String, request: PluginRequest) async throws -> PluginResponse {
        guard let plugin = plugins[pluginName] else {
            throw PluginError.pluginNotFound(pluginName)
        }
        
        guard pluginStates[pluginName] == .active else {
            throw PluginError.pluginNotActive(pluginName)
        }
        
        do {
            let response = try await plugin.execute(request: request)
            
            // Log plugin execution
            let logger = PluginLogger(pluginName: pluginName)
            logger.info("Plugin execution successful", metadata: [
                "requestId": request.id,
                "requestType": request.type,
                "responseSuccess": response.success
            ])
            
            return response
        } catch {
            let logger = PluginLogger(pluginName: pluginName)
            logger.error("Plugin execution failed", metadata: [
                "requestId": request.id,
                "requestType": request.type,
                "error": error.localizedDescription
            ])
            
            throw error
        }
    }
    
    // MARK: - Plugin Lifecycle
    
    func activatePlugin(_ name: String) throws {
        guard var plugin = plugins[name] else {
            throw PluginError.pluginNotFound(name)
        }
        
        let context = PluginContext(
            workspacePath: FileManager.default.currentDirectoryPath,
            config: ConfigurationManager.shared.currentConfig,
            eventBus: eventBus,
            logger: PluginLogger(pluginName: name)
        )
        
        try plugin.initialize(context: context)
        plugin.state = .active
        pluginStates[name] = .active
        
        // Notify plugin activation
        eventBus.post(PluginEvent(type: .activated, pluginName: name, metadata: nil))
    }
    
    func deactivatePlugin(_ name: String) throws {
        guard var plugin = plugins[name] else {
            throw PluginError.pluginNotFound(name)
        }
        
        try plugin.shutdown()
        plugin.state = .loaded
        pluginStates[name] = .loaded
        
        // Notify plugin deactivation
        eventBus.post(PluginEvent(type: .deactivated, pluginName: name, metadata: nil))
    }
    
    func unloadPlugin(_ name: String) throws {
        try deactivatePlugin(name)
        plugins.removeValue(forKey: name)
        pluginStates.removeValue(forKey: name)
    }
    
    // MARK: - Plugin Information
    
    func getPluginList() -> [PluginInfo] {
        return plugins.values.map { plugin in
            PluginInfo(
                name: plugin.metadata.name,
                version: plugin.metadata.version,
                type: plugin.metadata.category.rawValue,
                description: plugin.metadata.description,
                author: plugin.metadata.author,
                dependencies: [],
                permissions: [],
                supportedModels: []
            )
        }
    }
    
    func getPluginState(_ name: String) -> PluginState? {
        return pluginStates[name]
    }
    
    func getPluginMetrics() -> PluginMetrics {
        let totalPlugins = plugins.count
        let activePlugins = pluginStates.values.filter { if case .active = $0 { return true } else { return false } }.count
        let errorPlugins = pluginStates.values.filter { if case .error = $0 { return true } else { return false } }.count
        
        return PluginMetrics(
            total: totalPlugins,
            active: activePlugins,
            loaded: totalPlugins - activePlugins - errorPlugins,
            errors: errorPlugins
        )
    }
    
    struct PluginMetrics {
        let total: Int
        let active: Int
        let loaded: Int
        let errors: Int
        
        var summary: String {
            return """
            🔌 Plugin Metrics
            ═══════════════════════════
            Total: \(total)
            Active: \(active)
            Loaded: \(loaded)
            Errors: \(errors)
            """
        }
    }
}

// MARK: - Plugin Types

class CascadePlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .cascade
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        // Initialize cascade-specific functionality
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle cascade-specific requests
        switch request.type {
        case "enhance_scope":
            return PluginManager.PluginResponse(
                success: true,
                data: ["enhanced": "true"],
                error: nil,
                metadata: ["plugin": "cascade"]
            )
        case "optimize_cascade":
            return PluginManager.PluginResponse(
                success: true,
                data: ["optimized": "true"],
                error: nil,
                metadata: ["plugin": "cascade"]
            )
        default:
            throw PluginError.unsupportedRequest(request.type)
        }
    }
    
    func shutdown() throws {
        state = .loaded
    }
    
    private func enhanceScope(request: PluginManager.PluginRequest, context: PluginManager.PluginContext) throws -> PluginManager.PluginResponse {
        // Enhance scope with plugin-specific logic
        return PluginManager.PluginResponse(
            success: true,
            data: ["enhanced": "true"],
            error: nil,
            metadata: ["plugin": "cascade"]
        )
    }
    
    private func optimizeCascade(request: PluginManager.PluginRequest, context: PluginManager.PluginContext) throws -> PluginManager.PluginResponse {
        // Optimize cascade execution
        return PluginManager.PluginResponse(
            success: true,
            data: ["optimized": "true"],
            error: nil,
            metadata: ["plugin": "cascade"]
        )
    }
}

class WorkspacePlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .workspace
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle workspace-specific requests
        return PluginManager.PluginResponse(
            success: true,
            data: ["workspace_action": "true"],
            error: nil,
            metadata: ["plugin": "workspace"]
        )
    }
    
    func shutdown() throws {
        state = .loaded
    }
}

class MonitoringPlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .monitoring
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle monitoring-specific requests
        return PluginManager.PluginResponse(
            success: true,
            data: ["monitoring_data": "true"],
            error: nil,
            metadata: ["plugin": "monitoring"]
        )
    }
    
    func shutdown() throws {
        state = .loaded
    }
}

class UtilityPlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .utility
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle utility-specific requests
        return PluginManager.PluginResponse(
            success: true,
            data: ["utility_result": "true"],
            error: nil,
            metadata: ["plugin": "utility"]
        )
    }
    
    func shutdown() throws {
        state = .loaded
    }
}

class IntegrationPlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .integration
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle integration-specific requests
        return PluginManager.PluginResponse(
            success: true,
            data: ["integration_result": "true"],
            error: nil,
            metadata: ["plugin": "integration"]
        )
    }
    
    func shutdown() throws {
        state = .loaded
    }
}

class ExperimentalPlugin: PluginManager.Plugin {
    var metadata: PluginManager.PluginMetadata
    var state: PluginManager.PluginState = .unloaded
    
    init(info: PluginInfo) throws {
        self.metadata = PluginManager.PluginMetadata(
            name: info.name,
            version: info.version,
            description: info.description,
            author: info.author,
            dependencies: info.dependencies,
            permissions: info.permissions.map { PluginManager.PluginMetadata.PluginPermission(rawValue: $0)! },
            supportedModels: info.supportedModels,
            category: .experimental
        )
    }
    
    func initialize(context: PluginManager.PluginContext) throws {
        state = .loaded
    }
    
    func execute(request: PluginManager.PluginRequest) async throws -> PluginManager.PluginResponse {
        // Handle experimental-specific requests
        return PluginManager.PluginResponse(
            success: true,
            data: ["experimental_result": "true"],
            error: nil,
            metadata: ["plugin": "experimental"]
        )
    }
    
    func shutdown() throws {
        state = .loaded
    }
}

// MARK: - Supporting Types

struct PluginInfo: Codable {
    let name: String
    let version: String
    let type: String
    let description: String
    let author: String
    let dependencies: [String]
    let permissions: [String]
    let supportedModels: [String]
}

enum PluginError: Error {
    case pluginNotFound(String)
    case pluginNotActive(String)
    case unknownPluginType(String)
    case unsupportedRequest(String)
    case initializationFailed(String)
}

// MARK: - Event System

class EventBus {
    private var subscribers: [String: [PluginEventHandler]] = [:]
    
    func subscribe(to eventType: String, handler: @escaping PluginEventHandler) {
        if subscribers[eventType] == nil {
            subscribers[eventType] = []
        }
        subscribers[eventType]?.append(handler)
    }
    
    func post(_ event: PluginEvent) {
        subscribers[event.type.rawValue]?.forEach { handler in
            handler(event)
        }
    }
}

typealias PluginEventHandler = (PluginEvent) -> Void

struct PluginEvent {
    let type: EventType
    let pluginName: String
    let metadata: [String: Any]?
    
    enum EventType: String {
        case activated
        case deactivated
        case error
        case performance
        case cascade
    }
}

// MARK: - Plugin Logger

class PluginLogger {
    private let pluginName: String
    
    init(pluginName: String) {
        self.pluginName = pluginName
    }
    
    func info(_ message: String, metadata: [String: Any]? = nil) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var logEntry = "[\(timestamp)] [PLUGIN:\(pluginName)] INFO: \(message)"
        
        if let metadata = metadata {
            logEntry += " | \(metadata)"
        }
        
        print(logEntry)
    }
    
    func warning(_ message: String, metadata: [String: Any]? = nil) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var logEntry = "[\(timestamp)] [PLUGIN:\(pluginName)] WARNING: \(message)"
        
        if let metadata = metadata {
            logEntry += " | \(metadata)"
        }
        
        print(logEntry)
    }
    
    func error(_ message: String, metadata: [String: Any]? = nil) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var logEntry = "[\(timestamp)] [PLUGIN:\(pluginName)] ERROR: \(message)"
        
        if let metadata = metadata {
            logEntry += " | \(metadata)"
        }
        
        print(logEntry)
    }
    
    func debug(_ message: String, metadata: [String: Any]? = nil) {
        let timestamp = ISO8601DateFormatter().string(from: Date())
        var logEntry = "[\(timestamp)] [PLUGIN:\(pluginName)] DEBUG: \(message)"
        
        if let metadata = metadata {
            logEntry += " | \(metadata)"
        }
        
        print(logEntry)
    }
}
