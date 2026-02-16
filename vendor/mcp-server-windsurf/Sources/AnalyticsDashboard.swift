import Combine
import Darwin
import Foundation
import MCP

/// A simple wrapper for Codable values in dictionaries
enum CodableValue: Codable {
    case string(String)
    case double(Double)
    case int(Int)
    case bool(Bool)

    init(_ value: Any) {
        if let s = value as? String {
            self = .string(s)
        } else if let d = value as? Double {
            self = .double(d)
        } else if let i = value as? Int {
            self = .int(i)
        } else if let b = value as? Bool {
            self = .bool(b)
        } else {
            self = .string("\(value)")
        }
    }

    var doubleValue: Double? {
        switch self {
        case .double(let d): return d
        case .int(let i): return Double(i)
        case .string(let s): return Double(s)
        default: return nil
        }
    }

    var stringValue: String {
        switch self {
        case .string(let s): return s
        case .double(let d): return "\(d)"
        case .int(let i): return "\(i)"
        case .bool(let b): return "\(b)"
        }
    }
}

/// Advanced analytics dashboard for Windsurf MCP
class AnalyticsDashboard {
    static let shared = AnalyticsDashboard()

    private var metrics: [String: CodableValue] = [:]
    private var eventLog: [AnalyticsEvent] = []
    private let metricsSubject = PassthroughSubject<[String: CodableValue], Never>()
    private let eventSubject = PassthroughSubject<AnalyticsEvent, Never>()

    var metricsPublisher: AnyPublisher<[String: CodableValue], Never> {
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
        let data: [String: CodableValue]
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
        Timer.scheduledTimer(withTimeInterval: 30.0, repeats: true) { [weak self] _ in
            self?.collectMetrics()
        }
    }

    private func collectMetrics() {
        var currentMetrics: [String: CodableValue] = [:]

        currentMetrics["timestamp"] = CodableValue(Date())
        currentMetrics["uptime"] = CodableValue(ProcessInfo.processInfo.systemUptime)
        currentMetrics["memory_usage"] = CodableValue(getMemoryUsage())
        currentMetrics["cpu_usage"] = CodableValue(getCPUUsage())

        let perf = GlobalState.performanceManager.getPerformanceMetrics()
        currentMetrics["cache_hit_rate"] = CodableValue(perf.cacheHitRate)
        currentMetrics["average_response_time"] = CodableValue(perf.averageResponseTime)
        currentMetrics["active_connections"] = CodableValue(perf.connectionPoolSize)

        let health = GlobalState.errorRecoveryManager.getSystemHealth()
        currentMetrics["system_health_status"] = CodableValue(health.status.rawValue)
        currentMetrics["recent_error_count"] = CodableValue(health.recentErrorCount)

        metrics = currentMetrics
        metricsSubject.send(currentMetrics)
    }

    private func getMemoryUsage() -> Double {
        var info = mach_task_basic_info()
        var count = mach_msg_type_number_t(MemoryLayout<mach_task_basic_info>.size) / 4
        let kerr = withUnsafeMutablePointer(to: &info) { infoPtr in
            infoPtr.withMemoryRebound(to: integer_t.self, capacity: Int(count)) { intPtr in
                task_info(mach_task_self_, task_flavor_t(MACH_TASK_BASIC_INFO), intPtr, &count)
            }
        }
        return kerr == KERN_SUCCESS ? Double(info.resident_size) / 1024.0 / 1024.0 : 0.0
    }

    private func getCPUUsage() -> Double {
        var numCPUs: natural_t = 0
        var cpuInfo: processor_info_array_t?
        var numCpuInfo: mach_msg_type_number_t = 0
        let result = host_processor_info(
            mach_host_self(), PROCESSOR_CPU_LOAD_INFO, &numCPUs, &cpuInfo, &numCpuInfo)

        if result == KERN_SUCCESS, let cpuInfo = cpuInfo {
            // Simplified CPU usage - for production use a more accurate delta-based calculation
            vm_deallocate(
                mach_task_self_, vm_address_t(bitPattern: cpuInfo),
                vm_size_t(numCpuInfo) * vm_size_t(MemoryLayout<integer_t>.size))
            return 5.0  // Placeholder or implement full logic
        }
        return 0.0
    }

    func logEvent(_ event: AnalyticsEvent) {
        eventLog.append(event)
        if eventLog.count > 1000 { eventLog.removeFirst() }
        eventSubject.send(event)
    }

    // MARK: - Trends

    func getMetricsSummary() -> MetricsSummary {
        return MetricsSummary(
            timestamp: metrics["timestamp"]?.doubleValue.map { Date(timeIntervalSince1970: $0) }
                ?? Date(),
            uptime: metrics["uptime"]?.doubleValue ?? 0,
            memoryUsage: metrics["memory_usage"]?.doubleValue ?? 0,
            cpuUsage: metrics["cpu_usage"]?.doubleValue ?? 0,
            cacheHitRate: metrics["cache_hit_rate"]?.doubleValue ?? 0,
            averageResponseTime: metrics["average_response_time"]?.doubleValue ?? 0,
            systemHealthStatus: metrics["system_health_status"]?.stringValue ?? "unknown",
            recentErrorCount: metrics["recent_error_count"]?.doubleValue.map { Int($0) } ?? 0,
            totalPlugins: 0,
            activePlugins: 0,
            recentEvents: Array(eventLog.suffix(100)),
            topErrors: [],
            performanceTrends: calculatePerformanceTrends()
        )
    }

    private func calculatePerformanceTrends() -> PerformanceTrends {
        return PerformanceTrends(
            responseTimeTrend: .stable, errorRateTrend: .stable, throughputTrend: .stable)
    }
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
    let recentEvents: [AnalyticsDashboard.AnalyticsEvent]
    let topErrors: [(String, Int)]
    let performanceTrends: PerformanceTrends

    var summary: String {
        return "Analytics Summary: \(systemHealthStatus), \(recentErrorCount) errors"
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
            case .improving: return "Improving"
            case .stable: return "Stable"
            case .degrading: return "Degrading"
            }
        }
    }
    var summary: String { return "Trends: \(responseTimeTrend.description)" }
}

struct DashboardData {
    let summary: MetricsSummary
    let recentEvents: [AnalyticsDashboard.AnalyticsEvent]
}
