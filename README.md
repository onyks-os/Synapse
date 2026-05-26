<div align="center">
  <h1>Synapse</h1>
  <p><b>Brokerless IoT ingestion engine with spatial anomaly detection</b></p>

  <a href="https://github.com/onyks-os/Synapse/actions/workflows/ci.yml">
  </a>
  <a href="https://opensource.org/licenses/MIT">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT">
  </a>
</div>

Synapse is an experimental project exploring alternative Edge IoT topologies. It substitutes centralized message brokers like MQTT or Kafka with a true decentralized Symmetric P2P Mesh topology over ZeroMQ. Integrity checks and anomaly detection are processed locally on each node using H3 spatial grids.

![Synapse Dashboard Demo](https://raw.githubusercontent.com/onyks-os/Synapse/main/assets/gif/demo.gif)
*(Above: Synapse dashboard. Hexagons turn yellow or red when sensors report anomalies compared to their local peers).*

## Quickstart

You can run a local simulation using Docker:

```bash
git clone https://github.com/onyks-os/Synapse.git
cd Synapse
docker compose -f docker/docker-compose.yml up --build
```

Open http://localhost:8081 in a browser to view the local dashboard of `node-1`. You can explore the decentralized network via the "Connected Peers" sidebar.

## Chaos Engineering Built-in

Synapse includes a built-in Chaos Monkey to test the spatial corroboration and node eviction mechanisms under stress. 

![Chaos Monkey logs](https://raw.githubusercontent.com/onyks-os/Synapse/main/assets/img/chaos.png)
*(Above: Injecting malicious payloads via the `chaos_monkey.py` CLI triggers the local MAD corroboration, immediately flagging the rogue nodes as `FAULTY`).*

## Architecture Comparison

| Feature           | Traditional IoT                       | Synapse               |
| :---------------- | :------------------------------------ | :-------------------- |
| Topology          | Hub and Spoke (Cloud Broker)          | Symmetric P2P Mesh    |
| Anomaly Detection | Centralized                           | Decentralized (H3/MAD)|
| Resilience        | Single point of failure at the Broker | Decentralized         |
| Footprint         | High (JVM or heavy brokers)           | Low                   |

### Core Technologies
* **Networking:** ZeroMQ for Pub/Sub messaging.
* **Security:** CurveZMQ (optional) for curve25519-based encryption.
* **Spatial Engine:** Uber H3 Hexagonal Hierarchical Spatial Index.
* **Statistics:** Median Absolute Deviation (MAD) for outlier detection.

## Development

To set up the local development environment:

1. Install Python 3.11+ and venv.
2. Set up the environment:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    pip install .[dev]
    ```
3. Run the test suite:
    ```bash
    pytest
    ```

Further details are available in the Contributing Guidelines, Architecture Document, and ADRs.

## License
Distributed under the MIT [License](LICENSE).