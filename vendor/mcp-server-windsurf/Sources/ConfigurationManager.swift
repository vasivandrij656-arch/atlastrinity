import Foundation
import Combine

/// Configuration management and settings persistence
class ConfigurationManager {
    static let shared = ConfigurationManager()
    
    private let configURL: URL
    private var config: WindsurfConfig
    private var configSubject = PassthroughSubject<WindsurfConfig, Never>()
    
    var configPublisher: AnyPublisher<WindsurfConfig, Never> {
        configSubject.eraseToAnyPublisher()
    }
    
    private init() {
        // Store config in user's application support
        let configPath = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        configURL = configPath.appendingPathComponent("atlastrinity")
            .appendingPathComponent("windsurf_config.json")
        
        // Create directory if it doesn't exist
        try? FileManager.default.createDirectory(at: configURL.deletingLastPathComponent(), withIntermediateDirectories: true)
        
        // Load or create default config
        self.config = Self.loadConfig(from: configURL) ?? WindsurfConfig.default
        
        // Start auto-save timer
        startAutoSave()
    }
    
    // MARK: - Configuration Model
    
    struct WindsurfConfig: Codable {
        var general: GeneralSettings
        var cascade: CascadeSettings
        var performance: PerformanceSettings
        var logging: LoggingSettings
        var workspace: WorkspaceSettings
        var experimental: ExperimentalSettings
        
        static let `default` = WindsurfConfig(
            general: GeneralSettings(),
            cascade: CascadeSettings(),
            performance: PerformanceSettings(),
            logging: LoggingSettings(),
            workspace: WorkspaceSettings(),
            experimental: ExperimentalSettings()
        )
    }
    
    struct GeneralSettings: Codable {
        var apiKey: String?
        var defaultModel: String
        var timeoutDuration: TimeInterval
        var retryAttempts: Int
        var autoDetectWorkspace: Bool
        
        init() {
            self.apiKey = ProcessInfo.processInfo.environment["WINDSURF_API_KEY"]
            self.defaultModel = "swe-1.5"
            self.timeoutDuration = 120
            self.retryAttempts = 3
            self.autoDetectWorkspace = true
        }
    }
    
    struct CascadeSettings: Codable {
        var enableActionPhase: Bool
        var enableCortexReasoning: Bool
        var enableFileOperations: Bool
        var enableToolExecution: Bool
        var enableAutonomousExecution: Bool
        var actionTimeout: TimeInterval
        var scopeFields: [Int: Bool]
        var cortexFields: [Int: Bool]
        
        init() {
            self.enableActionPhase = true
            self.enableCortexReasoning = true
            self.enableFileOperations = true
            self.enableToolExecution = true
            self.enableAutonomousExecution = true
            self.actionTimeout = 180
            
            // Default field mappings based on experimental results
            self.scopeFields = [
                1: true,  // path
                2: true,  // uri
                3: true,  // repoName
                4: true,  // repoUrl
                5: true,  // is_workspace_root
                6: true,  // enable_file_operations
                7: true,  // enable_tool_execution
                10: true  // is_git_workspace
            ]
            
            self.cortexFields = [
                11: true, // enable_cortex_reasoning
                12: true, // enable_action_phase
                13: true, // enable_tool_execution
                14: true, // enable_file_operations
                15: true, // enable_autonomous_execution
                20: true  // cortex_config
            ]
        }
    }
    
    struct PerformanceSettings: Codable {
        var enableCaching: Bool
        var cacheSize: Int
        var cacheExpiration: TimeInterval
        var enableConnectionPooling: Bool
        var maxConnections: Int
        var enableRequestBatching: Bool
        var batchSize: Int
        var enableOptimization: Bool
        
        init() {
            self.enableCaching = true
            self.cacheSize = 100
            self.cacheExpiration = 300
            self.enableConnectionPooling = true
            self.maxConnections = 3
            self.enableRequestBatching = true
            self.batchSize = 5
            self.enableOptimization = true
        }
    }
    
