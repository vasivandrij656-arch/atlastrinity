import Foundation
import Combine

/// Advanced analytics dashboard for Windsurf MCP
class AnalyticsDashboard {
    static let shared = AnalyticsDashboard()
    
    private var metrics: [String: Any] = [:]
    private var eventLog: [AnalyticsEvent] = []
    private let metricsSubject = PassthroughSubject<[String: Any], Never>()
    private let eventSubject = PassthroughSubject<AnalyticsEvent, Never>()
    
    var metricsPublisher: AnyPublisher<[String: Any], Never> {
        metricsSubject.eraseToAnyPublisher()
    }
    
    var eventPublisher: AnyPublisher<AnalyticsEvent, Never> {
        eventSubject.eraseToAnyPublisher()
    }
    
    private init() {
        startMetricsCollection()
    }
    
    // MARK: - Analytics Event
    
    struct AnalyticsEvent: Codable {
        let timestamp: Date
        let type: EventType
        let category: EventCategory
        let data: [String: Any]
        let severity: EventSeverity
        
        enum EventType: String, Codable, CaseIterable {
            case cascadeStart = "cascade_start"
            case cascadeComplete = "cascade_complete"
            case cascadeError = "cascade_error"
            case fileOperation = "file_operation"
            case pluginExecution = "plugin_execution"
            case performanceMetric = "performance_metric"
            case systemHealth = "system_health"
            case userInteraction = "user_interaction"
        }
        
        enum EventCategory: String, Codable, CaseIterable {
            case cascade = "cascade"
            case performance = "performance"
            case system = "system"
            case user = "user"
            case plugin = "plugin"
            case error = "error"
        }
        
        enum EventSeverity: String, Codable, CaseIterable {
            case low = "low"
            case medium = "medium"
            case high = "high"
            case critical = "critical"
        }
    }
    
    // MARK: - Metrics Collection
    
    private func startMetricsCollection() {
        Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { _ in
            collectMetrics()
        }
    }
    
    private func collectMetrics() {
        var currentMetrics: [String: Any] = [:]
        
        // System metrics
        currentMetrics["timestamp"] = Date()
        currentMetrics["uptime"] = ProcessInfo.processInfo.systemUptime
        currentMetrics["memory_usage"] = getMemoryUsage()
        currentMetrics["cpu_usage"] = getCPUUsage()
        
        // Performance metrics
        currentMetrics["cache_hit_rate"] = PerformanceManager.shared.getPerformanceMetrics().cacheHitRate
        currentMetrics["average_response_time"] = PerformanceManager.shared.getPerformanceMetrics().averageResponseTime
        currentMetrics["active_connections"] = PerformanceManager.shared.getPerformanceMetrics().connectionPoolSize
        
        // System health metrics
        let healthMetrics = ErrorRecoveryManager.shared.getSystemHealth()
        currentMetrics["system_health_status"] = healthMetrics.status.rawValue
        currentMetrics["recent_error_count"] = healthMetrics.recentErrorCount
        currentMetrics["error_types"] = healthMetrics.errorTypes
        
        // Plugin metrics
        let pluginMetrics = PluginManager.shared.getPluginMetrics()
        currentMetrics["total_plugins"] = pluginMetrics.total
        currentMetrics["active_plugins"] = pluginMetrics.active
        currentMetrics["plugin_errors"] = pluginMetrics.errors
        
        // Configuration metrics
        let configAnalytics = ConfigurationManager.shared.getConfigAnalytics()
        currentMetrics["config_validation_errors"] = configAnalytics.validationErrors.count
        currentMetrics["enabled_features"] = configAnalytics.enabledFeatures.count
        currentMetrics["performance_impact"] = configAnalytics.performanceImpact.description
        currentMetrics["memory_footprint"] = configAnalytics.memoryFootprint
        
        // Update metrics
        metrics = currentMetrics
        metricsSubject.send(currentMetrics)
    }
    
    private func getMemoryUsage() -> Double {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size)/4
        
        let kerr: kern_return_t = withUnsafeMutablePointer(&info) {
            info.pointee = mach_task_basic_info()
            return task_info(mach_task_self_,
                          task_flavor_t(TASK_BASIC_INFO),
                          &info.pointee,
                          &count)
        }
        
