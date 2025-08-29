# Realm Terminology Evaluation

This note reviews replacing the term **World** with **Realm** across QMTL.

## Domain Fit

"World" currently denotes a top‑level portfolio boundary that groups related strategies and policies.  "Realm" carries a similar sense of an autonomous domain while sounding less overloaded with geographic or market connotations.  The term reads naturally in English and Korean ("렐름") and avoids confusion with external "world" naming found in third‑party tools.

## Impact Scope

Renaming touches documentation, configuration paths, APIs, and tooling.  A rough search shows over one hundred references to "World" in architecture, operations, and reference docs.  Key surfaces include `docs/world/*.md`, `docs/architecture/worldservice.md`, the World API reference, and the activation runbook.  Code samples and configuration snippets also assume `config/worlds/<id>.yml` and `qmtl world` CLI verbs.

## Prototype: config/realms

- Accept policy files under `config/realms/<realm_id>.yml` alongside the existing `config/worlds/` directory.
- Gateways and runners first look for a matching realm file; if absent they fall back to a world file for backward compatibility.
- Documentation examples updated to prefer the new path while noting legacy support.

## Prototype: `qmtl realm` CLI

- Mirror existing subcommands: `qmtl realm create`, `qmtl realm list`, `qmtl realm policy add`, etc.
- During transition, commands issue deprecation warnings when `qmtl world` is used and forward the call to the new implementation.
- Help text and `--help` output describe both terms until the migration is complete.

## Outstanding Questions

- Should database tables and event types (e.g., `WorldUpdated`) be renamed or aliased?
- How long should dual terminology be supported before removing `world`?
- Does any integration rely on the literal `world` term that would break even with aliases?

Further discussion is required before performing a full project‑wide rename.
