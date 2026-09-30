# SFTP vs. FTPS: Two "Secure FTPs" That Break in Different Places

#### I ran both in Docker, added latency, closed a firewall and watched each one fail in its own way

**By Tihomir Manushev**

*Sep 30, 2026 · 6 min read*

---

A partner sends a one-line email: "Please deliver the nightly files over secure FTP." Half the teams that get that email stand up SFTP. The other half stand up FTPS. Both halves think they did what was asked, and one of them finds out otherwise at 2 a.m. when the first transfer fails.

The two protocols share three letters and almost nothing else. One is a subsystem of SSH. The other is FTP from the 1980s with TLS wrapped around it. They fail in different places: FTPS at the firewall, SFTP on long network paths.

I built both in Docker and measured them, with and without latency, and with a firewall in the way. Every number below comes from that lab.

---

### Two Protocols That Share a Name

**SFTP** is a binary request/response protocol that runs inside one SSH channel. It uses one TCP connection on port 22, SSH keys for authentication and a host key for server identity. It was never finished as an RFC. OpenSSH implements draft version 3, and every mainstream client speaks that version. Since OpenSSH 9.0, even `scp` uses SFTP under the hood.

**FTPS** is classic FTP secured by TLS (RFC 4217). It keeps FTP's two-channel design: a **control connection** for commands, plus a *new* TCP connection for every file transfer and every directory listing. Explicit FTPS starts in plain text on port 21 and upgrades with `AUTH TLS`. Implicit FTPS starts in TLS on port 990. Identity comes from X.509 certificates, the same kind of PKI your HTTPS already uses.

That split between channels explains every failure below.

---

### The Lab

The SFTP server is OpenSSH 9.7 on Alpine. The FTPS server is vsftpd 3.0.3 on Debian. The client is a Ryzen 5 3600 running OpenSSH 9.6, curl 8.5 and Python 3.12. The SFTP side is locked down the way a partner drop-box should be:

```bash
Subsystem sftp internal-sftp

Match User courier
    ChrootDirectory /srv/sftp/%u
    ForceCommand internal-sftp
    AllowTcpForwarding no
    X11Forwarding no
    PermitTTY no
```

`ForceCommand internal-sftp` means a partner's key opens a file drop and nothing else: no shell, no tunnels. `sshd -t` accepts this block. Leave these lines out and the account you created for file delivery can also open a shell and forward ports.

The FTPS side needs a few more decisions:

```bash
ssl_enable=YES
force_local_logins_ssl=YES
force_local_data_ssl=YES
pasv_min_port=30000
pasv_max_port=30009
pasv_address=127.0.0.1
```

The last three lines are the ones that cause trouble.

---

### FTPS Breaks at the Firewall

In passive mode, the FTPS server tells the client "connect to me on port 30007" *inside the encrypted control channel*. With plain FTP, NAT gateways and firewalls read that reply and open the port on the fly. With FTPS they can't read it. So you must pin a passive port range, publish every port in it, and set `pasv_address` to the server's public IP, because the server can't learn that address from behind NAT.

I started a second FTPS container that published only port 21, which is what most first attempts look like:

```bash
< 230 Login successful.
< 200 PROT now Private.
> EPSV
< 229 Entering Extended Passive Mode (|||30007|)
* Connecting to 127.0.0.1 (127.0.0.1) port 30007
* Failed EPSV attempt. Disabling EPSV
> PASV
< 227 Entering Passive Mode (127,0,0,1,117,48).
curl: (7) Failed to connect to 127.0.0.1 port 2123 after 46 ms: Couldn't connect to server
```

Login works and the listing fails. Because the first step succeeds, someone always suspects the credentials first. Python's `ftplib` showed the same thing: `230 Login successful`, then `ConnectionRefusedError`. SFTP has no equivalent failure, because it only ever uses the one port.

---

### The Session-Reuse Trap

With the ports open, Python's standard library still failed against a default vsftpd:

```bash
error_perm 522 SSL connection failed: session reuse required
```

vsftpd defaults to `require_ssl_reuse=YES`, so it rejects any data connection that doesn't resume the control channel's TLS session. This stops an attacker from hijacking the data connection. curl resumes the session. `ftplib.FTP_TLS` does not. The fix is to pass the session in explicitly:

```python
import ftplib
import socket


class SessionReusingFTPS(ftplib.FTP_TLS):
    """FTP_TLS that resumes the control channel's TLS session on data channels."""

    def ntransfercmd(self, cmd: str, rest: int | None = None) -> tuple[socket.socket, int | None]:
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(
                conn, server_hostname=self.host, session=self.sock.session
            )
        return conn, size
```

The override skips `FTP_TLS.ntransfercmd`, opens the plain data socket and wraps it in TLS with `session=self.sock.session`. This worked over both TLS 1.2 and TLS 1.3. Setting `require_ssl_reuse=NO` on the server also "works", but it removes the protection. One more oddity: vsftpd running as PID 1 in a container died with a segfault after its first session until I added `docker run --init`.

---

### SFTP Breaks on Long Paths

Next I uploaded a 512 MB file with `tc netem` adding latency on the server side:

```bash
added RTT   OpenSSH sftp      curl FTPS
0 ms        ~230 MB/s         ~260 MB/s
25 ms        68 MB/s          122 MB/s
50 ms        35 MB/s           66 MB/s
```

With no added latency, the two are nearly equal. Once latency goes up, SFTP falls behind and its throughput halves each time the RTT doubles. That pattern means a fixed window is the limit. OpenSSH's channel window is set at compile time to `64 * 32 KiB`, which is 2 MiB. At 25 ms that allows at most about 84 MB/s. Raising `sftp -R 256` (more outstanding requests) changed nothing, because the SSH channel window was the limit, not SFTP's request depth. FTPS is also window-bound, but by the kernel's TCP send buffer, which is 4 MiB here and adjustable with a sysctl. Paramiko did worse than the OpenSSH CLI at 25 ms: 43 MB/s.

To move bulk data across continents, run parallel SFTP streams, use a patched SSH (HPN-SSH exists for exactly this problem), or accept FTPS's firewall work.

---

### Many Small Files Flip It Back

Big files are one workload. The nightly batch of 200 files of 16 KB each is another. I ran both Python clients at 25 ms of added RTT:

```bash
SFTP   200 files    15.64 s   1 TCP connection
FTPS   200 files    51.08 s   201 TCP connections
```

SFTP pays a few round trips per file (open, write, close) on the connection it already has. FTPS pays for a passive-mode handshake, a new TCP connection, a TLS resumption and a teardown for every file: about 255 ms per file against SFTP's 78 ms. The firewall sees 201 connections where SFTP makes one.

---

### How to Choose

The trust model usually matters more than speed. SFTP means one SSH key per partner, host-key fingerprints exchanged once, and one port on the allowlist. FTPS means certificates. That fits well if you already run a PKI or need client certificates for auditors, and it's a burden if you don't. Some banks, mainframes and older EDI partners only offer FTPS. In that case the choice is made for you, and the firewall work above is part of the job.

---

### Conclusion

Choose SFTP by default. It uses one port, needs no NAT workarounds, handles many small files well and gives you a hardened chroot in six lines of `sshd_config`. What it costs is throughput on high-latency paths, where the 2 MiB SSH window caps a single stream at roughly half of what FTPS reaches. Choose FTPS when a partner requires it or your identity model is already X.509. Budget for a pinned passive range, a correct `pasv_address`, and clients that resume TLS sessions. And when the email says "secure FTP", ask which one before you build anything.
