# ADR 001: Adoption of CurveZMQ for Data Channel Security

**Status**: Accepted

**Context**:
The communication channel between sensors and the monitor, based on ZMQ, currently transmits data in plaintext. This poses a significant security risk, as a malicious actor on the same network could intercept (sniff) or alter (spoof) the data sent by the sensors. Since the system is intended for a production environment, we cannot rely solely on physical or virtual network isolation (VPN/VLAN) as the only security measure.

**Decision**:
We will adopt CurveZMQ to secure the ZMQ data channel. CurveZMQ provides a robust end-to-end authentication and encryption mechanism based on elliptic-curve cryptography (Curve25519).

Each sensor and monitor will have a long-term key pair (public and private).
- The monitor will only accept connections from sensors whose public key is in an authorized whitelist.
- Communication between an authorized sensor and the monitor will be fully encrypted.

**Consequences**:

*   **Positive**:
    *   **Confidentiality**: Exchanged data is encrypted and cannot be read by third parties.
    *   **Authenticity and Integrity**: Only known and authorized sensors can communicate with the monitor, and their messages cannot be altered in transit.
    *   **Security by Design**: The system becomes inherently more secure, reducing reliance on network-level security.

*   **Negative**:
    *   **Management Complexity**: It introduces the need to securely generate, distribute, and manage cryptographic keys for every node in the system (sensors and monitors). A key provisioning and revocation process will need to be defined.
    *   **Performance Overhead**: Encryption introduces a slight computational and latency overhead. However, the efficiency of CurveZMQ makes this impact negligible for our stated scale constraints (1000 sensors @ 0.1 Hz).
