import subprocess

REMOTE_SCRIPT = """import os

plists = {
  "/Library/LaunchDaemons/com.thverify.server.plist": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.server</string>
  <key>UserName</key><string>visarutsankham</string>
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
</plist>''',

  "/Library/LaunchDaemons/com.thverify.public.plist": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.public</string>
  <key>UserName</key><string>visarutsankham</string>
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
</plist>''',

  "/Library/LaunchDaemons/com.thverify.tunnel.plist": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.tunnel</string>
  <key>UserName</key><string>visarutsankham</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/visarutsankham/bin/cloudflared</string>
    <string>--config</string>
    <string>/Users/visarutsankham/.cloudflared/th-verify-public.yml</string>
    <string>tunnel</string>
    <string>run</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/visarutsankham/th-verify</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/tunnel.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/tunnel.err</string>
</dict>
</plist>''',

  "/Library/LaunchDaemons/com.thverify.daily-sync.plist": '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.thverify.daily-sync</string>
  <key>UserName</key><string>visarutsankham</string>
  <key>WorkingDirectory</key><string>/Users/visarutsankham/th-verify</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>/Users/visarutsankham/th-verify/scripts/daily_sync.sh</string></array>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>3</integer><key>Minute</key><integer>30</integer></dict>
  <key>StandardOutPath</key><string>/Users/visarutsankham/th-verify/data/logs/launchd.out</string>
  <key>StandardErrorPath</key><string>/Users/visarutsankham/th-verify/data/logs/launchd.err</string>
</dict>
</plist>'''
}

for path, content in plists.items():
    with open(path, 'w') as f:
        f.write(content)
    os.chmod(path, 0o644)
    print(f"Installed {path}")
"""

def main():
    # Write remote script to /tmp/inst.py on lighthouse-core
    write_cmd = f"cat << 'EOF' > /tmp/inst.py\n{REMOTE_SCRIPT}\nEOF\n"
    subprocess.run(["ssh", "lighthouse-core", write_cmd], check=True)

    # Execute it with sudo
    exec_cmd = "echo popartpop01 | sudo -S python3 /tmp/inst.py"
    res = subprocess.run(["ssh", "lighthouse-core", exec_cmd], capture_output=True, text=True)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)

    # Bootstrap the launchdaemons into system domain
    bootstrap_cmd = (
        "echo popartpop01 | sudo -S launchctl bootstrap system /Library/LaunchDaemons/com.thverify.server.plist && "
        "echo popartpop01 | sudo -S launchctl bootstrap system /Library/LaunchDaemons/com.thverify.public.plist && "
        "echo popartpop01 | sudo -S launchctl bootstrap system /Library/LaunchDaemons/com.thverify.tunnel.plist && "
        "echo popartpop01 | sudo -S launchctl bootstrap system /Library/LaunchDaemons/com.thverify.daily-sync.plist"
    )
    res2 = subprocess.run(["ssh", "lighthouse-core", bootstrap_cmd], capture_output=True, text=True)
    print("BOOTSTRAP STDOUT:", res2.stdout)
    print("BOOTSTRAP STDERR:", res2.stderr)

if __name__ == "__main__":
    main()
