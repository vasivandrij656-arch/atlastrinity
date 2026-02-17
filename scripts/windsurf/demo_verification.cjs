const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const BINARY_PATH = path.join(
  __dirname,
  '../../vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf',
);
const DEMO_FILE = path.join(__dirname, '../../demo_verification.txt');

function encodeMessage(msg) {
  return `${JSON.stringify(msg)}\n`;
}

async function runDemo() {
  console.log('🌊 Starting Windsurf MCP Demo Verification');

  // Cleanup previous demo file
  if (fs.existsSync(DEMO_FILE)) {
    console.log(`🧹 Removing old demo file: ${DEMO_FILE}`);
    fs.unlinkSync(DEMO_FILE);
  }

  if (!fs.existsSync(BINARY_PATH)) {
    console.error(`❌ Binary not found. Please build it first: swift build -c release`);
    process.exit(1);
  }

  const child = spawn(BINARY_PATH, [], {
    env: {
      ...process.env,
      WINDSURF_API_KEY:
        'sk-ws-01-3vQio5CLce8beK1OqKX1zvWmP-nTjOV3JpO3O5v3tI6Yy7SIRWJyanWHnCpjDnCKIOd1JVKFww8DKfmu5yRqVqGbazlrug',
    },
    stdio: ['pipe', 'pipe', 'inherit'],
  });

  let buffer = '';
  const responses = new Map();

  child.stdout.on('data', (data) => {
    buffer += data.toString();
    const lines = buffer.split('\n');
    buffer = lines.pop();

    for (const line of lines) {
      if (line.trim().startsWith('{')) {
        try {
          const msg = JSON.parse(line);
          if (msg.id) responses.set(msg.id, msg);
        } catch {
          // Ignore non-json logs
        }
      }
    }
  });

  const waitResponse = (id, timeout = 60000) => {
    return new Promise((resolve, reject) => {
      const start = Date.now();
      const timer = setInterval(() => {
        if (responses.has(id)) {
          clearInterval(timer);
          resolve(responses.get(id));
        } else if (Date.now() - start > timeout) {
          clearInterval(timer);
          reject(new Error(`Timeout waiting for response ID ${id}`));
        }
      }, 100);
    });
  };

  try {
    // 1. Initialize
    console.log('📤 Sending initialize...');
    child.stdin.write(
      encodeMessage({
        jsonrpc: '2.0',
        id: 1,
        method: 'initialize',
        params: {
          protocolVersion: '2024-11-05',
          capabilities: {},
          clientInfo: { name: 'demo-client', version: '1.0' },
        },
      }),
    );
    await waitResponse(1);
    console.log('✅ Initialized');

    child.stdin.write(
      encodeMessage({
        jsonrpc: '2.0',
        method: 'notifications/initialized',
      }),
    );

    // 2. Chat Tool Call with File Creation Intent
    console.log('📤 Sending windsurf_chat tool call...');
    const uniqueID = Math.random().toString(36).substring(7);
    const toolCall = {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: {
        name: 'windsurf_chat',
        arguments: {
          message: `Please create a file named demo_verification.txt in the current directory with the FOLLOWING EXACT CONTENT:
Hello from Windsurf MCP Bridge!
Verification ID: ${uniqueID}
Timestamp: ${new Date().toISOString()}`,
          model: 'windsurf-fast',
        },
      },
    };
    child.stdin.write(encodeMessage(toolCall));

    console.log(
      '⏳ Waiting for model response and autonomous file action (this may take up to 60s)...',
    );
    const toolResult = await waitResponse(2, 120000);

    console.log('\n💬 Model Response Summary:');
    console.log(`${toolResult.result.content[0].text.slice(0, 300)}...`);

    // 3. Verify File Creation
    console.log('\n🧐 Verifying filesystem changes...');
    await new Promise((r) => setTimeout(r, 2000)); // Small buffer for disk sync

    if (fs.existsSync(DEMO_FILE)) {
      const content = fs.readFileSync(DEMO_FILE, 'utf8');
      console.log(`✅ SUCCESS: ${DEMO_FILE} was created!`);
      console.log('📝 File Content:');
      console.log('-------------------');
      console.log(content);
      console.log('-------------------');

      if (content.includes(uniqueID)) {
        console.log('✅ Content verification PASSED (Unique ID matched)');
      } else {
        console.warn('⚠️ Content verification FAILED (Unique ID not found)');
      }
    } else {
      console.error(`❌ FAILURE: ${DEMO_FILE} was NOT created.`);
    }
  } catch (e) {
    console.error('❌ Demo failed:', e.message);
  } finally {
    child.kill();
    process.exit(0);
  }
}

runDemo();
