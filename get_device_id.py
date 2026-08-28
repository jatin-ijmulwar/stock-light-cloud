import requests
import sys

def main():
    print("\n--- SmartThings Device Finder ---")
    token = input("Enter your SmartThings Personal Access Token: ").strip()
    
    if not token:
        print("Token cannot be empty!")
        sys.exit(1)
        
    url = "https://api.smartthings.com/v1/devices"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    
    print("\nFetching devices...")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        devices = response.json().get('items', [])
        
        if not devices:
            print("No devices found on this SmartThings account.")
            sys.exit(0)
            
        print("\n✅ Found these devices:\n")
        for dev in devices:
            name = dev.get('label') or dev.get('name') or "Unknown Device"
            device_id = dev.get('deviceId')
            print(f"Device Name: {name}")
            print(f"Device ID:   {device_id}")
            print("-" * 40)
            
        print("\nCopy the Device ID for your WiZ bulb and save it for the cloud project!")
        
    except requests.exceptions.HTTPError as e:
        if response.status_code == 401:
            print("❌ Unauthorized! Make sure you copied the token correctly.")
        else:
            print(f"❌ HTTP Error: {e}")
            print(response.text)
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
