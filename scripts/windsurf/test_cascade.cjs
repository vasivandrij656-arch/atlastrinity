const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const BINARY_PATH = path.join(__dirname, '../../vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf');

function encodeMessage(msg) {
    return JSON.stringify(msg) + '\n';
}

async function runTest() {
    console.log('🚀 Starting Node.js MCP Test');
    
    if (!fs.existsSync(BINARY_PATH)) {
        console.error(`❌ Binary not found at: ${BINARY_PATH}`);
        process.exit(1);
    }

    const child = spawn(BINARY_PATH, [], {
        env: { ...process.env },
        stdio: ['pipe', 'pipe', 'inherit'] // pipe stdin/stdout, inherit stderr
    });

    let buffer = '';
    
    child.stdout.on('data', (data) => {
        buffer += data.toString();
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
    const initPromise = new Promise(resolve => initResolver = resolve);

    function handleMessage(msg) {
        console.log('📩 Received:', JSON.stringify(msg).slice(0, 100) + '...');
        if (msg.id === 1) {
            console.log('✅ Initialize response received');
            initResolver(msg);
        }
    }

    // Send Initialize
    const initMsg = {
        jsonrpc: "2.0",
        id: 1,
        method: "initialize",
        params: {
            protocolVersion: "2024-11-05",
            capabilities: {},
            clientInfo: { name: "test-client", version: "1.0" }
        }
    };

    console.log('📤 Sending initialize...');
    child.stdin.write(encodeMessage(initMsg));

    // Wait for init
    try {
        await Promise.race([
            initPromise,
            new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 30000))
        ]);
        
        console.log('✅ Initialization successful!');
        
        // Send Initialized Notification
        child.stdin.write(encodeMessage({
            jsonrpc: "2.0",
            method: "notifications/initialized"
        }));

        // Send Tool Call
        const toolCall = {
            jsonrpc: "2.0",
            id: 2,
            method: "tools/call",
            params: {
                name: "windsurf_cascade",
                arguments: {
                    message: "Create /Users/dev/Documents/GitHub/atlastrinity/demo.txt with content 'Windsurf Bridge Demonstration'",
                    model: "windsurf-fast"
                }
            }
        };
        console.log('📤 Sending tool call...');
        child.stdin.write(encodeMessage(toolCall));
        
        // Wait for tool response (just wait 10s then check file)
        await new Promise(resolve => setTimeout(resolve, 10000));
        
        child.kill();
        
        // precise verification handled by caller or manual check
        console.log('🏁 Test finished, check for file creation.');
        
    } catch (e) {
        console.error('❌ Test failed:', e);
        child.kill();
        process.exit(1);
    }
}

runTest();
