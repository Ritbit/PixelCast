# PixelCast Documentation Guide

## File Header Format

Every Python and shell script file should have this header:

```python
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                           ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        path/to/file.py                                                 ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: Brief description of file purpose and main functionality.       ║
║              Can span multiple lines if needed.                              ║
║                                                                              ║
║ Important:   Key implementation notes, warnings, or requirements.            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
```

## Class Documentation

```python
class MyClass:
    """
    Brief description of class purpose.
    Additional details about behavior and usage.
    """
    
    def __init__(self, param1: type, param2: type):
        """
        Initialize the class.
        
        Args:
            param1 (type): Description of param1
            param2 (type): Description of param2
        """
        pass
```

## Function Documentation

```python
def my_function(arg1: str, arg2: int = 10) -> dict:
    """
    Brief description of what the function does.
    Additional details if needed.
    
    Args:
        arg1 (str): Description of arg1
        arg2 (int, optional): Description of arg2. Defaults to 10.
    
    Returns:
        dict: Description of return value with key structure if applicable
    
    Raises:
        ValueError: When and why this exception is raised
    """
    pass
```

## Method Documentation

```python
def process_data(self, data: list) -> bool:
    """
    Process the input data and update internal state.
    
    Args:
        data (list): List of data items to process
    
    Returns:
        bool: True if processing succeeded, False otherwise
    """
    pass
```

## Simple Function Documentation

For very simple functions, a one-line docstring is acceptable:

```python
def is_ready(self) -> bool:
    """Check if system is ready."""
    return self._ready
```

## Examples from PixelCast

### Complete File Example (sysinfo.py)

```python
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║ PixelCast - Professional LED Matrix Signage System                          ║
╠══════════════════════════════════════════════════════════════════════════════╣
║ File:        signage/sysinfo.py                                              ║
║ Version:     1.0.0                                                           ║
║ Author:      B. van Ritbergen <bas@ritbit.com>                               ║
║ Description: System information collector - gathers CPU, memory, temperature,║
║              disk usage, and uptime statistics for monitoring dashboard.     ║
║                                                                              ║
║ Important:   Returns plain dicts suitable for JSON serialization. Reads     ║
║              from /proc filesystem and system commands.                      ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

def cpu_percent() -> float:
    """
    Read CPU usage percentage from /proc/stat.
    Takes two samples 100ms apart for accurate measurement.
    
    Returns:
        float: CPU usage percentage (0-100)
    """
    # implementation...
```

### Complete Class Example (AlertManager)

```python
class AlertManager:
    """
    Manages high-priority alert overlays composited on top of playlist content.
    Uses TextRenderer for rendering with full text feature support.
    """
    
    def __init__(self, engine):
        """
        Initialize alert manager.
        
        Args:
            engine (MatrixEngine): Reference to matrix engine for display dimensions
        """
        # implementation...
    
    def show(self, cfg: dict):
        """
        Display a multi-line alert overlay.
        
        Args:
            cfg (dict): Alert configuration matching TextRenderer format:
                - lines (list): Line dicts with text, color, font, font_size, align, scroll, etc.
                - bg_color (list): RGB background color [R,G,B]
                - bg_image (str): Path to background image
                - bg_dim (int): Background dim percentage 0-100
                - bg_mode (str): 'color' or 'image'
                - v_center (bool): Vertically center text
                - duration (int): Display duration in seconds (default 10)
        """
        # implementation...
```

## Best Practices

1. **Always include type hints** in function signatures
2. **Document all parameters** with their types and purpose
3. **Describe return values** including structure for complex types (dicts, lists)
4. **Note default values** in optional parameters
5. **Mention exceptions** that might be raised
6. **Keep descriptions concise** but informative
7. **Use proper formatting** with blank lines between sections

## Status

- ✅ File headers: All files updated with proper format
- ✅ Author information: Updated to "B. van Ritbergen <bas@ritbit.com>"
- ✅ Fixed malformed headers: Removed literal `\n` characters
- ✅ Function documentation: Added to sysinfo.py (example)
- ✅ Class documentation: Added to AlertManager (example)
- 🔄 Remaining files: Apply same pattern to all classes and functions

## Next Steps

Continue adding docstrings to:
- All classes in signage/ modules
- All public methods and functions
- Complex private methods that need clarification
