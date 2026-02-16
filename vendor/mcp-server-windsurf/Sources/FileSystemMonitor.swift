import Dispatch
import Foundation

/// Real-time file system monitor for Action Phase verification
class FileSystemMonitor {
    private let monitoredDirectory: URL
    private var fileDescriptor: Int32 = -1
    private var source: DispatchSourceFileSystemObject?
    private let callback: (FileEvent) -> Void
    private let queue = DispatchQueue(label: "filesystem.monitor")

    struct FileEvent: Codable {
        let path: String
        let type: EventType
        let timestamp: Date

        enum EventType: String, Codable {
            case created = "created"
            case modified = "modified"
            case deleted = "deleted"
            case renamed = "renamed"

            var description: String {
                return self.rawValue
            }
        }
    }

    init(directoryPath: String, callback: @escaping (FileEvent) -> Void) {
        self.monitoredDirectory = URL(fileURLWithPath: directoryPath)
        self.callback = callback
    }

    deinit {
        stopMonitoring()
    }

    func startMonitoring() -> Bool {
        guard fileDescriptor == -1 else { return true }  // Already monitoring

        // Open directory for monitoring
        fileDescriptor = open(monitoredDirectory.path, O_EVTONLY)
        guard fileDescriptor != -1 else {
            fputs(
                "log: [windsurf] Failed to open directory for monitoring: \(monitoredDirectory.path)\n",
                stderr)
            return false
        }

        // Create dispatch source
        source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: fileDescriptor,
            eventMask: [.write, .delete, .rename],
            queue: queue
        )

        // Set event handler
        source?.setEventHandler { [weak self] in
            self?.handleFileSystemEvent()
        }

        // Set cancellation handler
        source?.setCancelHandler { [weak self] in
            guard let self = self else { return }
            if self.fileDescriptor != -1 {
                close(self.fileDescriptor)
                self.fileDescriptor = -1
            }
        }

        // Resume monitoring
        source?.resume()

        fputs(
            "log: [windsurf] Started file system monitoring for: \(monitoredDirectory.path)\n",
            stderr)
        return true
    }

    func stopMonitoring() {
        source?.cancel()
        source = nil
        if fileDescriptor != -1 {
            close(fileDescriptor)
            fileDescriptor = -1
        }
        fputs("log: [windsurf] Stopped file system monitoring\n", stderr)
    }

    private func handleFileSystemEvent() {
        let eventMask = source?.data ?? []

        if eventMask.contains(.write) {
            // Directory contents changed - scan for modifications
            scanForModifications()
        }

        if eventMask.contains(.delete) {
            // Something was deleted
            scanForDeletions()
        }

        if eventMask.contains(.rename) {
            // Something was renamed
            scanForRenames()
        }
    }

    private func scanForModifications() {
        // This is a simplified implementation
        // In a production system, you'd maintain a file state cache
        let fileManager = FileManager.default

        do {
            let contents = try fileManager.contentsOfDirectory(atPath: monitoredDirectory.path)

            for fileName in contents {
                let filePath = (monitoredDirectory.path as NSString).appendingPathComponent(
                    fileName)

                // Skip directories and hidden files
                var isDir: ObjCBool = false
                guard fileManager.fileExists(atPath: filePath, isDirectory: &isDir),
                    !isDir.boolValue,
                    !fileName.hasPrefix(".")
                else {
                    continue
                }

                let attributes = try? fileManager.attributesOfItem(atPath: filePath)
                let modificationDate = attributes?[.modificationDate] as? Date ?? Date()

                // If file was modified recently (within last 5 seconds)
                if Date().timeIntervalSince(modificationDate) < 5.0 {
                    let event = FileEvent(
                        path: filePath,
                        type: .modified,
                        timestamp: modificationDate
                    )

                    DispatchQueue.main.async {
                        self.callback(event)
                    }
                }
            }
        } catch {
            fputs("log: [windsurf] Error scanning directory: \(error)\n", stderr)
        }
    }

    private func scanForDeletions() {
        // Simplified deletion detection
        // In production, you'd compare with previous state
        fputs("log: [windsurf] File deletion detected in monitored directory\n", stderr)
    }

    private func scanForRenames() {
        // Simplified rename detection
        // In production, you'd compare with previous state
        fputs("log: [windsurf] File rename detected in monitored directory\n", stderr)
    }
}

