import Foundation

/// Multi-workspace context management for Windsurf MCP
class WorkspaceManager {
    static let shared = WorkspaceManager()

    private var workspaces: [String: WorkspaceContext] = [:]
    private var activeWorkspaceId: String?
    private let workspaceConfigFile: URL

    private init() {
        // Store workspace config in user's application support
        let configPath = FileManager.default.urls(
            for: .applicationSupportDirectory, in: .userDomainMask
        ).first!
        workspaceConfigFile = configPath.appendingPathComponent("atlastrinity")
            .appendingPathComponent("windsurf_workspaces.json")

        loadWorkspaces()
    }

    // MARK: - Workspace Management

    func createWorkspace(path: String, name: String? = nil) -> WorkspaceContext {
        let workspaceId = UUID().uuidString.prefix(8).lowercased()
        let workspaceName = name ?? URL(fileURLWithPath: path).lastPathComponent

        let context = WorkspaceContext(
            id: String(workspaceId),
            name: workspaceName,
            path: path,
            createdAt: Date(),
            lastUsed: Date()
        )

        workspaces[context.id] = context

        if activeWorkspaceId == nil {
            activeWorkspaceId = context.id
        }

        saveWorkspaces()
        return context
    }

    func switchToWorkspace(_ workspaceId: String) -> Bool {
        guard workspaces[workspaceId] != nil else { return false }

        activeWorkspaceId = workspaceId
        workspaces[workspaceId]?.lastUsed = Date()
        saveWorkspaces()

        fputs(
            "log: [windsurf] Switched to workspace: \(workspaces[workspaceId]?.name ?? "Unknown") (\(workspaceId))\n",
            stderr)
        return true
    }

    func getActiveWorkspace() -> WorkspaceContext? {
        guard let activeId = activeWorkspaceId else { return nil }
        return workspaces[activeId]
    }

    func getAllWorkspaces() -> [WorkspaceContext] {
        return workspaces.values.sorted { $0.lastUsed > $1.lastUsed }
    }

    func removeWorkspace(_ workspaceId: String) -> Bool {
        guard workspaces.removeValue(forKey: workspaceId) != nil else { return false }

        if activeWorkspaceId == workspaceId {
            activeWorkspaceId = workspaces.keys.first
        }

        saveWorkspaces()
        return true
    }

    func detectWorkspaceFromCurrentDirectory() -> WorkspaceContext? {
        let currentPath = FileManager.default.currentDirectoryPath

        // Check if current directory matches any existing workspace
        if let existingWorkspace = workspaces.values.first(where: { $0.path == currentPath }) {
            _ = switchToWorkspace(existingWorkspace.id)
            return existingWorkspace
        }

        // Auto-detect git repository
        if isGitRepository(currentPath) {
            let repoName =
                getGitRepositoryName(currentPath)
                ?? URL(fileURLWithPath: currentPath).lastPathComponent
            let newWorkspace = createWorkspace(path: currentPath, name: repoName)
            _ = switchToWorkspace(newWorkspace.id)
            return newWorkspace
        }

        // Create workspace for current directory if it doesn't exist
        let newWorkspace = createWorkspace(path: currentPath)
        _ = switchToWorkspace(newWorkspace.id)
        return newWorkspace
    }

    // MARK: - Workspace Context Enhancement

    func enhanceScopeForCurrentWorkspace() -> Data {
        guard let workspace = getActiveWorkspace() else {
            return createDefaultScope()
        }

        var scopeMsg = Data()
        scopeMsg.append(protoStr(1, workspace.path))  // path
        scopeMsg.append(protoStr(2, "file://" + workspace.path))  // uri
        scopeMsg.append(protoStr(3, workspace.name))  // repoName

        // Enhanced git information
        if let gitInfo = workspace.gitInfo {
            scopeMsg.append(protoStr(4, gitInfo.remoteUrl))  // repoUrl
            scopeMsg.append(protoStr(8, gitInfo.branch))  // branch
            scopeMsg.append(protoStr(9, gitInfo.commitHash))  // commit
        }

        // Workspace metadata
        scopeMsg.append(protoInt(5, 1))  // is_workspace_root: true
        scopeMsg.append(protoInt(6, 1))  // enable_file_operations: true
        scopeMsg.append(protoInt(7, 1))  // enable_tool_execution: true
        scopeMsg.append(protoInt(10, 1))  // is_git_workspace: workspace.gitInfo != nil

        // Project-specific settings
        if let projectType = detectProjectType(workspace.path) {
            scopeMsg.append(protoStr(11, projectType))  // project_type
        }

        return scopeMsg
    }

    // MARK: - Private Methods

