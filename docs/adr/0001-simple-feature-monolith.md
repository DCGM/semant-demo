# ADR 0001 - Feature-oriented monolith with optional interfaces

Status: direction agreed in discussion; documentation adoption pending.
Date: 2026-10-07.

## Context

The team needs parallel human/agent development, but does not need a large architecture
framework. The initial proposal included too many apparently mandatory files and was
ambiguous about where a concrete repository belongs.

## Decision

Use feature folders with thin routes, service functions, schemas, and access functions
where needed. Concrete repositories live under infrastructure adapters. Do not have a
second concrete `features/<feature>/repository.py` alongside the Weaviate implementation.
Classes are optional for shared dependency injection. A service can accept dependencies
as ordinary function parameters.

A port is a typed capability interface, normally a Python Protocol. Introduce it where
it supports a useful fake, isolates an external dependency, or provides multiple
implementations. Multiple production implementations are not a prerequisite. Do not
require a port for every helper. Do not require unsupported CRUD methods to exist.

Without a port, importing an adapter class for typing is allowed initially. This has
source coupling; it must not be described as strict clean-architecture dependency
inversion. The runtime API must still expose neutral data rather than SDK handles.
When vendor imports or testing friction leak into services, add the narrow interface.

Other features call documented service/access functions directly. No `public.py` is
needed yet. No cycles, raw cross-feature adapter access, generic service locator, or
central 'everything' service. Shared UI composition belongs in the app/workspace shell.

## Alternatives and consequences

Full hexagonal layering was rejected as the default ceremony; putting all business
logic in routes/adapters was rejected because ownership and testing become unclear.
The selected approach accepts a little concrete type coupling in exchange for simplicity.
Boundary checks should enforce actual SDK isolation and dependency cycles, not ban every
adapter annotation while ports remain optional.
