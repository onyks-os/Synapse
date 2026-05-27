# Mathematical and Statistical Formalisms of the Synapse Project

This document describes the mathematical and statistical formalisms that form the core of the Synapse system. The goal is to provide a clear understanding of the underlying logic for anyone, regardless of prior knowledge of the software.

## 1. Geospatial Indexing with H3

The Synapse system organizes network nodes (sensors) on a geographical basis. To do this, it uses the **H3 (Hexagonal Hierarchical Geospatial Indexing)** system, an open-source library created by Uber.

### 1.1. Basic Concept

H3 divides the Earth's surface into a grid of hexagons. Each hexagon, called a "cell," has a unique identifier (`h3_cell`). This grid is hierarchical: each hexagon can be subdivided into smaller hexagons at a higher resolution.

### 1.2. Purpose in the Project

In Synapse, each sensor sends its geographical coordinates (latitude and longitude). The system converts these coordinates into the corresponding H3 cell identifier at a predefined resolution.

The objective is to **group nodes by physical proximity**. All nodes located within the same H3 cell are considered "neighbors" or "peers." This grouping is the foundation for the corroboration logic described below.

## 2. Node State Management

Each node in the registry (`NodeRegistry`) can be in one of the following three states:

- **`ALIVE`**: The node is active and sending data regularly. Its data is currently considered reliable.
- **`FAULTY`**: The node is active, but the data it is sending has been identified as anomalous compared to its peers. The node does not participate in the calculation of corroboration metrics while in this state.
- **`DEAD`**: The node has not sent data for a period longer than the timeout threshold (`death_timeout`). It is considered inactive.

### 2.1. State Transitions

- **From any state to `ALIVE`**: When a node sends a new "ping" (a data packet), its status is immediately set to `ALIVE`, and its `last_seen` timestamp is updated. This allows a `FAULTY` or `DEAD` node to recover immediately if it comes back online and sends data.
- **From `ALIVE` to `FAULTY`**: If an `ALIVE` node fails the spatial corroboration check (Section 3), its status is changed to `FAULTY`.
- **From `ALIVE` or `FAULTY` to `DEAD`**: A periodic process (`check_timeouts`) checks all nodes. If the time elapsed since the last ping (`now - last_seen`) exceeds the `death_timeout` threshold, the node is marked as `DEAD`.

### 2.2. Garbage Collection

`DEAD` nodes are not removed immediately. They are kept for an additional period (`eviction_ttl`). A cleanup process (`evict_dead_nodes`) permanently deletes nodes from the registry that have been `DEAD` for more than `death_timeout + eviction_ttl`, freeing up resources.

## 3. Spatial Corroboration (Outlier Detection)

Spatial corroboration **flags active sensors that disagree with their geographic neighbours** (same H3 cell). It does **not** replace silence detection: that remains the `DEAD` timeout path.

All shipped methods share the same **leave-one-out** shell: for node *n*, peers are the other **`ALIVE`** readings in the cell. The **decision rule** is pluggable (`CORROBORATION_METHOD`).

### 3.1. Leave-one-out shell

For each H3 cell:

1. **Quorum:** Run only if there are at least **`min_peers`** `ALIVE` nodes in the cell.
2. **Peers:** For each candidate *n*, peer values = all other `ALIVE` `last_value` readings in that cell.
3. **Skip** if there are fewer than two peer values, or if the chosen statistic cannot be computed (e.g. zero spread).

### 3.2. Classic Z-score (method `zscore`)

On leave-one-out peer set *P*:

- μ = mean(*P*), σ = sample standard deviation of *P* (requires σ > 0).
- **Z** = \|value\_n − μ\| / σ.
- If **Z** > threshold → `FAULTY`.

**Caveat:** μ and σ are **not robust**: a few bad peers in *P* can skew the baseline and hide or exaggerate outliers. Prefer **`mad`** when peer count per cell is small.

### 3.3. Modified Z-score with MAD (method `mad`, default)

Still on leave-one-out *P*:

- *m* = median(*P*).
- **MAD** = median of \|p − m\| for p ∈ *P*.
- If MAD = 0, skip (no meaningful spread).
- **Modified Z** = 0.6745 × \|value\_n − m\| / MAD (scaling matches σ under normality for comparability).
- If modified Z > threshold → `FAULTY`.

This is **robust** to a minority of bad neighbours in *P*, which is common in edge meshes with small cells.

### 3.4. Hybrid AND (method `both`)

**FAULTY** only if **both** §3.2 and §3.3 would flag the same reading at the same threshold. If either side cannot compute, that side is treated as “not an outlier”, so **precision** is high and **recall** lower.

### 3.5. Practical example (classic Z on clean peers)

H3 cell with 5 temperature sensors: `min_peers = 4`, threshold = 2.0.  
Values: `s1=20.1`, `s2=20.0`, `s3=20.2`, `s4=19.9`, `s5=35.0`.

For `s5`, peers are `{20.1, 20.0, 20.2, 19.9}` → μ ≈ 20.05, σ ≈ 0.129 → Z ≈ 115.8 → `FAULTY`.

With **`mad`**, the same example also flags `s5` with a very large modified Z because the peer median and MAD stay tight while `s5` is far away.
