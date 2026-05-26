# API Reference

This document describes the HTTP API exposed by the **Monitor** service. The API is read-only and provides real-time data on the status of the sensor network.

The base URL of the API depends on how the service is run. When using Docker Compose, the default port is `8080`.

- **Base URL**: `http://localhost:8080`

## Data Objects

### `NodeEntry`

Represents a single sensor node in the registry.

| Field | Type | Description |
| --- | --- | --- |
| `node_id` | `string` | The unique identifier of the node. |
| `type` | `string` | The type of sensor (e.g., "mock", "chaos"). |
| `status` | `string` | The current status of the node. Can be `ALIVE`, `FAULTY`, or `DEAD`. |
| `last_seen` | `float` | Unix timestamp (seconds) of the last message received from the node. |
| `h3_cell` | `string` | The index of the H3 cell to which the node belongs. |
| `lat` | `float` | The last known latitude of the node. |
| `lon` | `float` | The last known longitude of the node. |
| `last_value` | `float` | The last sensor value sent by the node. |

---

## Endpoints

### GET `/api/v1/nodes`

Returns a list of all nodes registered in the system, regardless of their status.

- **Method**: `GET`
- **Path**: `/api/v1/nodes`
- **Success Response**: `200 OK`
- **Response Body**: An array of `NodeEntry` objects.

Legacy alias: `/api/nodes` remains available as a backward-compatible wrapper.

**Example Response (`200 OK`)**

```json
[
  {
    "h3_cell": "871fb4670ffffff",
    "last_seen": 1709894982.5,
    "last_value": 20.1,
    "lat": 45.4,
    "lon": 9.1,
    "node_id": "sensor_1",
    "status": "ALIVE",
    "type": "mock"
  },
  {
    "h3_cell": "871fb467effffff",
    "last_seen": 1709894975.1,
    "last_value": 999.0,
    "lat": 45.5,
    "lon": 9.2,
    "node_id": "sensor_2",
    "status": "FAULTY",
    "type": "mock"
  }
]
```

---

### GET `/api/v1/cells`

Returns a summary of the network state, grouped by H3 cell. This is the main endpoint used by the dashboard for visualization.

- **Method**: `GET`
- **Path**: `/api/v1/cells`
- **Success Response**: `200 OK`
- **Response Body**: An object (dictionary) where each key is an `h3_cell` ID. The value associated with each key is a summary object for that cell.

Legacy alias: `/api/cells` remains available as a backward-compatible wrapper.

#### Cell Summary Object Format

| Field | Type | Description |
| --- | --- | --- |
| `alive` | `integer` | The number of nodes with status `ALIVE` in the cell. |
| `faulty` | `integer` | The number of nodes with status `FAULTY` in the cell. |
| `dead` | `integer` | The number of nodes with status `DEAD` in the cell. |
| `nodes` | `array` | A list of the `node_id`s of all nodes present in the cell. |
| `lat` | `float` | The approximate latitude of the cell's centroid. |
| `lon` | `float` | The approximate longitude of the cell's centroid. |

**Example Response (`200 OK`)**

```json
{
  "871fb4670ffffff": {
    "alive": 5,
    "dead": 1,
    "faulty": 1,
    "lat": 45.46,
    "lon": 9.19,
    "nodes": [
      "sensor_1",
      "sensor_3",
      "sensor_4",
      "sensor_dead",
      "sensor_faulty",
      "sensor_5",
      "sensor_6"
    ]
  },
  "871fb467effffff": {
    "alive": 12,
    "dead": 0,
    "faulty": 0,
    "lat": 45.5,
    "lon": 9.2,
    "nodes": [
      "sensor_10",
      "sensor_11",
      "..."
    ]
  }
}
```

---

## Operators' Endpoints

### GET `/live`

Returns `{"status":"ok"}` for liveness checks.

### GET `/ready`

Returns `{"status":"ok", "nodes_total": ..., "nodes_alive": ...}` for readiness checks.

### GET `/metrics`

Prometheus-style metrics (`text/plain`) including:

- `Synapse_messages_total`
- `Synapse_invalid_payload_total`
- `Synapse_rate_limited_total`
- `Synapse_corroboration_faulty_total`
- node state gauges (`Synapse_nodes_alive`, `Synapse_nodes_faulty`, `Synapse_nodes_dead`)

Authentication: `/metrics` requires the dashboard API key when configured.