    private func loadWorkspaces() {
        guard FileManager.default.fileExists(atPath: workspaceConfigFile.path) else { return }

        do {
            let data = try Data(contentsOf: workspaceConfigFile)
            let decoder = JSONDecoder()
            decoder.dateDecodingStrategy = .iso8601

            let loadedWorkspaces = try decoder.decode([String: WorkspaceContext].self, from: data)
            workspaces = loadedWorkspaces

            // Set active workspace to most recently used
            if let mostRecent = workspaces.values.max(by: { $0.lastUsed < $1.lastUsed }) {
                activeWorkspaceId = mostRecent.id
            }

        } catch {
            fputs("log: [windsurf] Failed to load workspace config: \(error)\n", stderr)
        }
    }

    private func saveWorkspaces() {
        do {
            let encoder = JSONEncoder()
            encoder.dateEncodingStrategy = .iso8601
            encoder.outputFormatting = .prettyPrinted

            let data = try encoder.encode(workspaces)
            try data.write(to: workspaceConfigFile)

        } catch {
            fputs("log: [windsurf] Failed to save workspace config: \(error)\n", stderr)
        }
    }

    private func isGitRepository(_ path: String) -> Bool {
        let gitPath = (path as NSString).appendingPathComponent(".git")
        return FileManager.default.fileExists(atPath: gitPath)
    }

    private func getGitRepositoryName(_ path: String) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.arguments = ["config", "--get", "remote.origin.url"]
        process.currentDirectoryPath = path

        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()

            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            if let url = String(data: data, encoding: .utf8)?.trimmingCharacters(
                in: .whitespacesAndNewlines),
                !url.isEmpty
            {
                return URL(string: url)?.lastPathComponent.replacingOccurrences(
                    of: ".git", with: "")
            }
        } catch {
            // Git not available or not a git repo
        }

        return nil
    }

    private func detectProjectType(_ path: String) -> String? {
        let fileManager = FileManager.default

        // Detect common project types by presence of specific files
        if fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("package.json"))
        {
            return "nodejs"
        }

        if fileManager.fileExists(
            atPath: (path as NSString).appendingPathComponent("requirements.txt"))
            || fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("setup.py"))
            || fileManager.fileExists(
                atPath: (path as NSString).appendingPathComponent("pyproject.toml"))
        {
            return "python"
        }

        if fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("Cargo.toml")) {
            return "rust"
        }

        if fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("go.mod")) {
            return "go"
        }

        if fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("pom.xml")) {
            return "java"
        }

        return nil
    }

    private func createDefaultScope() -> Data {
        let currentPath = FileManager.default.currentDirectoryPath

        var scopeMsg = Data()
        scopeMsg.append(protoStr(1, currentPath))
        scopeMsg.append(protoStr(2, "file://" + currentPath))
        scopeMsg.append(protoStr(3, URL(fileURLWithPath: currentPath).lastPathComponent))
        scopeMsg.append(protoInt(5, 1))
        scopeMsg.append(protoInt(6, 1))
        scopeMsg.append(protoInt(7, 1))

        return scopeMsg
    }
}

// MARK: - Workspace Context Model

struct WorkspaceContext: Codable {
    let id: String
    let name: String
    let path: String
    let createdAt: Date
    var lastUsed: Date
    var gitInfo: GitInfo?
    var projectSettings: ProjectSettings?

    init(id: String, name: String, path: String, createdAt: Date, lastUsed: Date) {
        self.id = id
        self.name = name
        self.path = path
        self.createdAt = createdAt
        self.lastUsed = lastUsed

        // Auto-detect git info
        self.gitInfo = GitInfo.detect(for: path)

        // Auto-detect project settings
        self.projectSettings = ProjectSettings.detect(for: path)
    }
}

struct GitInfo: Codable {
    let remoteUrl: String
    let branch: String
    let commitHash: String
    let isDirty: Bool

    static func detect(for path: String) -> GitInfo? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/git")
        process.currentDirectoryPath = path

        // Get remote URL
        process.arguments = ["config", "--get", "remote.origin.url"]
        let remotePipe = Pipe()
        process.standardOutput = remotePipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()
            process.waitUntilExit()

            let remoteData = remotePipe.fileHandleForReading.readDataToEndOfFile()
            guard
                let remoteUrl = String(data: remoteData, encoding: .utf8)?.trimmingCharacters(
                    in: .whitespacesAndNewlines),
                !remoteUrl.isEmpty
            else {
                return nil
            }

            // Get current branch
            process.arguments = ["rev-parse", "--abbrev-ref", "HEAD"]
            let branchPipe = Pipe()
            process.standardOutput = branchPipe

            try process.run()
            process.waitUntilExit()

            let branchData = branchPipe.fileHandleForReading.readDataToEndOfFile()
            let branch =
                String(data: branchData, encoding: .utf8)?.trimmingCharacters(
                    in: .whitespacesAndNewlines) ?? "main"

            // Get commit hash
            process.arguments = ["rev-parse", "HEAD"]
            let commitPipe = Pipe()
            process.standardOutput = commitPipe

            try process.run()
            process.waitUntilExit()

