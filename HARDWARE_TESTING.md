# Hardware Exposure Time Testing Guide

## Overview

The DLPC900 Pattern On-The-Fly mode has a hardware-specific maximum exposure time limit (typically 3-6 seconds). This limit can vary between different hardware configurations, firmware versions, and DMD models.

This guide helps you determine YOUR specific hardware's maximum exposure time.

## Quick Start

```bash
python determine_max_exposure.py
```

Follow the on-screen prompts. The script will:
1. Test exposure times from 1 to 10 seconds
2. Ask you to visually confirm if each works
3. Identify your hardware's maximum
4. Provide exact values to update in your code

## What to Watch For

### ✅ WORKING Exposure
- Pattern stays **bright white** for the full test duration
- Example: 3-second test → pattern visible for full 3 seconds
- Pattern goes dark only after the specified time

### ❌ FAILING Exposure
- Pattern goes **dark early** (typically after 1-3 seconds)
- Example: 10-second test → pattern dark after 3 seconds
- Much shorter than the specified time

## Testing Process

### Step 1: Prepare
- Connect DMD hardware
- Power on and verify USB connection
- Close other applications using the DMD

### Step 2: Run Test
```bash
python determine_max_exposure.py
```

### Step 3: Watch the DMD (NOT the console!)
For each test:
1. Script says "GET READY TO WATCH THE DMD"
2. Press Enter when ready
3. **Watch the DMD screen** for the white pattern
4. Answer "yes" if pattern stayed on for FULL duration
5. Answer "no" if pattern went dark early 
### Step 4: Record Results
The script will show:
```
✅ CONFIRMED MAXIMUM: 5,000,000 μs (5.0 seconds)

RECOMMENDED CONFIGURATION VALUES
Based on your hardware test results:
  • Confirmed maximum: 5,000,000 μs (5.0s)
  • Recommended safe limit: 4,000,000 μs (4.0s)
```

### Step 5: Update Your Code

The script provides exact code snippets to copy-paste.

## Updating Configuration Values

### File 1: pycrafter6500.py

**Location:** Near the top of the file (around line 13)

**Find:**
```python
# DLPC900 Pattern On-The-Fly mode hardware limitation
MAX_SAFE_EXPOSURE_US = 5000000  # 5 seconds in microseconds
MAX_CONFIRMED_EXPOSURE_US = 3000000  # 3 seconds confirmed safe
```

**Replace with your tested values:**
```python
# DLPC900 Pattern On-The-Fly mode hardware limitation
MAX_SAFE_EXPOSURE_US = YOUR_MAX_HERE  # Your hardware maximum
MAX_CONFIRMED_EXPOSURE_US = YOUR_SAFE_HERE  # 80% of max for safety
```

### File 2: gui.py

**Location:** Near the top of the file (around line 13)

**Find:**
```python
# DLPC900 Pattern On-The-Fly hardware limits
MAX_SAFE_EXPOSURE_US = 5000000  # 5 seconds
MAX_RECOMMENDED_EXPOSURE_US = 3000000  # 3 seconds
```

**Replace with your tested values:**
```python
# DLPC900 Pattern On-The-Fly hardware limits
MAX_SAFE_EXPOSURE_US = YOUR_MAX_HERE  # Your hardware maximum
MAX_RECOMMENDED_EXPOSURE_US = YOUR_SAFE_HERE  # Recommended safe limit
```

## Example Results

### Example 1: Conservative Hardware (3-second max)

**Test Output:**
```
1.0s: ✓ WORKS
2.0s: ✓ WORKS
3.0s: ✓ WORKS
4.0s: ✗ FAILS
```

**Configuration:**
```python
MAX_SAFE_EXPOSURE_US = 3000000  # 3.0 seconds
MAX_CONFIRMED_EXPOSURE_US = 2400000  # 2.4 seconds (80% of max)
```

### Example 2: Better Hardware (5-second max)

**Test Output:**
```
1.0s: ✓ WORKS
2.0s: ✓ WORKS
3.0s: ✓ WORKS
4.0s: ✓ WORKS
5.0s: ✓ WORKS
6.0s: ✗ FAILS
```

