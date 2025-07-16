# Kiro Configuration for QMTL

This directory contains Kiro-specific configuration files and steering rules for the QMTL project.

## Directory Structure

```
.kiro/
├── README.md           # This file
├── settings/           # Kiro settings and configurations
│   └── mcp.json       # Model Context Protocol server configurations
├── steering/          # Context steering rules for AI assistance
│   ├── tech.md        # Technology stack and tooling guidelines
│   ├── structure.md   # Project structure and organization
│   └── product.md     # Product overview and core concepts
└── specs/             # Feature specifications and implementation plans
    └── dag-strategy-execution/  # Current DAG execution system spec
        ├── requirements.md
        ├── design.md
        └── tasks.md
```

## Steering Rules

The steering rules provide context to Kiro about:

- **Technology Stack**: Preferred tools, dependencies, and development practices
- **Project Structure**: Code organization, naming conventions, and architectural patterns  
- **Product Overview**: Core concepts, components, and use cases

These rules help ensure consistent development practices and provide relevant context for AI-assisted development.

## MCP Configuration

The MCP (Model Context Protocol) configuration enables Kiro to:

- Access filesystem operations for code analysis and modification
- Interact with Git for version control operations
- Maintain context about the project structure and dependencies

## Usage

When working with Kiro on QMTL:

1. Reference specific files using `#File` or `#Folder` syntax
2. Use `#Codebase` for project-wide analysis after indexing
3. Leverage the steering rules for consistent development practices
4. Follow the spec-driven development workflow for complex features

## Development Workflow

For new features:
1. Create a spec in `.kiro/specs/` following the established pattern
2. Use the requirements → design → tasks workflow
3. Execute tasks incrementally with Kiro assistance
4. Maintain test coverage and documentation standards