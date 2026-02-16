import Foundation

/// API versioning strategy for Windsurf MCP Provider
class APIVersionManager {
    static let shared = APIVersionManager()
    
    private let currentVersion: APIVersion
    private var supportedVersions: [APIVersion]
    private var versionPolicies: [VersionPolicy]
    
    private init() {
        self.currentVersion = APIVersion(
            major: 1,
            minor: 0,
            patch: 0,
            preRelease: nil,
            buildMetadata: nil
        )
        
        self.supportedVersions = [
            currentVersion,
            APIVersion(major: 0, minor: 9, patch: 0),
            APIVersion(major: 0, minor: 8, patch: 5)
        ]
        
        self.versionPolicies = [
            VersionPolicy(
                version: APIVersion(major: 1, minor: 0, patch: 0),
                deprecationDate: nil,
                supportEndDate: nil,
                migrationRequired: false,
                breakingChanges: false,
                policyType: .stable
            ),
            VersionPolicy(
                version: APIVersion(major: 0, minor: 9, patch: 0),
                deprecationDate: Date().addingTimeInterval(86400 * 30), // 30 days
                supportEndDate: Date().addingTimeInterval(86400 * 90), // 90 days
                migrationRequired: false,
                breakingChanges: false,
                policyType: .deprecated
            ),
            VersionPolicy(
                version: APIVersion(major: 0, minor: 8, patch: 5),
                deprecationDate: Date().addingTimeInterval(86400 * 60), // 60 days
                supportEndDate: Date().addingTimeInterval(86400 * 120), // 120 days
                migrationRequired: true,
                breakingChanges: true,
                policyType: .legacy
            )
        ]
    }
    
    // MARK: - Version Management
    
    struct APIVersion: Codable, Hashable, Comparable {
        let major: Int
        let minor: Int
        let patch: Int
        let preRelease: String?
        let buildMetadata: String?
        
        static let latest = APIVersion(major: 1, minor: 0, patch: 0)
        
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
    
    struct VersionPolicy {
        let version: APIVersion
        let deprecationDate: Date?
        let supportEndDate: Date?
        let migrationRequired: Bool
        let breakingChanges: Bool
        let policyType: PolicyType
        
        enum PolicyType {
            case stable
            case deprecated
            case legacy
            case experimental
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
                case .stable:
                    return .supported
                case .deprecated:
                    return .supported
                case .legacy:
                    return .supported
                case .experimental:
                    return .supported
                }
            }
        }
        
        enum PolicyStatus {
            case supported
            case deprecated
            case unsupported
        }
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
        
        // Check version policy
        if let policy = versionPolicies.first(where: { $0.version == version }) {
            switch policy.status {
            case .unsupported:
                errors.append("Version \(version.versionString) is no longer supported")
            case .deprecated:
                if let deprecationDate = policy.deprecationDate {
                    warnings.append("Version \(version.versionString) is deprecated (deprecated on \(deprecationDate))")
                }
            case .supported:
                break // No issues
            }
            
            if policy.breakingChanges {
                warnings.append("Version \(version.versionString) contains breaking changes")
            }
        }
        
        // Check for newer versions
        if version.isNewer(than: currentVersion) {
            warnings.append("Version \(version.versionString) is newer than current version \(currentVersion.versionString)")
        }
        
