---
type: Concept
title: DGX Dashboard
description: The NVIDIA dashboard service on the DGX Spark. It was observed bound to `127.0.0.1:11000` on the device and should be reached from the control host through an SSH tunnel unless the
resource: repo://hermes-workspace/knowledge/concepts/dgx-dashboard.md
tags: [hermes, concept]
timestamp: 2026-06-27T00:00:00+09:00
source_path: CONTEXT.md
---

# DGX Dashboard

The NVIDIA dashboard service on the DGX Spark. It was observed bound to `127.0.0.1:11000` on the device and should be reached from the control host through an SSH tunnel unless the user explicitly asks for external binding.
_Avoid_: exposing dashboard externally by default, confusing with Hermes dashboard
