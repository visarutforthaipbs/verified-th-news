import subprocess

PLISTS = {
    "/Users/visarutsankham/Library/LaunchAgents/com.thverify.daily-sync.plist": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.daily-sync</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>StandardIO</string>
    <string>LoginWindow</string>
  </array>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>/Users/visarutsankham/th-verify/scripts/daily_sync.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/launchd.err</string>
</dict>
</plist>
""",
    "/Users/visarutsankham/Library/LaunchAgents/com.thverify.monthly-brief.plist": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.monthly-brief</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>StandardIO</string>
    <string>LoginWindow</string>
  </array>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/visarutsankham/th-verify/.venv/bin/python</string>
    <string>scripts/build_brief.py</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/visarutsankham/th-verify</string>
  <key>StartCalendarInterval</key>
  <dict><key>Day</key><integer>1</integer><key>Hour</key><integer>4</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/brief.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/brief.err</string>
</dict>
</plist>
""",
    "/Users/visarutsankham/Library/LaunchAgents/com.thverify.server.plist": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.server</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>StandardIO</string>
    <string>LoginWindow</string>
  </array>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/visarutsankham/th-verify/.venv/bin/uvicorn</string>
    <string>th_verify.api:app</string>
    <string>--host</string><string>0.0.0.0</string>
    <string>--port</string><string>8942</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/visarutsankham/th-verify</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/server.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/server.err</string>
</dict>
</plist>
""",
    "/Users/visarutsankham/Library/LaunchAgents/com.thverify.public.plist": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.public</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>StandardIO</string>
    <string>LoginWindow</string>
  </array>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/visarutsankham/th-verify/.venv/bin/uvicorn</string>
    <string>th_verify.api:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8943</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict><key>TH_VERIFY_READONLY</key><string>1</string></dict>
  <key>WorkingDirectory</key><string>/Users/visarutsankham/th-verify</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/public.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/public.err</string>
</dict>
</plist>
""",
    "/Users/visarutsankham/Library/LaunchAgents/com.thverify.tunnel.plist": """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.tunnel</string>
  <key>LimitLoadToSessionType</key>
  <array>
    <string>Aqua</string>
    <string>Background</string>
    <string>StandardIO</string>
    <string>LoginWindow</string>
  </array>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/visarutsankham/bin/cloudflared</string>
    <string>--config</string>
    <string>/Users/visarutsankham/.cloudflared/th-verify-public.yml</string>
    <string>tunnel</string>
    <string>run</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/tunnel.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/tunnel.err</string>
</dict>
</plist>
""",
}

def main():
    for path, content in PLISTS.items():
        cmd = f"cat << 'EOF' > {path}\n{content}\nEOF\n"
        res = subprocess.run(["ssh", "lighthouse-core", cmd], capture_output=True, text=True)
        if res.returncode == 0:
            print(f"Successfully updated {path}")
        else:
            print(f"Error updating {path}: {res.stderr}")

if __name__ == "__main__":
    main()