            let commitData = commitPipe.fileHandleForReading.readDataToEndOfFile()
            let commitHash =
                String(data: commitData, encoding: .utf8)?.trimmingCharacters(
                    in: .whitespacesAndNewlines) ?? ""

            // Check if working directory is dirty
            process.arguments = ["status", "--porcelain"]
            let statusPipe = Pipe()
            process.standardOutput = statusPipe

            try process.run()
            process.waitUntilExit()

            let statusData = statusPipe.fileHandleForReading.readDataToEndOfFile()
            let statusOutput = String(data: statusData, encoding: .utf8) ?? ""
            let isDirty = !statusOutput.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty

            return GitInfo(
                remoteUrl: remoteUrl, branch: branch, commitHash: commitHash, isDirty: isDirty)

        } catch {
            return nil
        }
    }
}

struct ProjectSettings: Codable {
    let type: String
    let buildCommand: String?
    let testCommand: String?
    let dependencies: [String]

    static func detect(for path: String) -> ProjectSettings? {
        let fileManager = FileManager.default

        // Node.js project
        if fileManager.fileExists(atPath: (path as NSString).appendingPathComponent("package.json"))
        {
            do {
                let packageData = try Data(
                    contentsOf: URL(
                        fileURLWithPath: (path as NSString).appendingPathComponent("package.json")))
                let package = try JSONSerialization.jsonObject(with: packageData) as? [String: Any]

                let scripts = package?["scripts"] as? [String: String] ?? [:]
                let dependencies = Array((package?["dependencies"] as? [String: Any] ?? [:]).keys)

                return ProjectSettings(
                    type: "nodejs",
                    buildCommand: scripts["build"],
                    testCommand: scripts["test"],
                    dependencies: dependencies
                )
            } catch {
                return ProjectSettings(
                    type: "nodejs", buildCommand: nil, testCommand: nil, dependencies: [])
            }
        }

        // Python project
        if fileManager.fileExists(
            atPath: (path as NSString).appendingPathComponent("requirements.txt"))
        {
            do {
                let requirementsData = try Data(
                    contentsOf: URL(
                        fileURLWithPath: (path as NSString).appendingPathComponent(
                            "requirements.txt")))
                let requirements =
                    String(data: requirementsData, encoding: .utf8)?
                    .components(separatedBy: .newlines)
                    .map { $0.components(separatedBy: "==")[0] }
                    .filter { !$0.isEmpty && !$0.hasPrefix("#") } ?? []

                return ProjectSettings(
                    type: "python",
                    buildCommand: nil,
                    testCommand: "pytest",
                    dependencies: requirements
                )
            } catch {
                return ProjectSettings(
                    type: "python", buildCommand: nil, testCommand: nil, dependencies: [])
            }
        }

        return nil
    }
}

// MARK: - MCP Tool Extensions

extension WorkspaceManager {

    func handleWorkspaceList() -> String {
        let workspaces = getAllWorkspaces()
        let activeId = activeWorkspaceId

        var result = "📁 Windsurf Workspaces\n"
        result += "═══════════════════════════\n\n"

        for workspace in workspaces {
            let isActive = workspace.id == activeId ? "🟢" : "⚪"
            let projectType = workspace.projectSettings?.type ?? ""

            result += "\(isActive) \(workspace.name)\n"
            result += "   ID: \(workspace.id)\n"
            result += "   Path: \(workspace.path)\n"

            if !projectType.isEmpty {
                result += "   Type: \(projectType)\n"
            }

            if let gitInfo = workspace.gitInfo {
                result += "   Branch: \(gitInfo.branch)\n"
                result += "   Status: \(gitInfo.isDirty ? "🔴 Modified" : "✅ Clean")\n"
            }

            result +=
                "   Last Used: \(workspace.lastUsed.formatted(date: .abbreviated, time: .shortened))\n\n"
        }

        return result
    }

    func handleWorkspaceSwitch(workspaceId: String) -> String {
        guard switchToWorkspace(workspaceId) else {
            return "❌ Workspace not found: \(workspaceId)"
        }

        guard let workspace = getActiveWorkspace() else {
            return "❌ Failed to switch to workspace"
        }

        return """
            ✅ Switched to workspace: \(workspace.name)
            📁 Path: \(workspace.path)
            📦 Git: \(workspace.gitInfo != nil ? "Yes" : "No")
            🏗️ Project Type: \(workspace.projectSettings?.type ?? "Unknown")
            """
    }

    func handleWorkspaceCreate(path: String, name: String?) -> String {
        let workspace = createWorkspace(path: path, name: name)
        _ = switchToWorkspace(workspace.id)

        return """
            ✅ Created and switched to workspace: \(workspace.name)
            📁 Path: \(workspace.path)
            🆔 ID: \(workspace.id)
            📦 Git: \(workspace.gitInfo != nil ? "Yes" : "No")
            🏗️ Project Type: \(workspace.projectSettings?.type ?? "Unknown")
            """
    }
}
