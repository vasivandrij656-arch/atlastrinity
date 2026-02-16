import sys

def analyze_proto(data, indent=0):
    offset = 0
    while offset < len(data):
        try:
            # Read tag
            tag = 0
            shift = 0
            while offset < len(data):
                b = data[offset]
                offset += 1
                tag |= (b & 0x7F) << shift
                shift += 7
                if not (b & 0x80):
                    break
            
            if tag == 0: break
            
            field_num = tag >> 3
            wire_type = tag & 0x07
            
            prefix = "  " * indent
            
            if wire_type == 0:  # Varint
                v = 0
                s = 0
                while offset < len(data):
                    b = data[offset]
                    offset += 1
                    v |= (b & 0x7F) << s
                    s += 7
                    if not (b & 0x80):
                        break
                print(f"{prefix}Field {field_num} (Varint): {v}")
                
            elif wire_type == 2:  # Length-delimited
                length = 0
                s = 0
                while offset < len(data):
                    b = data[offset]
                    offset += 1
                    length |= (b & 0x7F) << s
                    s += 7
                    if not (b & 0x80):
                        break
                
                payload = data[offset:offset+length]
                offset += length
                
                # Check if it's likely a nested message or a string
                try:
                    s_val = payload.decode('utf-8')
                    if all(32 <= ord(c) < 127 or c in '\n\r\t' for c in s_val) and len(s_val) > 0:
                        print(f"{prefix}Field {field_num} (String): {s_val[:100]}...")
                    else:
                        raise ValueError()
                except:
                    print(f"{prefix}Field {field_num} (Message - {len(payload)} bytes):")
                    analyze_proto(payload, indent + 1)
                    
            elif wire_type == 1:  # 64-bit
                print(f"{prefix}Field {field_num} (64-bit)")
                offset += 8
            elif wire_type == 5:  # 32-bit
                print(f"{prefix}Field {field_num} (32-bit)")
                offset += 4
            else:
                print(f"{prefix}Unknown wire type {wire_type} at field {field_num}")
                break
        except Exception as e:
            # print(f"Error at offset {offset}: {e}")
            break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_pb.py <file.pb>")
        sys.exit(1)
    
    with open(sys.argv[1], 'rb') as f:
        analyze_proto(f.read())