        return ValidationResult(
            isValid: errors.isEmpty,
            errors: errors,
            warnings: warnings,
            recommendedVersion: errors.isEmpty ? currentVersion : nil
        )
    }
    
    struct ValidationResult {
        let isValid: Bool
        let errors: [String]
        let warnings: [String]
        let recommendedVersion: APIVersion?
    }
    
    // MARK: - Migration Support
    
    func getMigrationPath(from fromVersion: APIVersion, to toVersion: APIVersion) -> MigrationPath? {
        guard validateVersion(toVersion).isValid else {
            return nil
        }
        
        let migrationSteps = generateMigrationSteps(from: fromVersion, to: toVersion)
        
        return MigrationPath(
            fromVersion: fromVersion,
            toVersion: toVersion,
            steps: migrationSteps,
            estimatedTime: estimateMigrationTime(steps: migrationSteps),
            requiresDowntime: requiresDowntimeForMigration(from: fromVersion, to: toVersion)
        )
    }
    
    private func generateMigrationSteps(from: APIVersion, to: APIVersion) -> [MigrationStep] {
        var steps: [MigrationStep] = []
        
        // Major version upgrade
        if from.major < to.major {
            steps.append(MigrationStep(
                type: .majorUpgrade,
                description: "Upgrade from v\(from.major).\(from.minor) to v\(to.major).\(to.minor)",
                instructions: [
                    "Backup current configuration",
                    "Review breaking changes",
                    "Update dependencies",
                    "Test in staging environment",
                    "Deploy to production"
                ],
                estimatedTime: 60 * 60, // 1 hour
                requiresDowntime: true
            ))
        }
        
        // Minor version upgrade
        if from.minor < to.minor && from.major == to.major {
            steps.append(MigrationStep(
                type: .minorUpgrade,
                description: "Upgrade from v\(from.major).\(from.minor) to v\(to.major).\(to.minor)",
                instructions: [
                    "Review new features",
                    "Update configuration if needed",
                    "Test new functionality"
                ],
                estimatedTime: 15 * 60, // 15 minutes
                requiresDowntime: false
            ))
        }
        
        // Patch upgrade
        if from.patch < to.patch && from.minor == to.minor && from.major == to.major {
            steps.append(MigrationStep(
                type: .patchUpgrade,
                description: "Upgrade from v\(from.major).\(from.minor).\(from.patch) to v\(to.major).\(to.minor).\(to.patch)",
                instructions: [
                    "Apply patch updates"
                ],
                estimatedTime: 5 * 60, // 5 minutes
                requiresDowntime: false
            ))
        }
        
        return steps
    }
    
    private func estimateMigrationTime(steps: [MigrationStep]) -> TimeInterval {
        return steps.reduce(0) { $0 + $1.estimatedTime }
    }
    
    private func requiresDowntimeForMigration(from: APIVersion, to: APIVersion) -> Bool {
        return steps.contains { $0.requiresDowntime }
    }
    
    struct MigrationPath {
        let fromVersion: APIVersion
        let toVersion: APIVersion
        let steps: [MigrationStep]
        let estimatedTime: TimeInterval
        let requiresDowntime: Bool
        
        var summary: String {
            var summary = "Migration Path: v\(fromVersion.versionString) → v\(toVersion.versionString)\n"
            summary += "Steps: \(steps.count)\n"
            summary += "Estimated Time: \(formatDuration(estimatedTime))\n"
            summary += "Requires Downtime: \(requiresDowntime ? "Yes" : "No")"
            return summary
        }
    }
    
    struct MigrationStep {
        let type: MigrationType
        let description: String
        let instructions: [String]
        let estimatedTime: TimeInterval
        let requiresDowntime: Bool
        
        enum MigrationType {
            case majorUpgrade
            case minorUpgrade
            case patchUpgrade
            case configurationUpdate
            case dataMigration
        }
    }
    
    // MARK: - API Versioning Headers
    
    func setAPIVersionHeaders(for request: inout URLRequest, version: APIVersion? = nil) {
        let version = version ?? currentVersion
        
        request.setValue("application/vnd.windsurf-mcp.v\(version.major).\(version.minor)+json", forHTTPHeaderField: "Accept")
        request.setValue("windsurf-mcp-api-version", forHTTPHeaderField: "X-API-Version")
        request.setValue(version.versionString, forHTTPHeaderField: "X-Windsurf-Version")
    }
    
    func parseAPIVersion(from request: URLRequest) -> APIVersion? {
        guard let versionString = request.value(forHTTPHeaderField: "X-Windsurf-Version") else {
            return nil
        }
        
        return parseVersionString(versionString)
    }
    
    private func parseVersionString(_ versionString: String) -> APIVersion? {
        let components = versionString.components(separatedBy: ".")
        guard components.count >= 3 else { return nil }
        
        guard let major = Int(components[0]),
              let minor = Int(components[1]),
              let patch = Int(components[2]) else { return nil }
        
        let preReleaseAndBuild = components.count > 3 ? components[3].components(separatedBy: "+") : []
        let preRelease = preReleaseAndBuild.count > 0 ? preReleaseAndBuild[0] : nil
        let buildMetadata = preReleaseAndBuild.count > 1 ? preReleaseAndBuild[1] : nil
        
        return APIVersion(
            major: major,
            minor: minor,
            patch: patch,
            preRelease: preRelease,
            buildMetadata: buildMetadata
        )
    }
    
    // MARK: - Version Negotiation
    
    func negotiateVersion(clientSupportedVersions: [APIVersion]) -> NegotiationResult {
        // Find the highest version that both client and server support
        let compatibleVersions = clientSupportedVersions.filter { currentVersion.isCompatible(with: $0) }
        
        guard let selectedVersion = compatibleVersions.max() else {
            return NegotiationResult(
                selectedVersion: nil,
                serverVersion: currentVersion,
                supportedVersions: supportedVersions,
                negotiationType: .noCompatibleVersion
            )
        }
        
        let negotiationType: NegotiationType
        if selectedVersion == currentVersion {
            negotiationType = .current
        } else if selectedVersion.isNewer(than: currentVersion) {
            negotiationType = .upgradeAvailable
        } else {
            negotiationType = .downgradeRequired
        }
        
        return NegotiationResult(
            selectedVersion: selectedVersion,
            serverVersion: currentVersion,
            supportedVersions: supportedVersions,
            negotiationType: negotiationType
        )
    }
    
    struct NegotiationResult {
        let selectedVersion: APIVersion?
        let serverVersion: APIVersion
        let supportedVersions: [APIVersion]
        let negotiationType: NegotiationType
        
        enum NegotiationType {
            case current
            case upgradeAvailable
            case downgradeRequired
            case noCompatibleVersion
        }
        
        var summary: String {
            var summary = "Version Negotiation Result:\n"
            
            if let selected = selectedVersion {
                summary += "Selected: v\(selected.versionString)\n"
            } else {
                summary += "No compatible version found\n"
            }
            
            summary += "Server: v\(serverVersion.versionString)\n"
            summary += "Supported: \(supportedVersions.map { "v\($0.versionString)" }.joined(", "))\n"
            summary += "Type: \(negotiationType)\n"
            
            return summary
        }
    }
    
    // MARK: - Version Information
    
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
                summary += "v\(policy.version.versionString): \(policy.policyType.description) - \(policy.status.description)\n"
            }
            
            return summary
        }
    }
    
    private func getGitCommit() -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["rev-parse", "HEAD"]
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        
        do {
            try process.run()
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            return String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
        } catch {
            return nil
        }
    }
    
    private func getBuildNumber() -> String? {
        // Try to get build number from environment or build info file
        return ProcessInfo.processInfo.environment["BUILD_NUMBER"] ??
               Bundle.main.infoDictionary["CFBundleVersion"] as? String
    }
    
    // MARK: - Deprecation Warnings
    
    func checkDeprecationWarnings() -> [DeprecationWarning] {
        var warnings: [DeprecationWarning] = []
        
        for policy in versionPolicies {
            if case .deprecated = policy.status {
                if let deprecationDate = policy.deprecationDate {
                    let daysUntilDeprecation = Int((deprecationDate.timeIntervalSinceNow / 86400))
                    warnings.append(DeprecrecationWarning(
                        version: policy.version,
                        deprecationDate: deprecationDate,
                        daysUntilDeprecation: daysUntilDeprecation,
                        recommendedAction: "Upgrade to v\(currentVersion.versionString)"
                    ))
                }
            }
        }
        
        return warnings
    }
    
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
    
    // MARK: - Feature Flags
    
    func isFeatureEnabled(_ feature: FeatureFlag, version: APIVersion? = nil) -> Bool {
        let targetVersion = version ?? currentVersion
        
        switch feature {
        case .cascadeActionPhase:
            return targetVersion.major >= 1
        case .realTimeStreaming:
            return targetVersion.major >= 1
        case .pluginSystem:
            return targetVersion.major >= 1
        case .advancedCaching:
            return targetVersion.major >= 1
        case .configurationManagement:
            return targetVersion.major >= 1
        case .analyticsDashboard:
            return targetVersion.major >= 1
        case .errorRecovery:
            return targetVersion.major >= 1
        case .workspaceManagement:
            return targetVersion.major >= 1
        case .protobufFieldExperiments:
            return targetVersion.major >= 1
        }
    }
    
    enum FeatureFlag: String, CaseIterable {
        case cascadeActionPhase = "cascade_action_phase"
        case realTimeStreaming = "real_time_streaming"
        case pluginSystem = "plugin_system"
        case advancedCaching = "advanced_caching"
        case configurationManagement = "configuration_management"
        case analyticsDashboard = "analytics_dashboard"
        case errorRecovery = "error_recovery"
        case workspaceManagement = "workspace_management"
        case protobufFieldExperiments = "protobuf_field_experiments"
    }
    
    // MARK: - Compatibility Matrix
    
    func getCompatibilityMatrix() -> CompatibilityMatrix {
        var matrix: [String: [String: CompatibilityStatus]] = [:]
        
        let features = FeatureFlag.allCases
        
        for version in supportedVersions {
            var versionCompatibility: [String: CompatibilityStatus] = [:]
            
            for feature in features {
                let status: CompatibilityStatus
                if isFeatureEnabled(feature, version: version) {
                    status = .supported
                } else {
                    status = .notSupported
                }
                versionCompatibility[feature.rawValue] = status
            }
            
            matrix[version.versionString] = versionCompatibility
        }
        
        return CompatibilityMatrix(
            versions: supportedVersions,
            features: features.map { $0.rawValue },
            matrix: matrix
        )
    }
    
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
                summary += " \(feature.padding(toLength: 20)) |"
            }
            summary += "\n"
            
            // Data rows
            for version in versions {
                summary += "v\(version.versionString.padding(toLength: 10)) |"
                
                for feature in features {
                    let status = matrix[version.versionString]?[feature] ?? .notSupported
                    let statusIcon = status.icon
                    summary += " \(statusIcon.padding(toLength: 20)) |"
                }
                summary += "\n"
            }
            
            return summary
        }
    }
    
    enum CompatibilityStatus {
        case supported
        case notSupported
        case deprecated
        case experimental
        
        var icon: String {
            switch self {
            case .supported: return "✅"
            case .notSupported: return "❌"
            case .deprecated: return "⚠️"
            case .experimental: return "🧪"
            }
        }
    }
}

// MARK: - Helper Extensions

extension String {
    func padding(toLength: Int) -> String {
        return self.padding(toLength: toLength, with: " ")
    }
    
    func padding(toLength: Int, with: String) -> String {
        return self.padding(toLength: toLength, with: with, truncatingTail: false)
    }
}

// MARK: - Formatted Date Extensions

extension Date {
    func formatted(date: DateFormatter.Style, time: DateFormatter.Style) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = date
        formatter.timeStyle = time
        return formatter.string(from: self)
    }
}

// MARK: - Duration Formatting

private func formatDuration(_ duration: TimeInterval) -> String {
    let formatter = DateComponentsFormatter()
    formatter.allowedUnits = [.hour, .minute, .second]
    formatter.unitsStyle = .abbreviated
    return formatter.string(from: duration)
}
