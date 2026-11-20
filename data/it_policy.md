# GoAified Information Technology & Security Policy Manual
**Document ID:** GOA-IT-POL-2026-V1  
**Last Revised:** November 2026  
**Applicability:** All Employees, Engineers, Interns, and Contractors

---

## Section 1: Enterprise Network, VPN & Remote Access Policy

### 1.1 Secure VPN Configuration
All remote team members requiring access to internal staging clusters, development databases, CI/CD runners, and internal web portals must connect through the GoAified Corporate VPN.
- **Client Protocol:** OpenVPN / WireGuard protocol using client certificates and TOTP multi-factor authentication (MFA).
- **Setup Procedure:**
  1. Download the approved VPN Client from `https://software.goaified.internal/vpn`.
  2. Log in with your corporate Google SSO credentials (`@goaified.com`) to generate your encrypted client configuration profile (`goaified-vpn.ovpn`).
  3. Import the configuration profile into the VPN client.
  4. Primary Server Gateway: `vpn-gateway.goaified.com:1194` (UDP).
  5. Authenticate with your SSO username and prompt your mobile Authenticator app for 6-digit TOTP verification.

### 1.2 Troubleshooting Dropped VPN Connections
If your VPN connection drops unexpectedly, freezes, or fails to authenticate:
1. **Network Check:** Verify local network connectivity by pinging public DNS (`8.8.8.8` or `1.1.1.1`).
2. **Clock Synchronization:** Ensure your operating system clock is synchronized with internet time servers (NTP). A system time drift of more than 60 seconds causes TOTP and Kerberos handshake validation failures.
3. **Flush Local DNS Cache:**
   - Windows: Execute `ipconfig /flushdns` in Command Prompt.
   - macOS: Execute `sudo dscacheutil -flushcache; sudo killall -HUP mDNSResponder`.
   - Linux: Execute `sudo systemd-resolve --flush-caches`.
4. **Secondary Gateway Fallback:** If the primary gateway is unresponsive, toggle the gateway setting to the backup server: `vpn-backup.goaified.com:1194`.
5. **IT Escalation:** If connection errors persist (e.g., `TLS Error: TLS key negotiation failed` or `AUTH_FAILED`), raise an IT Helpdesk ticket with category **"Network & VPN"** and priority **"High"**.

---

## Section 2: Password Policy & Identity Security

### 2.1 Password Requirements
- Minimum length: **14 characters**.
- Must contain at least one uppercase letter (A-Z), one lowercase letter (a-z), one numerical digit (0-9), and at least one approved special character (`!@#$%^&*()_+-=`).
- Must not contain dictionary words, predictable sequences (e.g., `Password123!`), or the user's name/email handle.
- Expiration: Passwords must be rotated every **90 days**.
- History: The last **5 passwords** cannot be reused.

### 2.2 Account Lockout & Reset Procedures
- Accounts are automatically locked out after **5 consecutive failed authentication attempts** across any corporate service.
- Standard lockout duration is **30 minutes**, after which the account unlocks automatically.
- **Immediate Self-Service Password Reset:** Visit `https://id.goaified.internal/reset` and verify identity using SMS OTP + Authenticator push.
- If self-service verification is unavailable, submit an urgent IT ticket or contact the Helpdesk Slack channel (`#it-helpdesk`) to initiate identity verification via manager video confirmation.

---

## Section 3: Hardware Provisioning, Maintenance & Incident Reporting

### 3.1 Device Allocation & Maintenance
- Engineering and product team members are provisioned standard enterprise laptops (Apple MacBook Pro M3 or Lenovo ThinkPad X1 Carbon).
- Full Disk Encryption (FileVault on macOS, BitLocker with TPM on Windows) must remain active at all times.
- Operating system security patches must be installed within 7 calendar days of release.

### 3.2 Hardware Malfunctions (Screens, Keyboards, Battery)
- If an employee encounters hardware degradation—such as laptop screen flickering, display blanking, continuous fan noise with thermal throttling, or battery swelling:
  1. Immediately save open work and shut down the machine if battery swelling or overheating is observed.
  2. Capture a photo or short video clip documenting the screen flickering or defect.
  3. Raise an IT ticket via the IT Helpdesk Agent with:
     - Issue Type: `Hardware Defect / Screen Flickering`
     - Asset Serial Number (found on the underside of the laptop or via `system_profiler SPHardwareDataType`)
     - Priority: `High` or `Critical`
  4. For remote employees, IT Logistics will dispatch an express courier replacement loaner laptop within **24 to 48 hours**.

---

## Section 4: Software Approvals & IT Helpdesk Service Levels (SLAs)

### 4.1 Permitted Software
- Standard development tools (VS Code, JetBrains IDEs, Git, Docker, Python, Node.js, Postman, Google Workspace, Slack) are pre-whitelisted.
- Third-party generative AI desktop assistants or browser extensions that transmit proprietary source code must undergo Security Review by the InfoSec team.

### 4.2 Support Ticket Priority & SLA Matrix
All requests submitted to the IT Helpdesk are triaged according to the following Service Level Agreement (SLA):
| Priority | Criteria & Examples | Initial Response SLA | Target Resolution SLA |
| :--- | :--- | :--- | :--- |
| **Critical (P1)** | Complete work stoppage, company-wide VPN outage, suspected security breach, stolen laptop | 1 Hour | 4 Hours |
| **High (P2)** | Hardware failure (screen flickering, dead battery), user VPN blockage, account lockout | 4 Hours | 24 Hours |
| **Medium (P3)** | Software license allocation, local developer environment errors, peripheral requests | 12 Hours | 48 Hours |
| **Low (P4)** | General IT queries, accessory questions, non-blocking configuration requests | 24 Hours | 72 Hours |