    struct LoggingSettings: Codable {
        var enableLogging: Bool
        var logLevel: LogLevel
        var logToFile: Bool
        var logToConsole: Bool
        var maxLogFileSize: Int64
        var logRetentionDays: Int
        var enableDebugMode: Bool
        var logCategories: Set<String>
        
        enum LogLevel: String, Codable, CaseIterable {
            case debug, info, warning, error, critical
        }
        
        init() {
            self.enableLogging = true
            self.logLevel = .info
            self.logToFile = true
            self.logToConsole = true
            self.maxLogFileSize = 10 * 1024 * 1024 // 10MB
            self.logRetentionDays = 7
            self.enableDebugMode = false
            self.logCategories = ["cascade", "actionphase", "performance", "workspace"]
        }
    }
    
    struct WorkspaceSettings: Codable {
        var autoSwitchOnGitChange: Bool
        var rememberLastWorkspace: Bool
        var workspaceSpecificSettings: [String: WorkspaceSpecificConfig]
        var enableProjectDetection: Bool
        var enableDependencyAnalysis: Bool
        
        init() {
            self.autoSwitchOnGitChange = true
            self.rememberLastWorkspace = true
            self.workspaceSpecificSettings = [:]
            self.enableProjectDetection = true
            self.enableDependencyAnalysis = true
        }
    }
    
    struct WorkspaceSpecificConfig: Codable {
        var preferredModel: String?
        var customScopeFields: [Int: String]?
        var disabledFeatures: Set<String>?
        var customEnvironment: [String: String]?
        
        init() {
            self.preferredModel = nil
            self.customScopeFields = nil
            self.disabledFeatures = nil
            self.customEnvironment = nil
        }
    }
    
    struct ExperimentalSettings: Codable {
        var enableFieldExperimentation: Bool
        var autoOptimizeFields: Bool
        var enableAdvancedStreaming: Bool
        var enablePluginSystem: Bool
        var testFieldCombinations: [[Int: Int]]
        var learnedFieldMappings: [Int: Double] // Field number to success rate
        
        init() {
            self.enableFieldExperimentation = false
            self.autoOptimizeFields = true
            self.enableAdvancedStreaming = true
            self.enablePluginSystem = false
            self.testFieldCombinations = []
            self.learnedFieldMappings = [:]
        }
    }
    
    // MARK: - Configuration Access
    
    var currentConfig: WindsurfConfig {
        get { config }
        set {
            config = newValue
            saveConfig()
            configSubject.send(newValue)
        }
    }
    
