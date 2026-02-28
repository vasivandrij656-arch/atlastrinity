#!/usr/bin/env node
/**
 * Config Template Sync Script
 *
 * Syncs configuration templates to active config locations.
 * Usage: npm run config:sync
 *
 * This script copies template files from config/ to ~/.config/atlastrinity/
 * preserving user modifications while updating structure.
 */

import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const PROJECT_ROOT = path.resolve(__dirname, '..');
const CONFIG_ROOT = path.join(os.homedir(), '.config', 'atlastrinity');
const VIBE_ROOT = path.join(os.homedir(), '.vibe');
const VIBE_AGENTS_DIR = path.join(VIBE_ROOT, 'agents');
const MCP_DIR = path.join(CONFIG_ROOT, 'mcp');

// Configuration mappings: template -> destination
const CONFIG_MAPPINGS = [
  {
    template: path.join(PROJECT_ROOT, 'config', 'config.yaml.template'),
    destination: path.join(CONFIG_ROOT, 'config.yaml'),
    description: 'Main system configuration',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'behavior_config.yaml.template'),
    destination: path.join(CONFIG_ROOT, 'behavior_config.yaml'),
    description: 'Behavior engine configuration',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe_config.toml.template'),
    destination: path.join(CONFIG_ROOT, 'vibe_config.toml'),
    description: 'Vibe CLI configuration',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'accept-edits.toml.template'),
    destination: path.join(CONFIG_ROOT, 'vibe', 'agents', 'accept-edits.toml'),
    description: 'Vibe Agent: Accept Edits',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'auto-approve.toml.template'),
    destination: path.join(CONFIG_ROOT, 'vibe', 'agents', 'auto-approve.toml'),
    description: 'Vibe Agent: Auto Approve',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'plan.toml.template'),
    destination: path.join(CONFIG_ROOT, 'vibe', 'agents', 'plan.toml'),
    description: 'Vibe Agent: Plan',
  },

  {
    template: path.join(PROJECT_ROOT, 'config', 'mcp_servers.json.template'),
    destination: path.join(MCP_DIR, 'config.json'),
    description: 'MCP servers configuration',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'prometheus.yml.template'),
    destination: path.join(CONFIG_ROOT, 'prometheus.yml'),
    description: 'Prometheus metrics configuration',
  },
  // Native Vibe home directory mappings
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe_config.toml.template'),
    destination: path.join(VIBE_ROOT, 'config.toml'),
    description: 'Native Vibe CLI configuration (Home)',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'accept-edits.toml.template'),
    destination: path.join(VIBE_AGENTS_DIR, 'accept-edits.toml'),
    description: 'Native Vibe Agent: Accept Edits (Home)',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'auto-approve.toml.template'),
    destination: path.join(VIBE_AGENTS_DIR, 'auto-approve.toml'),
    description: 'Native Vibe Agent: Auto Approve (Home)',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'vibe', 'agents', 'plan.toml.template'),
    destination: path.join(VIBE_AGENTS_DIR, 'plan.toml'),
    description: 'Native Vibe Agent: Plan (Home)',
  },
  {
    template: path.join(PROJECT_ROOT, 'config', 'scripts', 'mikrotik_logger.py.template'),
    destination: path.join(CONFIG_ROOT, 'scripts', 'mikrotik_logger.py'),
    description: 'Mikrotik Logger Script',
  },
  {
    template: path.join(
      PROJECT_ROOT,
      'config',
      'launchd',
      'com.antigravity.mikrotik.logger.plist.template',
    ),
    destination: path.join(
      os.homedir(),
      'Library',
      'LaunchAgents',
      'com.antigravity.mikrotik.logger.plist',
    ),
    description: 'Mikrotik Logger LaunchAgent',
  },
];

function ensureDirectoryExists(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
    console.log(`✓ Created directory: ${dirPath}`);
  }
}

function backupConfig(filePath) {
  if (fs.existsSync(filePath)) {
    const backupPath = `${filePath}.backup.${Date.now()}`;
    fs.copyFileSync(filePath, backupPath);
    console.log(`  → Backup created: ${path.basename(backupPath)}`);
    return backupPath;
  }
  return null;
}

function syncConfig(mapping, options = {}) {
  const { template, destination, description } = mapping;
  const { force = false, backup = true } = options;

  console.log(`\n📝 ${description}`);
  console.log(`   Template: ${path.relative(PROJECT_ROOT, template)}`);
  console.log(`   Destination: ${path.relative(os.homedir(), destination)}`);

  // Check if template exists
  if (!fs.existsSync(template)) {
    console.log(`   ⚠️  Template not found, skipping`);
    return false;
  }

  // Ensure destination directory exists
  ensureDirectoryExists(path.dirname(destination));

  // Backup existing config if requested
  if (backup && fs.existsSync(destination)) {
    backupConfig(destination);
  }

  // Copy template to destination with variable substitution
  try {
    if (force || !fs.existsSync(destination)) {
      let content = fs.readFileSync(template, 'utf8');

      // Define substitutions
      const replacements = {
        '${PROJECT_ROOT}': PROJECT_ROOT,
        '${HOME}': os.homedir(),
        '${CONFIG_ROOT}': CONFIG_ROOT,
        '${PYTHONPATH}': PROJECT_ROOT,
        '${GITHUB_TOKEN}': process.env.GITHUB_TOKEN || '$' + '{GITHUB_TOKEN}',
        '${GOOGLE_MAPS_API_KEY}': process.env.GOOGLE_MAPS_API_KEY || '$' + '{GOOGLE_MAPS_API_KEY}',
        '${WINDSURF_API_KEY}': process.env.WINDSURF_API_KEY || '$' + '{WINDSURF_API_KEY}',
        '${MCP_DIR}': path.join(CONFIG_ROOT, 'mcp'),
      };

      // Perform replacements
      for (const [key, value] of Object.entries(replacements)) {
        content = content.replace(
          new RegExp(key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'),
          value,
        );
      }

      fs.writeFileSync(destination, content);
      console.log(`   ✓ Synced successfully`);
      return true;
    } else {
      console.log(`   → File exists, use --force to overwrite`);
      return false;
    }
  } catch (error) {
    console.error(`   ✗ Error syncing: ${error.message}`);
    return false;
  }
}

function main() {
  const args = process.argv.slice(2);
  const force = args.includes('--force');
  const noBackup = args.includes('--no-backup');

  console.log('═══════════════════════════════════════════════════════');
  console.log('  AtlasTrinity Config Template Sync');
  console.log('═══════════════════════════════════════════════════════');
  console.log(`Config Root: ${CONFIG_ROOT}`);
  console.log(`Force Mode: ${force ? 'YES' : 'NO'}`);
  console.log(`Backup: ${noBackup ? 'NO' : 'YES'}`);

  let syncedCount = 0;
  let skippedCount = 0;

  for (const mapping of CONFIG_MAPPINGS) {
    const synced = syncConfig(mapping, { force, backup: !noBackup });
    if (synced) {
      syncedCount++;
    } else {
      skippedCount++;
    }
  }

  console.log('\n═══════════════════════════════════════════════════════');
  console.log(`✓ Synced: ${syncedCount} files`);
  console.log(`→ Skipped: ${skippedCount} files`);
  console.log('═══════════════════════════════════════════════════════');

  if (skippedCount > 0 && !force) {
    console.log('\nℹ️  Use --force to overwrite existing configs');
    console.log('   Example: npm run config:sync -- --force');
  }

  console.log('\n✓ Config sync complete!');
  console.log('  Run your application to apply changes.\n');
}

// Run the script
main();
