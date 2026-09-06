import socket
import ipaddress
import urllib.parse
from typing import Tuple, List, Optional

# Standard cloud metadata and dangerous hostnames
BLOCKED_HOSTNAMES = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata.internal",
    "instance-data",
}

CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")

class SSRFSecurityException(Exception):
    """Raised when an untrusted live URL targets internal or restricted networks (SSRF prevention)."""
    pass

def assert_safe_url(url: str, allow_localhost_for_testing: bool = False) -> str:
    """
    Validates URL safety and raises SSRFSecurityException if unsafe.
    Returns normalized URL on success.
    """
    is_safe, reason = validate_safe_url(url, allow_localhost_for_testing=allow_localhost_for_testing)
    if not is_safe:
        raise SSRFSecurityException(f"SSRF Security Violation: {reason}")
    return url

def _parse_encoded_numeric_ip(hostname: str) -> Optional[ipaddress.IPv4Address]:
    """Detect and decode unusual IP representations: decimal integers, hex, and octal."""
    clean = hostname.strip()
    # Decimal integer IP (e.g., 2130706433 -> 127.0.0.1)
    if clean.isdigit():
        try:
            val = int(clean)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except Exception:
            pass

    # Hexadecimal IP (e.g., 0x7f000001 -> 127.0.0.1)
    if clean.lower().startswith("0x"):
        try:
            val = int(clean, 16)
            if 0 <= val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(val)
        except Exception:
            pass

    # Octal or mixed dot notation (e.g., 0177.0.0.1 or 0177.1)
    parts = clean.split(".")
    if len(parts) in (2, 3, 4):
        try:
            int_parts = []
            for p in parts:
                if p.startswith("0x") or p.startswith("0X"):
                    int_parts.append(int(p, 16))
                elif p.startswith("0") and len(p) > 1:
                    int_parts.append(int(p, 8))
                else:
                    int_parts.append(int(p, 10))
            # If standard 4 octets
            if len(int_parts) == 4 and all(0 <= x <= 255 for x in int_parts):
                ip_str = ".".join(str(x) for x in int_parts)
                return ipaddress.IPv4Address(ip_str)
        except Exception:
            pass

    return None

def validate_safe_url(url: str, allow_localhost_for_testing: bool = False) -> Tuple[bool, str]:
    """
    Validates that a URL is safe for browser evaluation and prevents SSRF attacks.
    Checks:
    1. Scheme is strictly 'http' or 'https'.
    2. Hostname is not in known internal/metadata blacklists.
    3. Hostname does not decode to unusual loopback or private encodings (hex/octal/int).
    4. Hostname resolves strictly to public routable IP addresses.
    5. Blocks loopback (127.0.0.0/8, ::1), private (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16),
       link-local / cloud metadata (169.254.0.0/16), CGNAT (100.64.0.0/10), multicast, and broadcast IPs.
    """
    if not url or not isinstance(url, str):
        return False, "URL is empty or invalid"

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as e:
        return False, f"Malformed URL: {str(e)}"

    # 1. Scheme check
    if parsed.scheme.lower() not in ("http", "https"):
        return False, f"Disallowed URL scheme '{parsed.scheme}'. Only 'http' and 'https' are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must contain a valid hostname."

    hostname_lower = hostname.lower()

    # 2. Testing bypass check (enabled during controlled unit tests or via env)
    import os
    testing_allowed = allow_localhost_for_testing or (os.getenv("EVALFORGE_ALLOW_LOCAL_TEST_SITES", "").lower() in ("true", "1"))
    if testing_allowed and (hostname_lower in ("localhost", "127.0.0.1", "::1", "0.0.0.0")):
        return True, "Allowed for local testing"

    # 3. Known dangerous hostnames
    if hostname_lower in BLOCKED_HOSTNAMES:
        return False, f"Access to blocked hostname '{hostname}' is prohibited (SSRF protection)."

    # 4. Check for unusual numeric/hex/octal IP representations
    decoded_ip = _parse_encoded_numeric_ip(hostname_lower)
    if decoded_ip:
        if decoded_ip.is_loopback:
            return False, f"Decoded IP '{decoded_ip}' is a loopback address (SSRF protection)."
        if decoded_ip.is_link_local:
            return False, f"Decoded IP '{decoded_ip}' is a link-local/cloud metadata address (SSRF protection)."
        if decoded_ip.is_private or decoded_ip in CARRIER_GRADE_NAT:
            return False, f"Decoded IP '{decoded_ip}' is a private network address (SSRF protection)."
        if decoded_ip.is_multicast or decoded_ip.is_unspecified or decoded_ip.is_reserved:
            return False, f"Decoded IP '{decoded_ip}' is not a routable public address."

    # 5. Check if hostname itself is directly a standard numeric IP string
    try:
        raw_ip = ipaddress.ip_address(hostname_lower)
        # Check IPv4 mapped in IPv6 (e.g., ::ffff:127.0.0.1)
        if isinstance(raw_ip, ipaddress.IPv6Address) and raw_ip.ipv4_mapped:
            raw_ip = raw_ip.ipv4_mapped

        if raw_ip.is_loopback:
            return False, f"Direct IP '{hostname}' is a loopback address (SSRF protection)."
        if raw_ip.is_link_local:
            return False, f"Direct IP '{hostname}' is a link-local/cloud metadata address (SSRF protection)."
        if raw_ip.is_private or (isinstance(raw_ip, ipaddress.IPv4Address) and raw_ip in CARRIER_GRADE_NAT):
            return False, f"Direct IP '{hostname}' is a private network address (SSRF protection)."
        if raw_ip.is_multicast or raw_ip.is_unspecified or raw_ip.is_reserved:
            return False, f"Direct IP '{hostname}' is not a routable public address."
    except ValueError:
        pass  # Hostname is a domain name, proceed to DNS resolution

    # 6. DNS Resolution & IP Range Validation
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as ge:
        return False, f"DNS resolution failed for hostname '{hostname}': {ge.strerror}"
    except Exception as ex:
        return False, f"DNS resolution error for hostname '{hostname}': {str(ex)}"

    if not addr_info:
        return False, f"No IP addresses resolved for hostname '{hostname}'"

    for entry in addr_info:
        ip_str = entry[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)

            if isinstance(ip_obj, ipaddress.IPv6Address) and ip_obj.ipv4_mapped:
                ip_obj = ip_obj.ipv4_mapped

            if ip_obj.is_loopback:
                return False, f"Resolved IP '{ip_str}' is a loopback address (SSRF protection)."

            if ip_obj.is_link_local:
                return False, f"Resolved IP '{ip_str}' is a link-local/cloud metadata address (SSRF protection)."

            if ip_obj.is_private or (isinstance(ip_obj, ipaddress.IPv4Address) and ip_obj in CARRIER_GRADE_NAT):
                return False, f"Resolved IP '{ip_str}' is a private network address (SSRF protection)."

            if ip_obj.is_multicast:
                return False, f"Resolved IP '{ip_str}' is a multicast address."

            if ip_obj.is_unspecified:
                return False, f"Resolved IP '{ip_str}' is an unspecified address."

            if ip_obj.is_reserved:
                return False, f"Resolved IP '{ip_str}' is a reserved address."

        except ValueError:
            return False, f"Invalid IP address resolved: '{ip_str}'"

    return True, "URL is safe"
