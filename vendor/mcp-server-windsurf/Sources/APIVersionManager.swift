import Foundation

/// API versioning errors
enum APIVersionError: Error, LocalizedError {
    case invalidVersionString(String)
    case unsupportedVersion(APIVersion)
    case versionNegotiationFailed

    var errorDescription: String? {
        switch self {
        case .invalidVersionString(let version):
            return "Invalid version string: \(version)"
        case .unsupportedVersion(let version):
            return "Unsupported version: \(version.versionString)"
        case .versionNegotiationFailed:
            return "Version negotiation failed"
        }
    }
}

/// Represents an API version
struct APIVersion: Codable, Hashable, Comparable {
    let major: Int
    let minor: Int
    let patch: Int
    let preRelease: String?
    let buildMetadata: String?

    static let latest = APIVersion(
        major: 1, minor: 0, patch: 0, preRelease: nil, buildMetadata: nil)

    var versionString: String {
        var version = "\(major).\(minor).\(patch)"
        if let preRelease = preRelease {
            version += "-\(preRelease)"
        }
        if let buildMetadata = buildMetadata {
            version += "+\(buildMetadata)"
        }
        return version
    }

    static func < (lhs: APIVersion, rhs: APIVersion) -> Bool {
        if lhs.major != rhs.major {
            return lhs.major < rhs.major
        }
        if lhs.minor != rhs.minor {
            return lhs.minor < rhs.minor
        }
        if lhs.patch != rhs.patch {
            return lhs.patch < rhs.patch
        }
        return false
    }

    func isCompatible(with other: APIVersion) -> Bool {
        if major != other.major {
            return false
        }
        if minor > other.minor {
            return false
        }
        return true
    }

    func isNewer(than other: APIVersion) -> Bool {
        if major != other.major {
            return major > other.major
        }
        if minor != other.minor {
            return minor > other.minor
        }
        if patch != other.patch {
            return patch > other.patch
        }
        return false
    }
}

/// Version policy for a specific API version
struct VersionPolicy {
    let version: APIVersion
    let deprecationDate: Date?
    let supportEndDate: Date?
    let migrationRequired: Bool
    let breakingChanges: Bool
    let policyType: PolicyType

    enum PolicyType: CustomStringConvertible {
        case stable
        case deprecated
        case legacy
        case experimental

        var description: String {
            switch self {
            case .stable: return "Stable"
            case .deprecated: return "Deprecated"
            case .legacy: return "Legacy"
            case .experimental: return "Experimental"
            }
        }
    }

    var status: PolicyStatus {
        let now = Date()

        if let deprecationDate = deprecationDate, now >= deprecationDate {
            if let supportEndDate = supportEndDate, now >= supportEndDate {
                return .unsupported
            } else {
                return .deprecated
            }
        } else {
            switch policyType {
            case .stable: return .supported
            case .deprecated: return .supported
            case .legacy: return .supported
            case .experimental: return .supported
            }
        }
    }

    enum PolicyStatus: CustomStringConvertible {
        case supported
        case deprecated
        case unsupported

        var description: String {
            switch self {
            case .supported: return "Supported"
            case .deprecated: return "Deprecated"
            case .unsupported: return "Unsupported"
            }
        }
    }
}

/// Result of version validation
struct ValidationResult {
    let isValid: Bool
    let errors: [String]
    let warnings: [String]
    let recommendedVersion: APIVersion?
}

/// Migration step information
struct MigrationStep {
    let type: MigrationType
    let description: String
    let instructions: [String]
    let estimatedTime: TimeInterval
    let requiresDowntime: Bool

    enum MigrationType: CustomStringConvertible {
        case majorUpgrade
        case minorUpgrade
        case patchUpgrade
        case configurationUpdate
        case dataMigration

        var description: String {
            switch self {
            case .majorUpgrade: return "Major Version Upgrade"
            case .minorUpgrade: return "Minor Version Upgrade"
            case .patchUpgrade: return "Patch Version Upgrade"
            case .configurationUpdate: return "Configuration Update"
            case .dataMigration: return "Data Migration"
            }
        }
    }
}

/// Full migration path between two versions
struct MigrationPath {
    let fromVersion: APIVersion
    let toVersion: APIVersion
    let steps: [MigrationStep]
    let estimatedTime: TimeInterval
    let requiresDowntime: Bool

    var summary: String {
        var summary =
            "Migration Path: v\(fromVersion.versionString) → v\(toVersion.versionString)\n"
        summary += "Steps: \(steps.count)\n"
        summary += "Estimated Time: \(formatDuration(estimatedTime))\n"
        summary += "Requires Downtime: \(requiresDowntime ? "Yes" : "No")"
        return summary
    }
}

