# Design decisions

## Overview

This document is the entry point to the service design, linking the documents
that describe its assumptions, architecture, API, security, storage, and observability.

Based on [requirements](../requirements.md) and [technology stack](../tech_stack.md).
Each document identifies confirmed decisions, proposed details, or provisional assumptions.

## Documents

| Document | Purpose |
| --- | --- |
| [Assumptions](assumptions.md) | Capacity, integration, and deployment assumptions requiring validation. |
| [Architecture](architecture.md) | Module responsibilities, request flow, transactions, concurrency, and execution model. |
| [API](api.md) | Payment endpoint, validation limits, response formats, and HTTP status mapping. |
| [Authentication and authorization](authentication_and_authorization.md) | JWT verification, payer authorization, and authentication configuration. |
| [Data model](data-model.md) | Platform storage, money representation, audit schema, and database permissions. |
| [Observability](observability.md) | Logs, metrics, health endpoints, operational access protection, and infrastructure responsibilities. |
