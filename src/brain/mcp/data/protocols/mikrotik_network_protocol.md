# MikroTik Network Protocol (v1.0)

## 🎯 Purpose

This protocol defines the standard procedures for MikroTik router interactions, network monitoring, logging, and security operations within the AtlasTrinity system.

## 🔌 Connection Configuration

### Primary Connection Details
```yaml
mikrotik_connection:
  host: "192.168.88.1"
  port: 666
  username: "admin"
  authentication_method: "ssh_key"
  ssh_options:
    - "StrictHostKeyChecking=no"
    - "UserKnownHostsFile=/dev/null"
  
network_context:
  subnet: "192.168.88.0/24"
  gateway: "192.168.88.1"
  dns_servers: ["192.168.88.1"]
  dhcp_range: "192.168.88.100-192.168.88.200"
```

### SSH Key Management
```yaml
ssh_key_locations:
  primary: "~/.ssh/id_rsa"
  project_specific: "~/.ssh/mikrotik_key"
  fallback_keys:
    - "~/.ssh/atlastrinity_mikrotik"
    - "./config/ssh/mikrotik_key"

key_requirements:
  type: "RSA"
  bits: 2048
  permissions: "600"
  passphrase: "none"
```

## 📊 Logging Infrastructure

### Log Collection System
```yaml
logging_system:
  script_location: "/scripts/mikrotik_logger.py"
  log_directory: "/Users/dev/.config/atlastrinity/logs/mikrotik"
  max_file_size: "1MB"
  rotation_policy: "automatic"
  
log_sources:
  - system_logs: "/log print detail show-ids"
  - firewall_logs: "/ip firewall filter print"
  - connection_tracking: "/ip connection print"
  - interface_stats: "/interface print stats"
  - dhcp_leases: "/ip dhcp-server lease print"
```

### Log File Structure
```yaml
log_file_format:
  naming: "mikrotik_{index}.log"
  metadata_file: ".last_id"
  content_structure:
    - timestamp
    - log_id
    - message
    - facility
    - severity
    
retention_policy:
  max_files: 10
  max_age_days: 30
  compression: "gzip"
```

## 🛡 Security & Access Control

### Authentication Protocol
```yaml
authentication_flow:
  1. Check SSH key availability
  2. Establish SSH connection on port 666
  3. Verify RouterOS version compatibility
  4. Validate administrative privileges
  5. Enable secure logging session

security_measures:
  - Port obfuscation (666 instead of 22)
  - SSH key authentication only
  - No password fallback
  - Connection timeout: 60 seconds
  - Rate limiting: 10 connections/minute
```

### Network Access Patterns
```yaml
access_patterns:
  management_subnet: "192.168.88.0/24"
  allowed_sources:
    - "192.168.88.10"  # Main workstation
    - "192.168.88.20"  # Secondary admin
    - "192.168.88.22"  # Current workstation (MAC: 9c:76:0e:48:90:fc)
    - "192.168.88.100" # Kali Linux VM
  
workstation_details:
  current_ip: "192.168.88.22"
  mac_address: "9c:76:0e:48:90:fc"
  interface: "en0"
  subnet_mask: "255.255.255.0"
  
forbidden_actions:
  - "Disable firewall rules"
  - "Modify SSH configuration"
  - "Change admin credentials"
  - "Disable logging"
```

## 🔧 Network Operations Protocol

### Discovery Phase
```yaml
network_discovery:
  prerequisites:
    - Verify own IP with `ifconfig` (current: 192.168.88.22)
    - Confirm gateway accessibility
    - Check SSH key availability
    
current_workstation:
  ip_address: "192.168.88.22"
  mac_address: "9c:76:0e:48:90:fc"
  interface: "en0"
  
commands:
  interface_check: "ifconfig | grep 192.168.88"
  gateway_ping: "ping -c 3 192.168.88.1"
  ssh_test: "ssh -p 666 admin@192.168.88.1 /system resource print"
```

### Monitoring Operations
```yaml
monitoring_tasks:
  network_status:
    - "/interface print stats"
    - "/ip route print"
    - "/ip firewall connection print"
    
  security_monitoring:
    - "/log print where topics~\"firewall\""
    - "/ip hotspot active print"
    - "/tool torch interface=ether1"
    
  system_health:
    - "/system resource print"
    - "/system health print"
    - "/user active print"
```

### Configuration Management
```yaml
configuration_backup:
  frequency: "daily"
  location: "/backups/mikrotik/"
  format: "RouterOS script"
  retention: "30 days"

critical_configs:
  - "/export"
  - "/ip firewall export"
  - "/interface export"
  - "/ip dhcp-server export"
```

## 🚨 Emergency Procedures

### Connection Failures
```yaml
troubleshooting_steps:
  1. Verify network connectivity
  2. Check SSH key permissions
  3. Validate MikroTik availability
  4. Test alternative ports
  5. Review firewall rules
  
diagnostic_commands:
  network_check: "ping -c 3 192.168.88.1"
  port_scan: "nmap -p 666 192.168.88.1"
  ssh_debug: "ssh -v -p 666 admin@192.168.88.1"
```

### Security Incidents
```yaml
incident_response:
  immediate_actions:
    - "/ip firewall filter add chain=input src-address=<suspicious_ip> action=drop"
    - "/log print where topics~\"critical\""
    - "/user active print"
    
  forensic_collection:
    - "/log print detail show-ids"
    - "/ip connection print"
    - "/tool sniffer quick start"
```

## 🔄 Integration with Other Protocols

### Protocol Dependencies
```yaml
required_imports:
  - "system_monitoring_protocol.md"  # For system state verification
  - "hacking_sysadmin_protocol.md"   # For network security operations
  
integration_points:
  task_protocol: "Include MikroTik checks for network-dependent tasks"
  search_protocol: "Use MikroTik logs for network forensics"
  system_mastery: "Leverage MikroTik for network control"
```

### Auto-Import Directive
```yaml
auto_import_triggers:
  - task_mentions: ["network", "router", "mikrotik", "firewall"]
  - operation_requires: ["port_forwarding", "nat_rules", "dhcp_config"]
  - security_context: ["network_monitoring", "intrusion_detection"]
  
import_statement: |
  // Auto-import MikroTik Network Protocol for network operations
  include_protocol("mikrotik_network_protocol.md")
```

## 📋 Quick Reference

### Essential Commands
```bash
# Quick connection test
ssh -p 666 admin@192.168.88.1 /system resource print

# Log collection
python3 /scripts/mikrotik_logger.py

# Network status
ssh -p 666 admin@192.168.88.1 "/interface print stats; /ip route print"

# Firewall status
ssh -p 666 admin@192.168.88.1 "/ip firewall filter print"
```

### File Locations
```yaml
critical_files:
  logger_script: "/scripts/mikrotik_logger.py"
  log_directory: "/Users/dev/.config/atlastrinity/logs/mikrotik/"
  ssh_keys: "~/.ssh/"
  backups: "/backups/mikrotik/"
```

---

## 📝 Version History

- **v1.0** (2026-02-15): Initial protocol definition
  - Connection configuration
  - Logging infrastructure
  - Security procedures
  - Integration framework

---

**Owner:** Network Operations Team  
**Maintenance:** AtlasTrinity System  
**Status:** ACTIVE - Ready for deployment
**Classification:** Internal Use Only