/// Result of version negotiation
struct NegotiationResult {
    let selectedVersion: APIVersion?
    let serverVersion: APIVersion
    let supportedVersions: [APIVersion]
    let negotiationType: NegotiationType

    enum NegotiationType: CustomStringConvertible {
        case current
        case upgradeAvailable
        case downgradeRequired
        case noCompatibleVersion

        var description: String {
            switch self {
            case .current: return "Current"
            case .upgradeAvailable: return "Upgrade Available"
            case .downgradeRequired: return "Downgrade Required"
            case .noCompatibleVersion: return "No Compatible Version"
            }
        }
    }

    var summary: String {
        var summary = "Version Negotiation Result:\n"
        if let selected = selectedVersion {
            summary += "Selected: v\(selected.versionString)\n"
        } else {
            summary += "No compatible version found\n"
        }
        summary += "Server: v\(serverVersion.versionString)\n"
        summary +=
            "Supported: \(supportedVersions.map { "v\($0.versionString)" }.joined(separator: ", "))\n"
        summary += "Type: \(negotiationType)\n"
        return summary
    }
}

/// Version info summary
struct VersionInfo {
    let currentVersion: APIVersion
    let supportedVersions: [APIVersion]
    let versionPolicies: [VersionPolicy]
    let buildDate: Date
    let gitCommit: String?
    let buildNumber: String?

    var summary: String {
        var summary = "Windsurf MCP Version Information\n"
        summary += "══════════════════════════════════\n"
        summary += "Current: v\(currentVersion.versionString)\n"
        summary += "Supported: \(supportedVersions.count) versions\n"
        summary += "Build: \(buildDate.formatted(date: .abbreviated, time: .shortened))\n"

        if let commit = gitCommit {
            summary += "Commit: \(commit.prefix(8))\n"
        }

        if let build = buildNumber {
            summary += "Build: \(build)\n"
        }

        summary += "\nVersion Policies:\n"
        for policy in versionPolicies {
            summary +=
                "v\(policy.version.versionString): \(policy.policyType.description) - \(policy.status.description)\n"
        }

        return summary
    }
}

/// Deprecation warning details
struct DeprecationWarning {
    let version: APIVersion
    let deprecationDate: Date
    let daysUntilDeprecation: Int
    let recommendedAction: String

    var summary: String {
        return """
            ⚠️ Deprecation Warning
            Version: v\(version.versionString)
            Deprecated on: \(deprecationDate.formatted(date: .abbreviated, time: .shortened))
            Days Left: \(daysUntilDeprecation)
            Action: \(recommendedAction)
            """
    }
}

/// Feature compatibility matrix
struct CompatibilityMatrix {
    let versions: [APIVersion]
    let features: [String]
    let matrix: [String: [String: CompatibilityStatus]]

    var summary: String {
        var summary = "Feature Compatibility Matrix\n"
        summary += "══════════════════════════════════\n"

        // Header row
        summary += "Version |"
        for feature in features {
            summary += " \(feature.paddingForComparison(toLength: 20)) |"
        }
        summary += "\n"

        // Data rows
        for version in versions {
            summary += "v\(version.versionString.paddingForComparison(toLength: 10)) |"

            for feature in features {
                let status = matrix[version.versionString]?[feature] ?? .notSupported
                let statusIcon = status.icon
                summary += " \(statusIcon.paddingForComparison(toLength: 20)) |"
            }
            summary += "\n"
        }

        return summary
    }
}

/// Compatibility status for a feature
enum CompatibilityStatus: CustomStringConvertible {
    case supported
    case notSupported
    case deprecated
    case experimental

    var description: String {
        switch self {
        case .supported: return "Supported"
        case .notSupported: return "Not Supported"
        case .deprecated: return "Deprecated"
        case .experimental: return "Experimental"
        }
    }

    var icon: String {
        switch self {
        case .supported: return "✅"
        case .notSupported: return "❌"
        case .deprecated: return "⚠️"
        case .experimental: return "🧪"
        }
    }
}

/// Feature flags
enum FeatureFlag: String, CaseIterable, CustomStringConvertible {
    case cascadeActionPhase = "cascade_action_phase"
    case realTimeStreaming = "real_time_streaming"
    case pluginSystem = "plugin_system"
    case advancedCaching = "advanced_caching"
    case configurationManagement = "configuration_management"
    case analyticsDashboard = "analytics_dashboard"
    case errorRecovery = "error_recovery"
    case workspaceManagement = "workspace_management"
    case protobufFieldExperiments = "protobuf_field_experiments"

