<<<<<<< HEAD
# N-Console 22.0.2 — Final Installer-Ready Source

## Compatibility strategy

Windows applications cannot be one native binary that is simultaneously x86 and x64.
This project therefore supports both by building:
- x64 build + x64 installer
- x86 build + x86 installer

The x86 build runs on both 32-bit and 64-bit Windows 10/11. The x64 build runs on 64-bit Windows.

The application does not hard-code a Windows 10/11-only version check, so normal future Windows releases can run it as long as Microsoft maintains the required Win32/.NET/Qt compatibility.

## Splash

The splash is full-screen, uses the supplied icon and illustration without overlap,
shows 1% → 100%, and is guaranteed not to close before 8 seconds.

## Build prerequisites

Install:
- Python 3.11 or newer
- Inno Setup 6

Install Python packages:

    py -m pip install -r requirements.txt
    py -m pip install pyinstaller pillow

Create ICO:

    py make_ico.py

### x64 build

    py -m PyInstaller --noconfirm --clean --windowed --onedir --name "N-Console" --icon "assets\\n_console_icon.ico" --add-data "assets;assets" --distpath "build\\N-Console-x64" main.py

Compile:
    installer\\N-Console-x64.iss

### x86 build

Build with a 32-bit Python environment, then:

    py -m PyInstaller --noconfirm --clean --windowed --onedir --name "N-Console" --icon "assets\\n_console_icon.ico" --add-data "assets;assets" --distpath "build\\N-Console-x86" main.py

Compile:
    installer\\N-Console-x86.iss

## Installation result

- Desktop shortcut
- Start Menu / All Programs entry
- Uninstaller
- Application icon
- Program Files installation
- Per-user SQLite data under %LOCALAPPDATA%\\N-Console

## Important

Do not put the database inside Program Files because standard users may not have write permission.


## Scanner service behavior in this revision

- TCP service detection is independent of ICMP ping.
- Therefore a device that blocks ICMP but has TCP/3389 open is still marked reachable and RDP is shown.
- Common infrastructure/service ports are scanned by default.
- Optional Deep Port Scan checks TCP 1–65535; use it for small ranges because it is intentionally slower.
- Every detected service is rendered as a blue clickable button with a green check mark.
- HTTP/HTTPS open in the browser.
- RDP opens Windows Remote Desktop.
- SSH/Telnet launch their corresponding clients.
- FTP opens an FTP URL.
- SMB opens the Windows network location.
- Other services are shown with their port and can be extended with protocol-specific launchers.

The service buttons are placed directly in the Services column; no extra popup is required.

## v4 scanner stability/layout update

- Deep scanning is moved to a background QThread/worker architecture, so the Windows UI does not become "Python is not responding" while a scan is running.
- Deep scan is cancellable.
- A common TCP scan is performed first. Deep 1–65535 scanning is performed only for hosts that are reachable by ICMP or expose a common TCP service, which avoids wasting the deep scan on dead hosts.
- Services use a wrapping button layout inside each table cell, so buttons never overlap. Row height expands for multiple services.
- Service buttons are blue with a check mark and open supported protocols directly.
- Inno Setup scripts create a Desktop shortcut, Start Menu/All Programs entry, and uninstaller.


## Ping & Route Diagnostics

The final UI includes a dedicated Ping & Route page:
- Ping a single IP address or hostname.
- Select 1–100 echo requests.
- Shows reachability, last latency and packet loss.
- Stop an active ping sequence.
- Run Windows `tracert` (or `traceroute` on non-Windows systems).
- Shows the route output and counts detected hops.
- Runs command-line diagnostics without blocking the Qt UI.


## Network Diagnostics v1.1

Predefined diagnostic modules:
- IP Configuration (`ipconfig /all`)
- ARP Table (`arp -a`)
- Route Table (`route print`)
- Network Connections (`netstat -ano`)
- DNS Cache (`ipconfig /displaydns`)
- DNS Lookup (`nslookup`)
- Hostname (`hostname`)
- MAC Addresses (`getmac /v`)
- Wi-Fi Information (`netsh wlan show interfaces`)
- Firewall Status (`netsh advfirewall show allprofiles`)
- TCP Port Test (`Test-NetConnection`)
- Flush DNS (`ipconfig /flushdns`)
- Release IP (`ipconfig /release`)
- Renew IP (`ipconfig /renew`)
- Save diagnostic output to TXT
- Non-blocking command execution through Qt QProcess


