import Foundation

/// Advanced Protobuf field discovery and validation system
class ProtobufFieldExplorer {
    private let connection: LSConnection
    private let apiKey: String

    init(connection: LSConnection, apiKey: String) {
        self.connection = connection
        self.apiKey = apiKey
    }

    /// Experiment with different field numbers to discover Cortex protocol fields
    func exploreCortexFields(baseModelUid: String) async -> [FieldExperiment] {
        var experiments: [FieldExperiment] = []

        // Test different field number combinations for Cortex reasoning
        let cortexFieldSets: [[(field: Int, value: Int)]] = [
            // Basic action enabling
            [(11, 1), (12, 1)],
            [(11, 1), (12, 1), (13, 1)],
            [(11, 1), (12, 1), (13, 1), (14, 1)],

            // Extended action flags
            [(11, 1), (12, 1), (13, 1), (14, 1), (15, 1)],
            [(11, 1), (12, 1), (13, 1), (14, 1), (15, 1), (16, 1)],

            // Alternative field number patterns
            [(21, 1), (22, 1), (23, 1)],
            [(31, 1), (32, 1), (33, 1)],
            [(41, 1), (42, 1), (43, 1)],

            // High-value fields (less likely but worth testing)
            [(101, 1), (102, 1)],
            [(201, 1), (202, 1)],
            [(301, 1), (302, 1)],
        ]

        for (index, fieldSet) in cortexFieldSets.enumerated() {
            let experiment = await testFieldSet(
                fields: fieldSet,
                modelUid: baseModelUid,
                experimentId: index + 1
            )
            experiments.append(experiment)

            // Small delay between experiments
            try? await Task.sleep(nanoseconds: 500_000_000)  // 0.5 seconds
        }

        return experiments
    }

    private func testFieldSet(
        fields: [(field: Int, value: Int)], modelUid: String, experimentId: Int
    ) async -> FieldExperiment {
        let startTime = Date()

        do {
            // Build experimental PlannerConfig
            var plannerProto = Data()
            plannerProto.append(protoStr(34, modelUid))  // plan_model
            plannerProto.append(protoStr(35, modelUid))  // requested_model

            // Add experimental fields
            for (field, value) in fields {
                plannerProto.append(protoInt(field, value))
            }

            // Create minimal Cascade request for testing
            let sessionId = "experiment-\(experimentId)-\(UUID().uuidString.prefix(8))"
            let meta = buildMetadataProto(apiKey: apiKey, sessionId: sessionId)

            // Start Cascade
            let startPayload = protoMsg(1, meta)
            let startResp = try await sendProto(LS_START_CASCADE, startPayload)

            guard let cascadeId = protoExtractString(startResp, 1), !cascadeId.isEmpty else {
                return FieldExperiment(
                    experimentId: experimentId,
                    fields: fields,
                    success: false,
                    responseTime: Date().timeIntervalSince(startTime),
                    error: "Failed to start Cascade"
                )
            }

            // Send test message with experimental config
            let configProto = protoMsg(5, protoMsg(1, plannerProto))
            let testMessage = "Create a test_file_\(experimentId).txt with experiment data"

            var itemsProto = Data()
            var textItem = Data()
            textItem.append(protoStr(1, testMessage))
            textItem.append(protoInt(4, 1))
            textItem.append(protoStr(15, UUID().uuidString))
            itemsProto.append(protoMsg(3, textItem))

            let queuePayload =
                protoMsg(1, meta) + protoStr(2, cascadeId) + itemsProto + configProto
                + protoInt(11, 1)
            let _ = try await sendProto(LS_INTERRUPT_WITH_MESSAGE, queuePayload)

            // Wait briefly and check for any response
            try? await Task.sleep(nanoseconds: 2_000_000_000)  // 2 seconds

            // Check if any files were created (simple verification)
            let testFilePath = "test_file_\(experimentId).txt"
            let fileCreated = FileManager.default.fileExists(atPath: testFilePath)

            // Clean up test file if created
            if fileCreated {
                try? FileManager.default.removeItem(atPath: testFilePath)
            }

            return FieldExperiment(
                experimentId: experimentId,
                fields: fields,
                success: fileCreated,
                responseTime: Date().timeIntervalSince(startTime),
                cascadeId: cascadeId,
                fileCreated: fileCreated
            )

        } catch {
            return FieldExperiment(
                experimentId: experimentId,
                fields: fields,
                success: false,
                responseTime: Date().timeIntervalSince(startTime),
                error: error.localizedDescription
            )
        }
    }

    /// Send Proto request helper
    private func sendProto(_ endpoint: String, _ payload: Data) async throws -> Data {
        let url = URL(string: "http://127.0.0.1:\(connection.port)\(endpoint)")!
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = "POST"
        req.setValue("application/grpc", forHTTPHeaderField: "Content-Type")
        req.setValue("trailers", forHTTPHeaderField: "TE")
        req.setValue(connection.csrfToken, forHTTPHeaderField: "x-codeium-csrf-token")

        // Envelope
        var env = Data()
        env.append(0)
        var len = UInt32(payload.count).bigEndian
        env.append(Data(bytes: &len, count: 4))
        env.append(payload)
        req.httpBody = env

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard let httpResp = resp as? HTTPURLResponse, httpResp.statusCode == 200 else {
            throw NSError(
                domain: "WindsurfMCP", code: 1,
                userInfo: [NSLocalizedDescriptionKey: "HTTP Error for \(endpoint)"])
        }

        // Unwrap Envelope
        if data.count >= 5 {
            let len = UInt32(
                bigEndian: data.subdata(in: 1..<5).withUnsafeBytes { $0.load(as: UInt32.self) })
            if data.count >= 5 + Int(len) {
                return data.subdata(in: 5..<5 + Int(len))
            }
        }
        return Data()
    }
}