    var description: String {
        return self.rawValue.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

/// API versioning strategy for Windsurf MCP Provider
class APIVersionManager {
    static let shared = APIVersionManager()

    public let currentVersion: APIVersion
    private var supportedVersions: [APIVersion]
    private var versionPolicies: [VersionPolicy]

    private init() {
        self.currentVersion = APIVersion(
            major: 1, minor: 0, patch: 0, preRelease: nil, buildMetadata: nil)

        self.supportedVersions = [
            currentVersion,
            APIVersion(major: 0, minor: 9, patch: 0, preRelease: nil, buildMetadata: nil),
            APIVersion(major: 0, minor: 8, patch: 5, preRelease: nil, buildMetadata: nil),
        ]

        self.versionPolicies = [
            VersionPolicy(
                version: APIVersion(
                    major: 1, minor: 0, patch: 0, preRelease: nil, buildMetadata: nil),
                deprecationDate: nil,
                supportEndDate: nil,
                migrationRequired: false,
                breakingChanges: false,
                policyType: .stable
            ),
            VersionPolicy(
                version: APIVersion(
                    major: 0, minor: 9, patch: 0, preRelease: nil, buildMetadata: nil),
                deprecationDate: Date().addingTimeInterval(86400 * 30),
                supportEndDate: Date().addingTimeInterval(86400 * 90),
                migrationRequired: false,
                breakingChanges: false,
                policyType: .deprecated
            ),
            VersionPolicy(
                version: APIVersion(
                    major: 0, minor: 8, patch: 5, preRelease: nil, buildMetadata: nil),
                deprecationDate: Date().addingTimeInterval(86400 * 60),
                supportEndDate: Date().addingTimeInterval(86400 * 120),
                migrationRequired: true,
                breakingChanges: true,
                policyType: .legacy
            ),
        ]
    }

    // MARK: - Version Validation

    func validateVersion(_ version: APIVersion) -> ValidationResult {
        guard supportedVersions.contains(version) else {
            return ValidationResult(
                isValid: false,
                errors: ["Unsupported version: \(version.versionString)"],
                warnings: [],
                recommendedVersion: currentVersion
            )
        }

        var errors: [String] = []
        var warnings: [String] = []

        if let policy = versionPolicies.first(where: { $0.version == version }) {
            switch policy.status {
            case .unsupported:
                errors.append("Version \(version.versionString) is no longer supported")
            case .deprecated:
                if let deprecationDate = policy.deprecationDate {
                    warnings.append(
                        "Version \(version.versionString) is deprecated (deprecated on \(deprecationDate))"
                    )
                }
            case .supported:
                break
            }

            if policy.breakingChanges {
                warnings.append("Version \(version.versionString) contains breaking changes")
            }
        }

        if version.isNewer(than: currentVersion) {
            warnings.append(
                "Version \(version.versionString) is newer than current version \(currentVersion.versionString)"
            )
        }

        return ValidationResult(
            isValid: errors.isEmpty,
            errors: errors,
            warnings: warnings,
            recommendedVersion: errors.isEmpty ? currentVersion : nil
        )
    }

    // MARK: - Migration Support

    func getMigrationPath(from fromVersion: APIVersion, to toVersion: APIVersion) -> MigrationPath?
    {
        guard validateVersion(toVersion).isValid else {
            return nil
        }

        let migrationSteps = generateMigrationSteps(from: fromVersion, to: toVersion)

        return MigrationPath(
            fromVersion: fromVersion,
            toVersion: toVersion,
            steps: migrationSteps,
            estimatedTime: estimateMigrationTime(steps: migrationSteps),
            requiresDowntime: migrationSteps.contains { $0.requiresDowntime }
        )
    }

    private func generateMigrationSteps(from: APIVersion, to: APIVersion) -> [MigrationStep] {
        var steps: [MigrationStep] = []
        if from.major < to.major {
            steps.append(
                MigrationStep(
                    type: .majorUpgrade,
                    description:
                        "Upgrade from v\(from.major).\(from.minor) to v\(to.major).\(to.minor)",
                    instructions: ["Backup", "Review changes", "Deploy"],
                    estimatedTime: 3600,
                    requiresDowntime: true
                ))
        } else if from.minor < to.minor {
            steps.append(
                MigrationStep(
                    type: .minorUpgrade,
                    description: "Upgrade to v\(to.major).\(to.minor)",
                    instructions: ["Update config", "Test"],
                    estimatedTime: 900,
                    requiresDowntime: false
                ))
        }
        return steps
    }

    private func estimateMigrationTime(steps: [MigrationStep]) -> TimeInterval {
        return steps.reduce(0) { $0 + $1.estimatedTime }
    }

    // MARK: - Versioning Headers

    func setAPIVersionHeaders(for request: inout URLRequest, version: APIVersion? = nil) {
        let version = version ?? currentVersion
        request.setValue(
            "application/vnd.windsurf-mcp.v\(version.major).\(version.minor)+json",
            forHTTPHeaderField: "Accept")
        request.setValue("windsurf-mcp-api-version", forHTTPHeaderField: "X-API-Version")
        request.setValue(version.versionString, forHTTPHeaderField: "X-Windsurf-Version")
    }

    public func parseVersionString(_ version: String) throws -> APIVersion {
        let components = version.components(separatedBy: ".")
        guard components.count >= 3,
            let major = Int(components[0]),
            let minor = Int(components[1]),
            let patch = Int(components[2])
        else {
            throw APIVersionError.invalidVersionString(version)
        }
        return APIVersion(
            major: major, minor: minor, patch: patch, preRelease: nil, buildMetadata: nil)
    }

    // MARK: - Negotiation

    func negotiateVersion(clientSupportedVersions: [APIVersion]) -> NegotiationResult {
        let compatibleVersions = clientSupportedVersions.filter {
            currentVersion.isCompatible(with: $0)
        }
        guard let selectedVersion = compatibleVersions.max() else {
            return NegotiationResult(
                selectedVersion: nil,
                serverVersion: currentVersion,
                supportedVersions: supportedVersions,
                negotiationType: .noCompatibleVersion
            )
        }

        let type: NegotiationResult.NegotiationType
        if selectedVersion == currentVersion {
            type = .current
        } else if selectedVersion.isNewer(than: currentVersion) {
            type = .upgradeAvailable
        } else {
            type = .downgradeRequired
        }

        return NegotiationResult(
            selectedVersion: selectedVersion,
            serverVersion: currentVersion,
            supportedVersions: supportedVersions,
            negotiationType: type
        )
    }

    // MARK: - Information

    func getVersionInfo() -> VersionInfo {
        return VersionInfo(
            currentVersion: currentVersion,
            supportedVersions: supportedVersions,
            versionPolicies: versionPolicies,
            buildDate: Date(),
            gitCommit: getGitCommit(),
            buildNumber: getBuildNumber()
        )
    }

    private func getGitCommit() -> String? {
        // Implementation omitted for brevity or use previous one
        return nil
    }

    private func getBuildNumber() -> String? {
        return ProcessInfo.processInfo.environment["BUILD_NUMBER"]
    }

    // MARK: - Deprecation

    func checkDeprecationWarnings() -> [DeprecationWarning] {
        var warnings: [DeprecationWarning] = []
        for policy in versionPolicies {
            if case .deprecated = policy.status, let date = policy.deprecationDate {
                let days = Int(date.timeIntervalSinceNow / 86400)
                warnings.append(
                    DeprecationWarning(
                        version: policy.version,
                        deprecationDate: date,
                        daysUntilDeprecation: days,
                        recommendedAction: "Upgrade to v\(currentVersion.versionString)"
                    ))
            }
        }
        return warnings
    }

    // MARK: - Features

    func isFeatureEnabled(_ feature: FeatureFlag, version: APIVersion? = nil) -> Bool {
        let target = version ?? currentVersion
        return target.major >= 1
    }

    func getCompatibilityMatrix() -> CompatibilityMatrix {
        var matrix: [String: [String: CompatibilityStatus]] = [:]
        let features = FeatureFlag.allCases
        for version in supportedVersions {
            var versionComp: [String: CompatibilityStatus] = [:]
            for feature in features {
                versionComp[feature.rawValue] =
                    isFeatureEnabled(feature, version: version) ? .supported : .notSupported
            }
            matrix[version.versionString] = versionComp
        }
        return CompatibilityMatrix(
            versions: supportedVersions,
            features: features.map { $0.rawValue },
            matrix: matrix
        )
    }
}

// MARK: - Helpers

extension String {
    func paddingForComparison(toLength: Int) -> String {
        return self.padding(toLength: toLength, withPad: " ", startingAt: 0)
    }
}

extension Date {
    func formatted(date: DateFormatter.Style, time: DateFormatter.Style) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = date
        formatter.timeStyle = time
        return formatter.string(from: self)
    }
}

func formatDuration(_ duration: TimeInterval) -> String {
    let formatter = DateComponentsFormatter()
    formatter.allowedUnits = [.hour, .minute, .second]
    formatter.unitsStyle = .abbreviated
    return formatter.string(from: duration) ?? "\(Int(duration))s"
}