## v1.2 diagnostic fixes

- Fixed `QTextCursor.End` PySide6 AttributeError.
- Added missing `re` import used by ping latency parsing.
- Ping now correctly parses Windows `time<1ms` and `time=...ms`.
- Ping UI no longer reports a false Python error after a successful reply.
- Trace Route output runs through the diagnostic process without blocking the GUI.
- Network Diagnostics now includes Run ALL Diagnostics.
- Each diagnostic result is appended to one report view.
- Target-specific DNS/reverse lookup and TCP port testing are available.
- Ping/Trace buttons from Network Diagnostics open the dedicated Ping & Route page.
- Splash is true full-screen and retains the minimum 8-second loading requirement.


## v1.3 Built-in Telnet terminal

- Telnet command line is docked directly under the terminal viewport.
- No separate password/input popup is used.
- Continuous socket reader prevents output from stopping after the initial buffer.
- Telnet negotiation (IAC/WILL/WONT/DO/DONT) is handled.
- Large outputs continuously append and auto-scroll.
- 8 KB socket reads reduce truncation/stalling on large switch outputs.
- UTF-8 with CP437 fallback helps preserve device text/box characters.
- IP Scanner TELNET service actions can open the built-in terminal.


## v1.3.1 hotfix
- Added missing PySide6 `QPlainTextEdit` import required by the built-in Telnet terminal.


## v1.4 Remote Access / SSH / Telnet
- Built-in Telnet connection bar with host and port.
- Built-in SSH terminal using Paramiko; no Windows ssh.exe required for GUI SSH.
- SSH username/password fields with masked password input.
- RDP launches the native Windows mstsc.exe client.
- IP Scanner service buttons route SSH/Telnet/RDP into N-Console.
- Large SSH/Telnet output streams continuously.
- Passwords are not written to connection history.


## v1.5 Telnet final fix
- Added permanently visible Host/IP and Port fields above the terminal.
- Added working Connect button.
- Direct IP Scanner Telnet launches still use the same built-in terminal.
- Large output streaming and Telnet negotiation from v1.4 are retained.


## v1.6 FINAL Telnet fix
- Fixed Qt QRect service-layout crash.
- Telnet socket output now reaches the GUI through Qt signals.
- Telnet IAC negotiation handles data split across socket reads.
- 16 KB receive buffer supports large switch output.
- CRLF commands supported.


## v1.7 FINAL PuTTY-style Telnet terminal
- Removed the separate bottom command card.
- Commands are typed directly into the terminal surface.
- Enter sends the current terminal command.
- Ctrl+C sends an interrupt.
- Automatic cleanup of ANSI/control characters.
- Automatic handling of `--More--` pager prompts by sending a space.
- Pager markers are removed from the visible output.
- Large Telnet output remains in one continuous terminal.


## v1.8 Physical Serial Console
- Added Serial Console for physical switch/router console access through USB-to-Serial/COM.
- COM-port discovery with Refresh.
- Baud: 9600/19200/38400/57600/115200.
- Data bits, parity and stop bits selectable.
- Direct in-terminal typing; no separate command box.
- Non-wrapping professional terminal.
- Output is rendered in controlled 18 ms / 4 KB chunks to avoid a huge result appearing in one instant.
- Telnet output uses the same controlled rendering so long commands look more natural.

## v1.9 Terminal Input/History Fix
- Prevents locally typed commands from being displayed twice when the network device echoes them.
- Up Arrow recalls previous commands.
- Down Arrow moves forward through command history and restores the current line.
- Enter clears the local input before transmission so the device echo is the single displayed command.
- Ctrl+U clears the active command line.
- Terminal remains non-wrapping and protects previous device output.

## v1.1.0 Telnet Terminal Polish
- Telnet authentication password input is masked inside the terminal and is never saved to command history.
- Device prompt/output is protected from accidental editing.
- Active input is preserved if asynchronous device output arrives.
- Command execution temporarily locks the input line until a network-device prompt returns, preventing prompt corruption while output is streaming.
- Up/Down command history remains available for completed commands.
- Long output is rendered progressively at a controlled cadence (1024-byte chunks / 35 ms) instead of appearing as one instant block.
- Telnet line endings/control characters are normalized to keep columns and prompts stable.
- Fake local host prompt was removed; the actual device prompt is displayed by the Telnet session.


