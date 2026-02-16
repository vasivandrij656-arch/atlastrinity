// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "mcp-server-windsurf",
    platforms: [
        .macOS(.v13)
    ],
    dependencies: [
        .package(url: "https://github.com/modelcontextprotocol/swift-sdk.git", from: "0.7.0")
    ],
    targets: [
        .executableTarget(
            name: "mcp-server-windsurf",
            dependencies: [
                .product(name: "MCP", package: "swift-sdk")
            ],
            path: "Sources",
            sources: [
                "main.swift",
                "FileSystemMonitor.swift",
                "ProtobufFieldExplorer.swift", 
                "WindsurfLogger.swift",
                "WorkspaceManager.swift",
                "ErrorRecoveryManager.swift"
            ]
        )
    ]
)