    var general: GeneralSettings {
        get { config.general }
        set {
            config.general = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    var cascade: CascadeSettings {
        get { config.cascade }
        set {
            config.cascade = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    var performance: PerformanceSettings {
        get { config.performance }
        set {
            config.performance = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    var logging: LoggingSettings {
        get { config.logging }
        set {
            config.logging = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    var workspace: WorkspaceSettings {
        get { config.workspace }
        set {
            config.workspace = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    var experimental: ExperimentalSettings {
        get { config.experimental }
        set {
            config.experimental = newValue
            saveConfig()
            configSubject.send(config)
        }
    }
    
    // MARK: - Configuration Management
    
    private static func loadConfig(from url: URL) -> WindsurfConfig? {
        guard FileManager.default.fileExists(atPath: url.path) else {
            return nil
        }
        
        do {
            let data = try Data(contentsOf: url)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            return try decoder.decode(WindsurfConfig.self, from: data)
        } catch {
            fputs("log: [windsurf] Failed to load config: \(error)\n", stderr)
            return nil
        }
    }
    
    private func saveConfig() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted
            
            let data = try encoder.encode(config)
            try data.write(to: configURL)
        } catch {
            fputs("log: [windsurf] Failed to save config: \(error)\n", stderr)
        }
    }
    
    private func startAutoSave() {
        Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { _ in
            self.saveConfig()
        }
    }
    
    // MARK: - Configuration Validation
    
    func validateConfig() -> [ConfigValidationError] {
        var errors: [ConfigValidationError] = []
        
        // Validate general settings
        if config.general.apiKey?.isEmpty == false {
            let apiKey = config.general.apiKey!
            if !apiKey.hasPrefix("sk-ws-") || apiKey.count <= 20 {
                errors.append(.invalidAPIKey)
            }
        }
        
        if config.general.timeoutDuration < 10 || config.general.timeoutDuration > 600 {
            errors.append(.invalidTimeout)
        }
        
        // Validate cascade settings
        if config.cascade.actionTimeout < 30 || config.cascade.actionTimeout > 600 {
            errors.append(.invalidActionTimeout)
        }
        
        // Validate performance settings
        if config.performance.cacheSize < 10 || config.performance.cacheSize > 1000 {
            errors.append(.invalidCacheSize)
        }
        
        // Validate logging settings
        if config.logging.maxLogFileSize < 1024 * 1024 || config.logging.maxLogFileSize > 100 * 1024 * 1024 {
            errors.append(.invalidLogFileSize)
        }
        
        return errors
    }
    
    enum ConfigValidationError {
        case invalidAPIKey
        case invalidTimeout
        case invalidActionTimeout
        case invalidCacheSize
        case invalidLogFileSize
        
        var description: String {
            switch self {
            case .invalidAPIKey:
                return "API key must be in format 'sk-ws-...' and be longer than 20 characters"
            case .invalidTimeout:
                return "Timeout must be between 10 and 600 seconds"
            case .invalidActionTimeout:
                return "Action timeout must be between 30 and 600 seconds"
            case .invalidCacheSize:
                return "Cache size must be between 10 and 1000 entries"
            case .invalidLogFileSize:
                return "Log file size must be between 1MB and 100MB"
            }
        }
    }
    
    // MARK: - Configuration Templates
    
    func applyTemplate(_ template: ConfigTemplate) {
        switch template {
        case .development:
            applyDevelopmentTemplate()
        case .production:
            applyProductionTemplate()
        case .minimal:
            applyMinimalTemplate()
        case .experimental:
            applyExperimentalTemplate()
        }
    }
    
    enum ConfigTemplate {
        case development
        case production
        case minimal
        case experimental
    }
    
    private func applyDevelopmentTemplate() {
        config.logging.logLevel = .debug
        config.logging.enableDebugMode = true
        config.experimental.enableFieldExperimentation = true
        config.performance.enableCaching = false // Disable caching for development
        config.cascade.actionTimeout = 300 // Longer timeout for debugging
    }
    
    private func applyProductionTemplate() {
        config.logging.logLevel = .warning
        config.logging.enableDebugMode = false
        config.experimental.enableFieldExperimentation = false
        config.performance.enableCaching = true
        config.performance.enableOptimization = true
        config.cascade.actionTimeout = 120 // Standard timeout
    }
    
    private func applyMinimalTemplate() {
        config.logging.enableLogging = false
        config.performance.enableCaching = false
        config.performance.enableOptimization = false
        config.experimental.enableFieldExperimentation = false
        config.cascade.enableActionPhase = false
    }
    
    private func applyExperimentalTemplate() {
        config.experimental.enableFieldExperimentation = true
        config.experimental.enableAdvancedStreaming = true
        config.experimental.enablePluginSystem = true
        config.logging.enableDebugMode = true
        config.cascade.enableAutonomousExecution = true
    }
    
    // MARK: - Configuration Export/Import
    
    func exportConfig() -> Data? {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted
            return try encoder.encode(config)
        } catch {
            fputs("log: [windsurf] Failed to export config: \(error)\n", stderr)
            return nil
        }
    }
    
    func importConfig(from data: Data) -> Bool {
        do {
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601
            let newConfig = try decoder.decode(WindsurfConfig.self, from: data)
            
            // Validate imported config
            let oldConfig = config
            config = newConfig
            
            let errors = validateConfig()
            if !errors.isEmpty {
                config = oldConfig // Revert on validation failure
                return false
            }
            
            saveConfig()
            configSubject.send(config)
            return true
        } catch {
            fputs("log: [windsurf] Failed to import config: \(error)\n", stderr)
            return false
        }
    }
    
    // MARK: - Configuration Reset
    
    func resetToDefaults() {
        config = WindsurfConfig.default
        saveConfig()
        configSubject.send(config)
    }
    
    func resetSection(_ section: ConfigSection) {
        switch section {
        case .general:
            config.general = GeneralSettings()
        case .cascade:
            config.cascade = CascadeSettings()
        case .performance:
            config.performance = PerformanceSettings()
        case .logging:
            config.logging = LoggingSettings()
        case .workspace:
            config.workspace = WorkspaceSettings()
        case .experimental:
            config.experimental = ExperimentalSettings()
        }
        
        saveConfig()
        configSubject.send(config)
    }
    
    enum ConfigSection {
        case general, cascade, performance, logging, workspace, experimental
    }
    
    // MARK: - Configuration Analytics
    
    func getConfigAnalytics() -> ConfigAnalytics {
        return ConfigAnalytics(
            configVersion: "1.0.0",
            lastModified: Date(),
            validationErrors: validateConfig(),
            enabledFeatures: getEnabledFeatures(),
            performanceImpact: calculatePerformanceImpact(),
            memoryFootprint: calculateMemoryFootprint()
        )
    }
    
    struct ConfigAnalytics {
        let configVersion: String
        let lastModified: Date
        let validationErrors: [ConfigValidationError]
        let enabledFeatures: [String]
        let performanceImpact: PerformanceImpact
        let memoryFootprint: Int64
        
        var summary: String {
            var summary = """
            📊 Configuration Analytics
            ═══════════════════════════
            Version: \(configVersion)
            Last Modified: \(lastModified.formatted(date: .abbreviated, time: .shortened))
            Validation Errors: \(validationErrors.count)
            Enabled Features: \(enabledFeatures.count)
            Performance Impact: \(performanceImpact.description)
            Memory Footprint: \(memoryFootprint / 1024) KB
            """
            
            if !validationErrors.isEmpty {
                summary += "\n⚠️ Validation Issues:\n"
                for error in validationErrors {
                    summary += "  • \(error.description)\n"
                }
            }
            
            return summary
        }
    }
    
    enum PerformanceImpact {
        case low, medium, high
        
        var description: String {
            switch self {
            case .low: return "Low"
            case .medium: return "Medium"
            case .high: return "High"
            }
        }
    }
    
    private func getEnabledFeatures() -> [String] {
        var features: [String] = []
        
        if config.cascade.enableActionPhase { features.append("Action Phase") }
        if config.cascade.enableCortexReasoning { features.append("Cortex Reasoning") }
        if config.performance.enableCaching { features.append("Response Caching") }
        if config.performance.enableConnectionPooling { features.append("Connection Pooling") }
        if config.experimental.enableFieldExperimentation { features.append("Field Experimentation") }
        if config.experimental.enableAdvancedStreaming { features.append("Advanced Streaming") }
        
        return features
    }
    
    private func calculatePerformanceImpact() -> PerformanceImpact {
        var impactScore = 0
        
        if config.performance.enableCaching { impactScore += 1 }
        if config.performance.enableConnectionPooling { impactScore += 1 }
        if config.performance.enableOptimization { impactScore += 1 }
        if config.cascade.enableActionPhase { impactScore += 2 }
        if config.experimental.enableAdvancedStreaming { impactScore += 2 }
        
        switch impactScore {
        case 0...2: return .low
        case 3...5: return .medium
        default: return .high
        }
    }
    
    private func calculateMemoryFootprint() -> Int64 {
        var footprint: Int64 = 1024 // Base footprint
        
        if config.performance.enableCaching {
            footprint += Int64(config.performance.cacheSize * 1000) // Approximate per entry
        }
        
        if config.logging.enableLogging {
            footprint += config.logging.maxLogFileSize
        }
        
        return footprint
    }
}
