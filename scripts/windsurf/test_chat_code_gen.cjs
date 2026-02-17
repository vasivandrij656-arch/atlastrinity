const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');

const BINARY_PATH = path.join(
  __dirname,
  '../../vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf',
);

function encodeMessage(msg) {
  return `${JSON.stringify(msg)}\n`;
}

async function runTest() {
  console.log('🚀 Starting Windsurf Chat Code Gen Test');

  if (!fs.existsSync(BINARY_PATH)) {
    console.error(`❌ Binary not found at: ${BINARY_PATH}`);
    process.exit(1);
  }

  const child = spawn(BINARY_PATH, [], {
    env: { ...process.env },
    stdio: ['pipe', 'pipe', 'inherit'],
  });

  let buffer = '';

  child.stdout.on('data', (data) => {
    const str = data.toString();
    console.log('📥 Raw Handshake Data:', str.slice(0, 100).replace(/\r\n/g, '\\r\\n'));
    buffer += str;
    processBuffer();
  });

  function processBuffer() {
    while (true) {
      const nlIndex = buffer.indexOf('\n');
      if (nlIndex === -1) return;

      const line = buffer.slice(0, nlIndex).trim();
      buffer = buffer.slice(nlIndex + 1);

      if (line.startsWith('{')) {
        try {
          const message = JSON.parse(line);
          handleMessage(message);
        } catch (e) {
          console.error('❌ Failed to parse message:', e, 'Raw:', line);
        }
      }
    }
  }

  let initResolver;
  const initPromise = new Promise((resolve) => (initResolver = resolve));

  function handleMessage(msg) {
    if (msg.id === 1) {
      console.log('✅ Initialize response received');
      initResolver(msg);
    } else if (msg.id === 2) {
      console.log('📩 Chat Response:', JSON.stringify(msg.result, null, 2));
      if (msg.result?.content?.[0].text.includes('```')) {
        console.log('✅ Markdown code block detected!');
      } else {
        console.log('⚠️ No markdown code block detected.');
      }
      child.kill();
      process.exit(0);
    }
  }

  // Send Initialize
  const initMsg = {
    jsonrpc: '2.0',
    id: 1,
    method: 'initialize',
    params: {
      protocolVersion: '2024-11-05',
      capabilities: {},
      clientInfo: { name: 'test-client', version: '1.0' },
    },
  };

  console.log('📤 Sending initialize...');
  child.stdin.write(encodeMessage(initMsg));

  // Wait for init
  try {
    await Promise.race([
      initPromise,
      new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 30000)),
    ]);

    console.log('✅ Initialization successful!');

    // Send Initialized
    child.stdin.write(
      encodeMessage({
        jsonrpc: '2.0',
        method: 'notifications/initialized',
      }),
    );

    // Send Chat Tool Call
    const toolCall = {
      jsonrpc: '2.0',
      id: 2,
      method: 'tools/call',
      params: {
        name: 'windsurf_chat',
        arguments: {
          message:
            "Create /Users/dev/Documents/GitHub/atlastrinity/manual_node_chat_test.txt with content 'Chat Mode Works'",
          model: 'swe-1.5',
        },
      },
    };
    console.log('📤 Sending chat tool call...');
    child.stdin.write(encodeMessage(toolCall));
  } catch (e) {
    console.error('❌ Test failed:', e);
    child.kill();
    process.exit(1);
  }
}
runTest();
