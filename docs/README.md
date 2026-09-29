# PixelCast Documentation

This directory contains all project documentation.

## Documentation Files

### DOCUMENTATION_GUIDE.md

Complete guide for code documentation standards including:

- File header format
- Class and function docstring templates
- Parameter and return value documentation
- Best practices and examples

Use this as a reference when adding documentation to new code.

### CLAUDE_PROJECT_CONTEXT.md

Comprehensive project context including:

- System architecture overview
- Component descriptions
- Technical implementation details
- Configuration reference
- API documentation

This is the main technical reference document.

### CLAUDE_PROJECT_QUICKREF.md

Quick reference notes for common tasks and patterns.

### FEATURES.md

Feature list, roadmap, and development notes including:

- Implemented features
- Planned enhancements
- Known issues
- Future development ideas

### OS-UPDATES.md

Runbook for applying Debian and kernel updates to a device whose SD card is
protected by the read-only overlay filesystem, including:

- Why a plain `apt upgrade` fails (and why the failure is usually harmless)
- What is and is not persistent across a reboot
- Auditing the RAM overlay for unsaved config before rebooting
- Disabling the overlay, upgrading, installing the RT kernel, re-enabling
- Recovery if the device will not boot

Read this before touching `apt` on a PixelCast device.

## Additional Documentation

For specific topics, see:

- **Installation & Deployment**: `../deployment/README.md`
- **API Reference**: See CLAUDE_PROJECT_CONTEXT.md
- **User Guide**: Web interface is self-documenting
- **Hardware Setup**: See main README.md

## Contributing Documentation

When adding new features or making significant changes:

1. Update CLAUDE_PROJECT_CONTEXT.md with technical details
2. Add code documentation following DOCUMENTATION_GUIDE.md
3. Update FEATURES.md if adding new functionality
4. Update main README.md if user-facing changes

## Documentation Standards

All code should include:

- File headers with project name, version, author, description
- Class docstrings describing purpose and usage
- Function/method docstrings with parameters and return values
- Inline comments for complex logic

See DOCUMENTATION_GUIDE.md for templates and examples.