## v1.9 MAC + Smooth Telnet
- Improved Windows MAC/neighbor resolution using ARP, Get-NetNeighbor and netsh fallbacks.
- MAC is resolved for reachable hosts whether reachability was detected by ICMP or TCP.
- Telnet output cadence adjusted to 45 ms / 768-byte chunks for smoother progressive rendering.


## v1.9 IP Scanner MAC + Hostname Fix
- Fixed Windows ARP MAC parsing.
- MAC lookup now retries after refreshing the local neighbor entry.
- Uses ARP, Get-NetNeighbor and netsh neighbor fallbacks.
- Hostname resolution now uses reverse DNS, ping -a, NetBIOS nbtstat and Resolve-DnsName fallbacks.
- Hostname lookup is performed only for reachable hosts so large CIDR scans remain responsive.
- MAC addresses are necessarily limited to devices visible through the local L2/neighbor table; routed remote hosts may not expose their MAC to the scanning PC.


## v2.0 Subnet Calculator
- Added IPv4 CIDR calculator with /0 through /32 support.
- Calculates network, subnet mask, wildcard, broadcast, first/last usable, total addresses and usable hosts.
- Shows Class A/B/C/D/E classification.
- Exports a professionally formatted Excel report with auto-fit widths and freeze panes.

## IP Scanner MAC/Hostname behavior
- MAC lookup is refreshed through Windows ARP/neighbor sources after reachability testing.
- Hostname lookup uses reverse DNS/Windows fallbacks.
- A remote device behind a routed VPN cannot expose its own MAC address to the scanning PC through normal Windows ARP; the MAC visible to the scanner is normally the next-hop/gateway. A device MAC across a routed VPN requires querying the remote gateway/switch (for example via SNMP/API).


## v2.1 Complete Subnet Inventory
- Subnet Calculator now displays every address in the calculated IPv4 range.
- Each IP is classified as Network, Host, Broadcast, or Point-to-Point.
- Default Gateway supports automatic first-usable selection or a custom gateway.
- Excel export includes a summary sheet and a Complete IP List sheet.
- GUI limits extremely large ranges to keep the application responsive; Excel safely respects the workbook row limit.


## v1.2.0 — Scanner Refresh & Dashboard Refresh
- Cancelled IP scans release the CIDR/worker controls immediately.
- A new CIDR can be entered and scanned without closing N-Console.
- Local IPv4-to-MAC mapping is collected from Windows network adapters, so the PC running N-Console can show its own MAC when its IP is in the scan range.
- Dashboard includes a full-app Refresh button.
- Application version updated to 1.2.0.
- Inno Setup x86/x64 version metadata updated to 1.2.0.


## v22.0.1 — Scanner Thread Safety Fix
- Fixed PySide6 cross-thread UI updates during IP scanning.
- Scanner worker signals now use QObject-bound queued slots instead of lambdas.
- Cancel/restart can safely be used without closing N-Console.
- Stale results from a cancelled scan are ignored.
- Version updated to 22.0.1.


## v22.0.1 Scanner ordering fix

- Live IP Scanner rows are inserted in numeric IPv4 order while scanning.
- Results now appear as `.1, .2, .3 ... .254` and then continue into the next subnet, regardless of which worker finishes first.
- Excel export remains numerically sorted as well.
- x64 Inno Setup source paths are corrected for the project/installer folder layout.
- Desktop and Start Menu shortcuts remain enabled.


## Splash Asset Fix — 22.0.1
The splash screen now resolves icon and illustration assets from PyInstaller `_MEIPASS`, the installed application directory, and source mode. The build script validates all three required assets before building.
=======
# N-Console
N-Console — A Windows-based network administration toolkit for SSH, Telnet, RDP, IP scanning, subnet calculation, diagnostics, ping/traceroute, and connection auditing.
>>>>>>> b1fd001b3170c9c62e9ecaecd3ce04c2b5bea63b


## v22.0.2 Scanner console-window fix

- All Python `subprocess.run()` calls now use a Windows `CREATE_NO_WINDOW` wrapper.
- IP Scanner CLI probes such as `ping`, `arp`, `netsh`, `nbtstat`, and PowerShell run without opening visible console windows.
- Large scans such as /22 or 1024+ hosts therefore remain inside the N-Console UI instead of creating one window per probe.