/// Action Phase verification system with file monitoring
class ActionPhaseVerifier {
    private var fileMonitor: FileSystemMonitor!
    private var detectedEvents: [FileSystemMonitor.FileEvent] = []
    private let startTime = Date()

    init(workspacePath: String) {
        self.fileMonitor = nil
        self.fileMonitor = FileSystemMonitor(directoryPath: workspacePath) { [weak self] event in
            self?.handleFileEvent(event)
        }
    }

    func startVerification() {
        detectedEvents.removeAll()
        _ = fileMonitor.startMonitoring()
        fputs("log: [windsurf] Action Phase verification started\n", stderr)
    }

    func stopVerification() -> ActionPhaseResult {
        fileMonitor.stopMonitoring()

        let result = ActionPhaseResult(
            duration: Date().timeIntervalSince(startTime),
            fileEvents: detectedEvents,
            success: !detectedEvents.isEmpty
        )

        fputs(
            "log: [windsurf] Action Phase verification completed: \(detectedEvents.count) events detected\n",
            stderr)
        return result
    }

    private func handleFileEvent(_ event: FileSystemMonitor.FileEvent) {
        detectedEvents.append(event)

        let message =
            "log: [windsurf] Action Phase event: \(event.type.description) - \(event.path)\n"
        fputs(message, stderr)

        // Also check if this looks like a file creation from Cascade
        if event.type == .created || event.type == .modified {
            verifyCascadeSignature(event.path)
        }
    }

    private func verifyCascadeSignature(_ filePath: String) {
        do {
            let content = try String(contentsOfFile: filePath, encoding: .utf8)

            // Look for Cascade/AI generation signatures
            let cascadeSignatures = [
                "Generated by",
                "AI Assistant",
                "Cascade",
                "Windsurf",
                "automatically created",
            ]

            let hasCascadeSignature = cascadeSignatures.contains { signature in
                content.localizedCaseInsensitiveContains(signature)
            }

            if hasCascadeSignature {
                fputs("log: [windsurf] Cascade signature detected in: \(filePath)\n", stderr)
            }

        } catch {
            // File might be binary or unreadable
        }
    }
}

struct ActionPhaseResult {
    let duration: TimeInterval
    let fileEvents: [FileSystemMonitor.FileEvent]
    let success: Bool

    var summary: String {
        let createdCount = fileEvents.filter { $0.type == .created }.count
        let modifiedCount = fileEvents.filter { $0.type == .modified }.count
        let deletedCount = fileEvents.filter { $0.type == .deleted }.count

        return """
            🎯 Action Phase Verification Results
            ═══════════════════════════════════
            ⏱️ Duration: \(String(format: "%.2f", duration))s
            📁 Total Events: \(fileEvents.count)
            📝 Files Created: \(createdCount)
            ✏️ Files Modified: \(modifiedCount)
            🗑️ Files Deleted: \(deletedCount)
            ✅ Success: \(success ? "YES" : "NO")
            """
    }
}

// MARK: - Integration with handleCascade

/// Global verifier instance
var actionVerifier: ActionPhaseVerifier?

func startActionPhaseVerification() {
    let workspacePath = FileManager.default.currentDirectoryPath
    actionVerifier = ActionPhaseVerifier(workspacePath: workspacePath)
    actionVerifier?.startVerification()
}

func stopActionPhaseVerification() -> ActionPhaseResult? {
    guard let verifier = actionVerifier else { return nil }
    let result = verifier.stopVerification()
    actionVerifier = nil
    return result
}