**Configuration:**
```python
MAX_SAFE_EXPOSURE_US = 5000000  # 5.0 seconds
MAX_CONFIRMED_EXPOSURE_US = 4000000  # 4.0 seconds (80% of max)
```

## Understanding the Values

### MAX_SAFE_EXPOSURE_US
- **What it is:** The absolute maximum your hardware supports
- **Found by:** Testing until a failure occurs
- **GUI behavior:** Shows ERROR and blocks projection if exceeded
- **Use case:** Hard limit - never exceed this

### MAX_CONFIRMED_EXPOSURE_US (or MAX_RECOMMENDED_EXPOSURE_US)
- **What it is:** Conservative safe limit (typically 80% of max)
- **Purpose:** Provides safety margin for reliability
- **GUI behavior:** Shows WARNING (allows continuation)
- **Use case:** Recommended maximum for production use

## Troubleshooting

### Problem: All tests fail
**Possible causes:**
- Hardware not properly connected
- Wrong display mode
- Configuration issues

**Solutions:**
1. Verify DMD is powered and connected
2. Check USB drivers (Windows: use Zadig)
3. Try running one of the example scripts first
4. Check if DMD works with manufacturer's software

### Problem: Inconsistent results
**Possible causes:**
- Not watching DMD carefully
- Thermal effects (DMD heating up)
- Power supply issues

**Solutions:**
1. Let DMD cool down between tests
2. Run tests multiple times to confirm
3. Test in controlled environment
4. Check power supply is adequate

### Problem: Very low maximum (< 2 seconds)
**Possible causes:**
- Wrong firmware version
- Incorrect DMD model
- Hardware issue

**Solutions:**
1. Check firmware version
2. Verify DMD model compatibility
3. Test with manufacturer's software
4. Contact technical support

## Different Hardware Configurations

### DLP6500
- Typical range: 3-5 seconds
- Well-tested configuration

### DLP9000  
- Typical range: 3-5 seconds
- Similar to DLP6500

### DLP670S / DLP500YX
- Typical range: May vary
- Test your specific hardware

### DLP5500
- Typical range: 3-5 seconds
- Uses DLPA200 driver

## After Testing

### Update Documentation
Document your hardware's limits in your project:
```markdown
## Hardware Configuration
- DMD Model: DLP6500
- Firmware Version: X.X.X
- Maximum Exposure: 5.0 seconds (tested)
- Recommended Maximum: 4.0 seconds
- Test Date: 2025-01-08
```

### Share Results
If you test multiple hardware configurations, consider:
- Creating a compatibility chart
- Documenting firmware version effects
- Sharing results with the community

### Re-test After Changes
Re-run tests after:
- Firmware updates
- Hardware modifications
- Driver updates
- DMD replacement

## Workarounds for Long Exposures

If your maximum is lower than needed:

### Duplicate Images
For 10s exposure with 5s maximum:
```python
images = [pattern, pattern]  # Same image twice
exposure = [5000000, 5000000]  # 5s + 5s = 10s
cycles = 1
```

### Multiple Cycles
```python
images = [pattern]
exposure = [5000000]  # 5s
cycles = 2  # Repeat 2 times = 10s total
```

### Constant Mode with Software Timing
```python
dlp.defsequence([image], [5000000], [False], [0], [1], 0xFFFFFFFF)
dlp.startsequence()
time.sleep(10)  # Control duration in software
dlp.stopsequence()
```

## Support

For issues or questions:
1. Check `EXPOSURE_TIME_FIX_SUMMARY.md` for detailed fix information
2. Review `EXPOSURE_TIME_WORKAROUND.md` for alternative approaches
3. Consult the DLPC900 Programmer's Guide
4. Contact Texas Instruments support for hardware-specific questions

## Version History

- **v1.0** (2025-01-08): Initial release
  - Tests 1-10 second exposure range
  - Provides configuration recommendations
  - Includes workaround suggestions
