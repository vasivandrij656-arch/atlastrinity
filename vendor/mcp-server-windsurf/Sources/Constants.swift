import Foundation

// MARK: - Models
struct WindsurfModel {
    let id: String
    let name: String
    let family: String
    let tier: String
    let protobufId: String
    let description: String
    let capabilities: [String]
    let contextWindow: Int
    let maxTokens: Int
    let pricing: PricingInfo
}

struct PricingInfo {
    let inputPrice: Double
    let outputPrice: Double
    let currency: String
    let unit: String
}

// MARK: - Model Definitions
let WINDSURF_MODELS: [WindsurfModel] = [
    WindsurfModel(
        id: "swe-1.5",
        name: "SWE-1.5",
        family: "swe",
        tier: "premium",
        protobufId: "MODEL_SWE_1_5",
        description: "Advanced software engineering model",
        capabilities: ["code", "debug", "architecture", "testing"],
        contextWindow: 128000,
        maxTokens: 8192,
        pricing: PricingInfo(
            inputPrice: 0.003, outputPrice: 0.009, currency: "USD", unit: "1K tokens")
    ),
    WindsurfModel(
        id: "deepseek-v3",
        name: "DeepSeek V3",
        family: "deepseek",
        tier: "value",
        protobufId: "MODEL_DEEPSEEK_V3",
        description: "Cost-effective reasoning model",
        capabilities: ["reasoning", "math", "logic", "analysis"],
        contextWindow: 64000,
        maxTokens: 4096,
        pricing: PricingInfo(
            inputPrice: 0.001, outputPrice: 0.003, currency: "USD", unit: "1K tokens")
    ),
    WindsurfModel(
        id: "windsurf-fast",
        name: "Windsurf Fast",
        family: "chat",
        tier: "free",
        protobufId: "MODEL_CHAT_11121",
        description: "Fast general-purpose model",
        capabilities: ["chat", "completion", "summarization"],
        contextWindow: 32000,
        maxTokens: 2048,
        pricing: PricingInfo(inputPrice: 0.0, outputPrice: 0.0, currency: "USD", unit: "1K tokens")
    ),
]

// MARK: - Version Info
let IDE_VERSION = "1.107.0"
let EXTENSION_VERSION = "1.9552.21"