struct FieldExperiment {
    let experimentId: Int
    let fields: [(field: Int, value: Int)]
    let success: Bool
    let responseTime: TimeInterval
    let cascadeId: String?
    let fileCreated: Bool?
    let error: String?

    init(
        experimentId: Int, fields: [(field: Int, value: Int)], success: Bool,
        responseTime: TimeInterval, cascadeId: String? = nil, fileCreated: Bool? = nil,
        error: String? = nil
    ) {
        self.experimentId = experimentId
        self.fields = fields
        self.success = success
        self.responseTime = responseTime
        self.cascadeId = cascadeId
        self.fileCreated = fileCreated
        self.error = error
    }

    var summary: String {
        let fieldList = fields.map { "\($0.field)=\($0.value)" }.joined(separator: ", ")
        let result = success ? "✅ SUCCESS" : "❌ FAILED"

        var summary = "Experiment \(experimentId): \(result)\n"
        summary += "  Fields: [\(fieldList)]\n"
        summary += "  Response Time: \(String(format: "%.2f", responseTime))s\n"

        if let fileCreated = fileCreated {
            summary += "  File Created: \(fileCreated ? "YES" : "NO")\n"
        }

        if let error = error {
            summary += "  Error: \(error)\n"
        }

        if let cascadeId = cascadeId {
            summary += "  Cascade ID: \(cascadeId)\n"
        }

        return summary
    }
}

/// Field experiment results analyzer
class FieldExperimentAnalyzer {
    static func analyzeResults(_ experiments: [FieldExperiment]) -> AnalysisResult {
        let successfulExperiments = experiments.filter { $0.success }
        let failedExperiments = experiments.filter { !$0.success }

        // Identify potentially important fields
        var fieldSuccessRates: [Int: Double] = [:]

        for experiment in experiments {
            for (field, _) in experiment.fields {
                let totalCount = experiments.filter { exp in
                    exp.fields.contains { $0.field == field }
                }.count

                if totalCount > 0 {
                    let successCount = successfulExperiments.filter { exp in
                        exp.fields.contains { $0.field == field }
                    }.count
                    fieldSuccessRates[field] = Double(successCount) / Double(totalCount)
                }
            }
        }

        // Sort fields by success rate
        let sortedFields = fieldSuccessRates.sorted { $0.value > $1.value }

        return AnalysisResult(
            totalExperiments: experiments.count,
            successfulExperiments: successfulExperiments.count,
            failedExperiments: failedExperiments.count,
            fieldSuccessRates: fieldSuccessRates,
            topFields: sortedFields.prefix(5).map { $0 },
            recommendations: generateRecommendations(fieldSuccessRates: fieldSuccessRates)
        )
    }

    private static func generateRecommendations(fieldSuccessRates: [Int: Double]) -> [String] {
        var recommendations: [String] = []

        // Find fields with high success rates
        let highSuccessFields = fieldSuccessRates.filter { $0.value >= 0.7 }.map { $0.key }

        if !highSuccessFields.isEmpty {
            recommendations.append("High-success fields to prioritize: \(highSuccessFields)")
        }

        // Find fields with moderate success rates
        let moderateSuccessFields = fieldSuccessRates.filter { $0.value >= 0.3 && $0.value < 0.7 }
            .map { $0.key }

        if !moderateSuccessFields.isEmpty {
            recommendations.append(
                "Moderate-success fields worth further testing: \(moderateSuccessFields)")
        }

        // Find completely unsuccessful fields
        let zeroSuccessFields = fieldSuccessRates.filter { $0.value == 0.0 }.map { $0.key }

        if !zeroSuccessFields.isEmpty {
            recommendations.append("Fields to avoid (0% success): \(zeroSuccessFields)")
        }

        return recommendations
    }
}

struct AnalysisResult {
    let totalExperiments: Int
    let successfulExperiments: Int
    let failedExperiments: Int
    let fieldSuccessRates: [Int: Double]
    let topFields: [(key: Int, value: Double)]
    let recommendations: [String]

    var summary: String {
        var summary = """
            🧪 Protobuf Field Experiment Analysis
            ════════════════════════════════════
            📊 Total Experiments: \(totalExperiments)
            ✅ Successful: \(successfulExperiments) (\(String(format: "%.1f", Double(successfulExperiments) / Double(totalExperiments) * 100))%)
            ❌ Failed: \(failedExperiments) (\(String(format: "%.1f", Double(failedExperiments) / Double(totalExperiments) * 100))%)

            🏆 Top Performing Fields:
            """

        for (field, rate) in topFields {
            summary += "\n  Field \(field): \(String(format: "%.1f", rate * 100))% success rate"
        }

        summary += "\n\n💡 Recommendations:\n"
        for recommendation in recommendations {
            summary += "\n  • \(recommendation)"
        }

        return summary
    }
}
