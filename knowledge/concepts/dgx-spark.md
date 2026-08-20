---
type: Concept
title: DGX Spark
description: The user's NVIDIA DGX Spark / GIGABYTE AI TOP ATOM Linux workstation reachable on the LAN for SSH, DGX Dashboard, and remote desktop work. It is not automatically a Hermes host. Cu
resource: repo://hermes-workspace/knowledge/concepts/dgx-spark.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# DGX Spark

The user's NVIDIA DGX Spark / GIGABYTE AI TOP ATOM Linux workstation reachable on the LAN for SSH, DGX Dashboard, and remote desktop work. It is not automatically a Hermes host. Current access path is `bobeenlee@100.103.30.62` over Tailscale; the LAN address `172.30.1.87` and `aitopatom-36a9.local` are fallbacks observed during setup.
_Avoid_: assuming DGX operations use the default Hermes target tooling, treating the onboarding web UI as a permanent service

Access path, doc map, and the account boundary: [DGX Spark Remote Access](../runbooks/dgx-spark-remote-access.md).
