const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const BINARY_PATH = path.join(
  __dirname,
  '../../vendor/mcp-server-windsurf/.build/arm64-apple-macosx/release/mcp-server-windsurf',
);
const ENV_PATH = '/Users/dev/.config/atlastrinity/.env';

const ENV_LINE_REGEX = /^\s*([\w.-]+)\s*=\s*(.*)?\s*$/;

// Load ENV manually
function loadEnv() {
  try {
    const content = fs.readFileSync(ENV_PATH, 'utf8');
    content.split('\n').forEach((line) => {
      const match = line.match(ENV_LINE_REGEX);
      if (match) {
        const key = match[1];
        let value = match[2] || '';
        if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
        process.env[key] = value;
      }
    });
  } catch {
    console.error('Warning: Failed to load .env from', ENV_PATH);
  }
}

loadEnv();

async function testModel(modelName, toolName = 'windsurf_chat') {
  console.log(`\n🧪 Testing Model: ${modelName} (${toolName})`);
  console.log('───────────────────────────────────────');

  return new Promise((resolve) => {
    const mcp = spawn(BINARY_PATH, [], {
      env: { ...process.env, WINDSURF_DEBUG: 'true' },
    });

    let output = '';
    let errorOutput = '';

    mcp.stdout.on('data', (data) => {
      output += data.toString();
    });

    mcp.stderr.on('data', (data) => {
      errorOutput += data.toString();
    });

    const sendMessage = (msg) => {
      mcp.stdin.write(`${JSON.stringify(msg)}\n`);
    };

    // 1. Initialize
    sendMessage({
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: {},
        clientInfo: { name: 'test-client', version: '1.0.0' },
      },
    });

    // 2. Call tool after a short delay
    setTimeout(() => {
      sendMessage({
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/call',
        params: {
          name: toolName,
          arguments: {
            message: "Say 'Success' if you can read this.",
            model: modelName,
          },
        },
      });
    }, 1000);

    // 3. Close after timeout
    setTimeout(() => {
      mcp.kill();
      console.log(`--- Output for ${modelName} ---`);
      console.log(output);
      if (errorOutput) {
        console.log(`--- Error for ${modelName} ---`);
        console.log(errorOutput);
      }
      console.log('----------------------------');
      const success =
        output.includes('Success') ||
        (output.includes('deltaMessage') && output.length > 500) ||
        output.includes('Action: Created/Modified');
      if (success) {
        console.log(`✅ ${modelName}: SUCCESS`);
      } else {
        console.log(`❌ ${modelName}: FAILED or EMPTY`);
      }
      resolve(success);
    }, 15000);
  });
}

async function runAllTests() {
  console.log('🌊 Starting Multi-Model Verification');

  const results = [];

  results.push({
    model: 'windsurf-fast',
    success: await testModel('windsurf-fast', 'windsurf_chat'),
  });
  results.push({ model: 'swe-1.5', success: await testModel('swe-1.5', 'windsurf_cascade') });
  results.push({ model: 'deepseek-v3', success: await testModel('deepseek-v3', 'windsurf_chat') });
  results.push({ model: 'deepseek-r1', success: await testModel('deepseek-r1', 'windsurf_chat') });

  console.log('\n📊 Final Test Results');
  console.log('====================');
  results.forEach((r) => {
    console.log(`${r.model.padEnd(15)}: ${r.success ? '✅ OK' : '❌ FAIL'}`);
  });
}

runAllTests().catch(console.error);
