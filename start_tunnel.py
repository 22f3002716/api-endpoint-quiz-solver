"""
Start ngrok tunnel using pyngrok (no manual download needed)
"""
from pyngrok import ngrok

# Start tunnel
public_url = ngrok.connect(5000)
print(f"\n{'='*60}")
print(f"🌐 Public URL: {public_url}")
print(f"{'='*60}\n")
print(f"Update quick_test.py with:")
print(f'CUSTOM_QUIZ_BASE = "{public_url}"\n')
print("Press Ctrl+C to stop tunnel...")

try:
    # Keep running
    import time
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n✅ Tunnel stopped")
    ngrok.disconnect(public_url)
