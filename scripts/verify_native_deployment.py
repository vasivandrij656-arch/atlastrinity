#!/usr/bin/env python3
"""
🧪 Native Deployment Verification Script
Перевіряє нативну розгортку Windsurf MCP без Docker
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, Any

# Colors for output
RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
BLUE = '\033[0;34m'
NC = '\033[0m'

def log_info(msg: str):
    print(f"{BLUE}[INFO]{NC} {msg}")

def log_success(msg: str):
    print(f"{GREEN}[SUCCESS]{NC} {msg}")

def log_warning(msg: str):
    print(f"{YELLOW}[WARNING]{NC} {msg}")

def log_error(msg: str):
    print(f"{RED}[ERROR]{NC} {msg}")

def get_project_root() -> Path:
    return Path(__file__).parent.parent

def check_prerequisites() -> bool:
    """Перевіряє необхідні залежності"""
    log_info("Checking prerequisites...")
    
    all_good = True
    
    # Check Swift
    try:
        result = subprocess.run(['swift', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_success(f"✅ Swift: {result.stdout.strip()}")
        else:
            log_error("❌ Swift not found")
            all_good = False
    except FileNotFoundError:
        log_error("❌ Swift not found")
        all_good = False
    
    # Check Python
    try:
        result = subprocess.run(['python3', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_success(f"✅ Python: {result.stdout.strip()}")
        else:
            log_error("❌ Python not found")
            all_good = False
    except FileNotFoundError:
        log_error("❌ Python not found")
        all_good = False
    
    # Check Node.js
    try:
        result = subprocess.run(['node', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            log_success(f"✅ Node.js: {result.stdout.strip()}")
        else:
            log_error("❌ Node.js not found")
            all_good = False
    except FileNotFoundError:
        log_error("❌ Node.js not found")
        all_good = False
    
    return all_good

def check_windsurf_binary() -> bool:
    """Перевіряє Windsurf MCP бінарний файл"""
    log_info("Checking Windsurf MCP binary...")
    
    project_root = get_project_root()
    binary_path = project_root / "vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
    
    if not binary_path.exists():
        log_error(f"❌ Binary not found: {binary_path}")
        return False
    
    if not os.access(binary_path, os.X_OK):
        log_error(f"❌ Binary not executable: {binary_path}")
        return False
    
    # Get file info
    stat = binary_path.stat()
    size_mb = stat.st_size / (1024 * 1024)
    log_success(f"✅ Binary found: {binary_path}")
    log_info(f"   Size: {size_mb:.1f} MB")
    log_info(f"   Modified: {stat.st_mtime}")
    
    return True

def check_configuration() -> bool:
    """Перевіряє конфігураційні файли"""
    log_info("Checking configuration...")
    
    config_dir = Path.home() / ".config" / "atlastrinity"
    env_file = config_dir / ".env"
    config_file = config_dir / "config.yaml"
    
    all_good = True
    
    if not config_dir.exists():
        log_error(f"❌ Config directory not found: {config_dir}")
        all_good = False
    else:
        log_success(f"✅ Config directory: {config_dir}")
    
    if not env_file.exists():
        log_warning(f"⚠️  Environment file not found: {env_file}")
        all_good = False
    else:
        log_success(f"✅ Environment file: {env_file}")
        
        # Check for required environment variables
        with open(env_file) as f:
            content = f.read()
            if 'WINDSURF_API_KEY' in content:
                log_success("✅ WINDSURF_API_KEY found")
            else:
                log_warning("⚠️  WINDSURF_API_KEY not found")
    
    if not config_file.exists():
        log_error(f"❌ Config file not found: {config_file}")
        all_good = False
    else:
        log_success(f"✅ Config file: {config_file}")
    
    return all_good

def check_mcp_integration() -> bool:
    """Перевіряє MCP інтеграцію"""
    log_info("Checking MCP integration...")
    
    try:
        # Change to project root
        project_root = get_project_root()
        os.chdir(project_root)
        
        # Test MCP status
        result = subprocess.run(['npm', 'run', 'mcp:status'], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            log_success("✅ MCP status check passed")
            log_info("Output:")
            for line in result.stdout.split('\n')[:5]:
                if line.strip():
                    log_info(f"   {line}")
        else:
            log_warning("⚠️  MCP status check failed")
            log_error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log_error("❌ MCP status check timed out")
        return False
    except Exception as e:
        log_error(f"❌ MCP status check error: {e}")
        return False
    
    return True

def test_windsurf_mcp_connection() -> bool:
    """Тестує з'єднання з Windsurf MCP"""
    log_info("Testing Windsurf MCP connection...")
    
    try:
        project_root = get_project_root()
        binary_path = project_root / "vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf"
        
        # Test binary with --help
        result = subprocess.run([str(binary_path), '--help'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            log_success("✅ Windsurf MCP binary responds to --help")
            return True
        else:
            log_warning("⚠️  Windsurf MCP binary --help failed")
            log_error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log_error("❌ Windsurf MCP binary test timed out")
        return False
    except Exception as e:
        log_error(f"❌ Windsurf MCP binary test error: {e}")
        return False

def check_python_integration() -> bool:
    """Перевіряє Python інтеграцію"""
    log_info("Checking Python MCP integration...")
    
    try:
        project_root = get_project_root()
        os.chdir(project_root)
        
        # Test Python MCP manager
        test_code = '''
import sys
sys.path.insert(0, 'src')
try:
    from brain.mcp.mcp_manager import MCPManager
    print("MCPManager import: OK")
    
    import asyncio
    async def test():
        manager = MCPManager()
        return True
    
    result = asyncio.run(test())
    print("MCPManager test: OK")
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
'''
        
        result = subprocess.run(['python3', '-c', test_code], 
                              capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            log_success("✅ Python MCP integration test passed")
            return True
        else:
            log_warning("⚠️  Python MCP integration test failed")
            log_error(f"Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log_error("❌ Python MCP integration test timed out")
        return False
    except Exception as e:
        log_error(f"❌ Python MCP integration test error: {e}")
        return False

def check_electron_build() -> bool:
    """Перевіряє Electron build"""
    log_info("Checking Electron build...")
    
    project_root = get_project_root()
    dist_dir = project_root / "dist"
    
    if not dist_dir.exists():
        log_warning("⚠️  Electron build directory not found")
        return False
    
    # Check for main.js
    main_js = dist_dir / "main" / "main.js"
    if not main_js.exists():
        log_warning("⚠️  Electron main.js not found")
        return False
    
    log_success(f"✅ Electron build found: {dist_dir}")
    return True

def check_package_json() -> bool:
    """Перевіряє package.json конфігурацію"""
    log_info("Checking package.json configuration...")
    
    project_root = get_project_root()
    package_json = project_root / "package.json"
    
    if not package_json.exists():
        log_error("❌ package.json not found")
        return False
    
    try:
        with open(package_json) as f:
            config = json.load(f)
        
        # Check for Windsurf MCP in extraResources
        extra_resources = config.get('build', {}).get('extraResources', [])
        windsurf_resource = None
        
        for resource in extra_resources:
            if resource.get('from') == 'vendor/mcp-server-windsurf/.build/release/mcp-server-windsurf':
                windsurf_resource = resource
                break
        
        if windsurf_resource:
            log_success("✅ Windsurf MCP found in extraResources")
            log_info(f"   From: {windsurf_resource['from']}")
            log_info(f"   To: {windsurf_resource['to']}")
        else:
            log_warning("⚠️  Windsurf MCP not found in extraResources")
        
        # Check scripts
        scripts = config.get('scripts', {})
        if 'mcp:status' in scripts:
            log_success("✅ MCP status script found")
        else:
            log_warning("⚠️  MCP status script not found")
        
        return True
        
    except Exception as e:
        log_error(f"❌ Error reading package.json: {e}")
        return False

def generate_report() -> Dict[str, Any]:
    """Генерує звіт про стан розгортки"""
    project_root = get_project_root()
    
    report = {
        'timestamp': os.path.getctime(project_root),
        'project_root': str(project_root),
        'checks': {
            'prerequisites': check_prerequisites(),
            'windsurf_binary': check_windsurf_binary(),
            'configuration': check_configuration(),
            'mcp_integration': check_mcp_integration(),
            'python_integration': check_python_integration(),
            'electron_build': check_electron_build(),
            'package_json': check_package_json()
        },
        'summary': {
            'total_checks': 8,
            'passed_checks': 0,
            'failed_checks': 0,
            'warnings': 0
        }
    }
    
    # Count passed/failed checks
    passed = sum(1 for result in report['checks'].values() if result)
    failed = len(report['checks']) - passed
    
    report['summary']['passed_checks'] = passed
    report['summary']['failed_checks'] = failed
    
    report['summary']['status'] = (
        'PASS' if report['summary']['failed_checks'] == 0 else 'FAIL'
    )
    
    return report

def main():
    """Головна функція"""
    print("🧪 AtlasTrinity Native Deployment Verification")
    print("==========================================")
    print()
    
    # Generate report
    report = generate_report()
    
    # Print results
    print(f"📊 Deployment Report")
    print(f"==================")
    print(f"Timestamp: {report['timestamp']}")
    print(f"Project Root: {report['project_root']}")
    print()
    
    print("🔍 Check Results:")
    print("---------------")
    
    for check_name, result in report['checks'].items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} {check_name}")
    
    print()
    print("📈 Summary:")
    print("-----------")
    summary = report['summary']
    print(f"Status: {summary['status']}")
    print(f"Total Checks: {summary['total_checks']}")
    print(f"Passed: {summary['passed_checks']}")
    print(f"Failed: {summary['failed_checks']}")
    print()
    
    # Recommendations
    if summary['status'] == 'PASS':
        print("🎉 All checks passed! Native deployment is ready.")
        print()
        print("🚀 Next steps:")
        print("1. Update API keys in ~/.config/atlastrinity/.env")
        print("2. Start application: npm run dev")
        print("3. Or start Windsurf MCP only: ./scripts/start_windsurf_native.sh")
        print("4. Check MCP status: npm run mcp:status")
    else:
        print("❌ Some checks failed. Please address the issues above.")
        print()
        print("🔧 Troubleshooting:")
        print("1. Install missing prerequisites (Swift, Python, Node.js)")
        print("2. Run deployment script: ./scripts/deploy_windsurf_native.sh")
        print("3. Update configuration files")
        print("4. Check logs for detailed error information")
    
    # Save report to file
    report_file = get_project_root() / "native_deployment_report.json"
    try:
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        log_success(f"Report saved to: {report_file}")
    except Exception as e:
        log_warning(f"Failed to save report: {e}")
    
    # Exit with appropriate code
    sys.exit(0 if summary['status'] == 'PASS' else 1)

if __name__ == "__main__":
    main()