        if kerr == KERN_SUCCESS {
            return Double(info.resident_size) / 1024.0 / 1024.0 // MB
        }
        return 0.0
    }
    
    private func getCPUUsage() -> Double {
        var info = processor_info_array_t(count: 1)
        var count = mach_msg_type_number_t(MemoryLayout<processor_info_array_t>.size)/4
        
        let kerr: kern_return_t = withUnsafeMutablePointer(&info) {
            return host_processor_info(mach_host_self(), PROCESSOR_INFO, &info, &count)
        }
        
        if kerr == KERN_SUCCESS {
            return Double(info.cpu_info.0.cpu_ticks.0) / 100.0
        }
        return 0.0
    }
    
    // MARK: - Event Logging
    
    func logEvent(_ event: AnalyticsEvent) {
        eventLog.append(event)
        
        // Keep only last 1000 events
        if eventLog.count > 1000 {
            eventLog.removeFirst(eventLog.count - 1000)
        }
        
        eventSubject.send(event)
        
        // Log to file if enabled
        if ConfigurationManager.shared.logging.enableLogging {
            logEventToFile(event)
        }
    }
    
    private func logEventToFile(_ event: AnalyticsEvent) {
        let logEntry = """
        {
            "timestamp": "\(ISO8601DateFormatter().string(from: event.timestamp))",
            "type": "\(event.type.rawValue)",
            "category": "\(event.category.rawValue)",
            "severity": "\(event.severity.rawValue)",
            "data": \(try! JSONSerialization.data(withJSONObject: event.data, options: .prettyPrinted))
        }
        """
        
        // Write to analytics log file
        let logFile = getAnalyticsLogFile()
        if let data = logEntry.data(using: .utf8) {
            if FileManager.default.fileExists(atPath: logFile.path) {
                if let fileHandle = try? FileHandle(forWritingTo: logFile) {
                    fileHandle.seekToEndOfFile()
                    fileHandle.write(data)
                    fileHandle.write("\n".data(using: .utf8) ?? Data())
                    fileHandle.closeFile()
                }
            } else {
                try? logEntry.write(to: logFile, atomically: true, encoding: .utf8)
            }
        }
    }
    
    private func getAnalyticsLogFile() -> URL {
        let configPath = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let analyticsDir = configPath.appendingPathComponent("atlastrinity").appendingPathComponent("analytics")
        
        try? FileManager.default.createDirectory(at: analyticsDir, withIntermediateDirectories: true)
        
        return analyticsDir.appendingPathComponent("analytics.jsonl")
    }
    
    // MARK: - Analytics Queries
    
    func getMetricsSummary() -> MetricsSummary {
        let currentMetrics = metrics
        let recentEvents = eventLog.suffix(100)
        
        return MetricsSummary(
            timestamp: currentMetrics["timestamp"] as? Date ?? Date(),
            uptime: currentMetrics["uptime"] as? TimeInterval ?? 0,
            memoryUsage: currentMetrics["memory_usage"] as? Double ?? 0,
            cpuUsage: currentMetrics["cpu_usage"] as? Double ?? 0,
            cacheHitRate: currentMetrics["cache_hit_rate"] as? Double ?? 0,
            averageResponseTime: currentMetrics["average_response_time"] as? TimeInterval ?? 0,
            systemHealthStatus: currentMetrics["system_health_status"] as? String ?? "unknown",
            recentErrorCount: currentMetrics["recent_error_count"] as? Int ?? 0,
            totalPlugins: currentMetrics["total_plugins"] as? Int ?? 0,
            activePlugins: currentMetrics["active_plugins"] as? Int ?? 0,
            recentEvents: Array(recentEvents),
            topErrors: getTopErrors(from: recentEvents),
            performanceTrends: calculatePerformanceTrends()
        )
    }
    
    struct MetricsSummary {
        let timestamp: Date
        let uptime: TimeInterval
        let memoryUsage: Double
        let cpuUsage: Double
        let cacheHitRate: Double
        let averageResponseTime: TimeInterval
        let systemHealthStatus: String
        let recentErrorCount: Int
        let totalPlugins: Int
        let activePlugins: Int
        let recentEvents: [AnalyticsEvent]
        let topErrors: [(String, Int)]
        let performanceTrends: PerformanceTrends
        
        var summary: String {
            return """
            📊 Analytics Dashboard Summary
            ═════════════════════════════════
            🕒 Last Updated: \(timestamp.formatted(date: .abbreviated, time: .shortened))
            ⏱️ Uptime: \(String(format: "%.1f", uptime / 3600))h
            💾 Memory Usage: \(String(format: "%.1f", memoryUsage))MB
            🖥️ CPU Usage: \(String(format: "%.1f", cpuUsage))%
            
            🚀 Performance Metrics:
            📈 Cache Hit Rate: \(String(format: "%.1f", cacheHitRate * 100))%
            ⏱️ Avg Response: \(String(format: "%.2f", averageResponseTime))s
            
            🏥️ System Health:
            📊 Status: \(systemHealthStatus)
            ❌ Recent Errors: \(recentErrorCount)
            
            🔌 Plugins:
            📦 Total: \(totalPlugins)
            ✅ Active: \(activePlugins)
            ❌ Errors: \(totalPlugins - activePlugins)
            
            📈 Performance Trends:
            \(performanceTrends.summary)
            """
        }
    }
    
    struct PerformanceTrends {
        let responseTimeTrend: TrendDirection
        let errorRateTrend: TrendDirection
        let throughputTrend: TrendDirection
        
        enum TrendDirection {
            case improving, stable, degrading
            
            var description: String {
                switch self {
                case .improving: return "📈 Improving"
                case .stable: return "➡️ Stable"
                case .degrading: return "📉 Degrading"
                }
            }
        }
        
        var summary: String {
            return """
            Response Time: \(responseTimeTrend.description)
            Error Rate: \(errorRateTrend.description)
            Throughput: \(throughputTrend.description)
            """
        }
    }
    
    private func getTopErrors(from events: [AnalyticsEvent]) -> [(String, Int)] {
        let errorEvents = events.filter { $0.type == .cascadeError || $0.type == .pluginExecution }
        var errorCounts: [String: Int] = [:]
        
        for event in errorEvents {
            let errorType = event.data["error"] as? String ?? "unknown"
            errorCounts[errorType, default: 0] += 1
        }
        
        return errorCounts.sorted { $0.value > $1.value }.prefix(5).map { ($0.key, $0.value) }
    }
    
    private func calculatePerformanceTrends() -> PerformanceTrends {
        let recentEvents = eventLog.suffix(50)
        let olderEvents = eventLog.dropLast(50).suffix(50)
        
        let recentResponseTimes = recentEvents.compactMap { $0.data["response_time"] as? TimeInterval }
        let olderResponseTimes = olderEvents.compactMap { $0.data["response_time"] as? TimeInterval }
        
        let recentErrorRate = Double(recentEvents.filter { $0.severity == .high || $0.severity == .critical }.count) / Double(recentEvents.count)
        let olderErrorRate = Double(olderEvents.filter { $0.severity == .high || $0.severity == .critical }.count) / Double(olderEvents.count)
        
        let responseTimeTrend = calculateTrend(recent: recentResponseTimes, older: olderResponseTimes)
        let errorRateTrend = calculateTrend(recent: recentErrorRate, older: olderErrorRate)
        let throughputTrend = calculateTrend(recent: Double(recentEvents.count), older: Double(olderEvents.count))
        
        return PerformanceTrends(
            responseTimeTrend: responseTimeTrend,
            errorRateTrend: errorRateTrend,
            throughputTrend: throughputTrend
        )
    }
    
    private func calculateTrend<T: Comparable>(recent: [T], older: [T]) -> PerformanceTrends.TrendDirection {
        guard !recent.isEmpty && !older.isEmpty else { return .stable }
        
        let recentAvg = recent.reduce(0, +) / Double(recent.count)
        let olderAvg = older.reduce(0, +) / Double(older.count)
        
        let difference = recentAvg - olderAvg
        let threshold = olderAvg * 0.1 // 10% threshold
        
        if difference > threshold {
            return .degrading
        } else if difference < -threshold {
            return .improving
        } else {
            return .stable
        }
    }
    
    // MARK: - Dashboard API
    
    func getDashboardData() -> DashboardData {
        let summary = getMetricsSummary()
        let recentEvents = eventLog.suffix(20)
        let performanceMetrics = PerformanceManager.shared.getPerformanceMetrics()
        let pluginMetrics = PluginManager.shared.getPluginMetrics()
        let healthMetrics = ErrorRecoveryManager.shared.getSystemHealth()
        
        return DashboardData(
            summary: summary,
            recentEvents: Array(recentEvents),
            performanceMetrics: performanceMetrics,
            pluginMetrics: pluginMetrics,
            healthMetrics: healthMetrics,
            charts: generateChartData()
        )
    }
    
    struct DashboardData {
        let summary: MetricsSummary
        let recentEvents: [AnalyticsEvent]
        let performanceMetrics: PerformanceManager.PerformanceMetrics
        let pluginMetrics: PluginManager.PluginMetrics
        let healthMetrics: ErrorRecoveryManager.SystemHealth
        let charts: [ChartData]
    }
    
    struct ChartData {
        let name: String
        let type: ChartType
        let data: [DataPoint]
        
        enum ChartType {
            case line
            case bar
            case pie
        }
        
        struct DataPoint {
            let timestamp: Date
            let value: Double
            let label: String?
        }
    }
    
    private func generateChartData() -> [ChartData] {
        var charts: [ChartData] = []
        
        // Response time chart
        let responseTimeEvents = eventLog.filter { $0.type == .cascadeComplete }
            .compactMap { event in
                ChartData.DataPoint(
                    timestamp: event.timestamp,
                    value: event.data["duration"] as? Double ?? 0,
                    label: nil
                )
            }
        
        if !responseTimeEvents.isEmpty {
            charts.append(ChartData(
                name: "Response Times",
                type: .line,
                data: Array(responseTimeEvents.suffix(50))
            ))
        }
        
        // Error rate chart
        let errorRateData = calculateErrorRateData()
        charts.append(ChartData(
            name: "Error Rate",
            type: .line,
            data: errorRateData
        ))
        
        // Plugin usage chart
        let pluginUsageData = generatePluginUsageData()
        charts.append(ChartData(
            name: "Plugin Usage",
            type: .bar,
            data: pluginUsageData
        ))
        
        return charts
    }
    
    private func calculateErrorRateData() -> [ChartData.DataPoint] {
        let timeWindow: TimeInterval = 3600 // 1 hour
        let now = Date()
        let windowStart = now.addingTimeInterval(-timeWindow)
        
        let eventsInWindow = eventLog.filter { $0.timestamp >= windowStart }
        let bucketSize: TimeInterval = 300 // 5 minutes
        let bucketCount = Int(timeWindow / bucketSize)
        
        var dataPoints: [ChartData.DataPoint] = []
        
        for i in 0..<bucketCount {
            let bucketStart = windowStart.addingTimeInterval(TimeInterval(i) * bucketSize)
            let bucketEnd = bucketStart.addingTimeInterval(bucketSize)
            
            let eventsInBucket = eventsInWindow.filter { $0.timestamp >= bucketStart && $0.timestamp < bucketEnd }
            let errorCount = eventsInBucket.filter { $0.severity == .high || $0.severity == .critical }.count
            let errorRate = eventsInBucket.isEmpty ? 0.0 : Double(errorCount) / Double(eventsInBucket.count)
            
            dataPoints.append(ChartData.DataPoint(
                timestamp: bucketStart,
                value: errorRate,
                label: nil
            ))
        }
        
        return dataPoints
    }
    
    private func generatePluginUsageData() -> [ChartData.DataPoint] {
        let pluginMetrics = PluginManager.shared.getPluginMetrics()
        
        return [
            ChartData.DataPoint(timestamp: Date(), value: Double(pluginMetrics.active), label: "Active"),
            ChartData.DataPoint(timestamp: Date(), value: Double(pluginMetrics.loaded), label: "Loaded"),
            ChartData.DataPoint(timestamp: Date(), value: Double(pluginMetrics.errors), label: "Errors")
        ]
    }
}

// MARK: - Extensions

extension AnalyticsDashboard.AnalyticsEvent.EventType: Codable {}
extension AnalyticsDashboard.AnalyticsEvent.Category: Codable {}
extension AnalyticsDashboard.AnalyticsEvent.Severity: Codable {}

// MARK: - System Imports

import Darwin
import MachO
