import json
import sys

def main():
    with open('core.config_entries.json', 'r') as f:
        config = json.load(f)
        
    for entry in config['data']['entries']:
        if entry['domain'] == 'starlink_ha':
            # Set a valid unique_id to force entity creation
            entry['unique_id'] = "starlink_0100000000000000008B65AD"
            print(f"Fixed unique_id for {entry['entry_id']}")
            
    with open('core.config_entries.json', 'w') as f:
        json.dump(config, f, indent=2)

if __name__ == "__main__":
    main()
