#!/usr/bin/env python
"""
Hardware Exposure Time Limit Test
==================================
This script helps you determine the ACTUAL maximum exposure time
supported by your DLPC900 hardware in Pattern On-The-Fly mode.

INSTRUCTIONS:
1. Connect your DMD hardware
2. Run this script: python determine_max_exposure.py
3. Watch the DMD projection (NOT the console timing)
4. For each test, note if the white pattern stays on for the FULL duration
5. Script will identify your hardware's maximum working exposure time
6. Update the constants in your code based on the results

IMPORTANT: Watch the DMD screen, not the script timing!
"""

import pycrafter6500
import numpy as np
import time
import sys

def wait_for_user(prompt):
    """Wait for user to press Enter"""
    if sys.version_info[0] >= 3:
        input(prompt)
    else:
        raw_input(prompt)

def test_exposure(dlp, exposure_us, test_image):
    """Test a single exposure time and get user feedback"""
    exposure_sec = exposure_us / 1000000.0
    
    print(f"\n{'='*70}")
    print(f"Testing: {exposure_us:,} μs ({exposure_sec:.1f} seconds)")
    print(f"{'='*70}")
    
    # Configure sequence
    images = [test_image]
    exposure = [exposure_us]
    trigger_in = [False]
    dark_time = [0]
    trigger_out = [1]
    repeat = 1
    
    print("Configuring sequence...")
    dlp.defsequence(images, exposure, trigger_in, dark_time, trigger_out, repeat)
    
    print("\n*** GET READY TO WATCH THE DMD ***")
    print(f"The white pattern should stay on for {exposure_sec:.1f} seconds")
    print(f"If it disappears EARLIER, it FAILED")
    print(f"Press Enter when ready...")
    wait_for_user("")
    
    print(f"\nStarting projection NOW! Watch the DMD for {exposure_sec:.1f} seconds...")
    dlp.startsequence()
    
    # Wait for the pattern to complete
    time.sleep(exposure_sec + 1.0)
    
    dlp.stopsequence()
    
    # Get user feedback
    print(f"\nDid the pattern stay on for the FULL {exposure_sec:.1f} seconds?")
    print("(If it disappeared earlier, answer 'no')")
    
    while True:
        response = input("Enter 'yes' or 'no': ").strip().lower()
        if response in ['yes', 'y']:
            return True
        elif response in ['no', 'n']:
            return False
        else:
            print("Please enter 'yes' or 'no'")

def main():
    print("\n" + "="*70)
    print("DLPC900 Maximum Exposure Time Determination Tool")
    print("="*70)
    
    print("\nThis tool will help you find the maximum exposure time")
    print("supported by YOUR specific hardware configuration.")
    
    print("\n⚠️  IMPORTANT:")
    print("  - Watch the DMD projection, NOT the console!")
    print("  - Pattern should stay bright for the FULL test duration")
    print("  - If it goes dark early, the test FAILED")
    
    wait_for_user("\nPress Enter to start testing...")
    
    # Connect to DMD
    print("\nConnecting to DMD...")
    try:
        dlp = pycrafter6500.dmd()
        print("✓ Connected successfully")
    except Exception as e:
        print(f"❌ Error connecting to DMD: {e}")
        print("\nMake sure:")
        print("  1. DMD is powered on")
        print("  2. USB cable is connected")
        print("  3. Drivers are installed (Windows: use Zadig)")
        return
    
    # Create test pattern (solid white)
    test_image = np.ones((1080, 1920), dtype=np.uint8)
    
    # Test exposure times (in microseconds)
    # Start low and work up to find the breaking point
    test_exposures = [
        1000000,    # 1 second (should always work)
        2000000,    # 2 seconds
        3000000,    # 3 seconds (confirmed safe on most hardware)
        4000000,    # 4 seconds
        5000000,    # 5 seconds
        6000000,    # 6 seconds
        7000000,    # 7 seconds
        8000000,    # 8 seconds
        10000000,   # 10 seconds
    ]
    
    results = {}
    max_working = 0
    first_failing = None
    
    print("\n" + "="*70)
    print("Starting systematic exposure time tests...")
    print("="*70)
    
    for exposure_us in test_exposures:
        try:
            worked = test_exposure(dlp, exposure_us, test_image)
            results[exposure_us] = worked
            
            if worked:
                max_working = exposure_us
                print(f"✓ Result: {exposure_us/1000000:.1f}s exposure WORKS")
            else:
                print(f"✗ Result: {exposure_us/1000000:.1f}s exposure FAILED")
                if first_failing is None:
                    first_failing = exposure_us
                # Stop testing once we find a failure
                print("\nFound the breaking point! Stopping tests.")
                break
                
        except Exception as e:
            print(f"❌ Error during test: {e}")
            results[exposure_us] = False
            break
    
    # Print summary
    print("\n" + "="*70)
    print("TEST RESULTS SUMMARY")
    print("="*70)
    
    print("\nTest Results:")
    for exposure_us, worked in sorted(results.items()):
        status = "✓ WORKS" if worked else "✗ FAILS"
        print(f"  {exposure_us:>10,} μs ({exposure_us/1000000:>4.1f}s): {status}")
    
    print("\n" + "-"*70)
    
    if max_working > 0:
        print(f"\n✅ CONFIRMED MAXIMUM: {max_working:,} μs ({max_working/1000000:.1f} seconds)")
        print(f"\nYour hardware supports exposure times up to {max_working/1000000:.1f} seconds.")
        
        if first_failing:
            print(f"Exposures at or above {first_failing/1000000:.1f}s will fail (terminate early).")
    else:
        print("\n⚠️  WARNING: No working exposures found!")
        print("This suggests a hardware or configuration issue.")
        return
    
    # Recommend values to use
    print("\n" + "="*70)
    print("RECOMMENDED CONFIGURATION VALUES")
    print("="*70)
    
    # Conservative recommendation: 80% of max
    recommended_safe = int(max_working * 0.8)
    
    print(f"\nBased on your hardware test results:")
    print(f"  • Confirmed maximum: {max_working:,} μs ({max_working/1000000:.1f}s)")
    print(f"  • Recommended safe limit: {recommended_safe:,} μs ({recommended_safe/1000000:.1f}s)")
    print(f"    (80% of maximum for safety margin)")
    
    print("\n" + "="*70)
    print("UPDATE YOUR CODE WITH THESE VALUES")
    print("="*70)
    
    print("\n1️⃣  Update pycrafter6500.py (around line 13):")
    print("-" * 70)
    print(f"""
# DLPC900 Pattern On-The-Fly mode hardware limitation
MAX_SAFE_EXPOSURE_US = {max_working}  # {max_working/1000000:.1f} seconds - YOUR hardware max
MAX_CONFIRMED_EXPOSURE_US = {recommended_safe}  # {recommended_safe/1000000:.1f} seconds - recommended safe
""")
    
    print("\n2️⃣  Update gui.py (around line 13):")
    print("-" * 70)
    print(f"""
# DLPC900 Pattern On-The-Fly hardware limits
MAX_SAFE_EXPOSURE_US = {max_working}  # {max_working/1000000:.1f} seconds - YOUR hardware max
MAX_RECOMMENDED_EXPOSURE_US = {recommended_safe}  # {recommended_safe/1000000:.1f} seconds - recommended safe
""")
    
    print("\n" + "="*70)
    print("USAGE GUIDELINES")
    print("="*70)
    
    print(f"""
✅ SAFE: Keep exposures ≤ {recommended_safe/1000000:.1f} seconds
   These will work reliably on your hardware.

⚠️  CAUTION: Exposures {recommended_safe/1000000:.1f}s - {max_working/1000000:.1f}s
   These work but you're close to the limit. Test thoroughly!

❌ AVOID: Exposures > {max_working/1000000:.1f} seconds
   These will fail (terminate early).
   Use workarounds: duplicate images or more cycles.
""")
    
    # Workaround example
    if max_working < 10000000:
        desired_time = 10  # 10 seconds
        cycles_needed = int(np.ceil(desired_time / (max_working/1000000)))
        print(f"\n💡 Example: For {desired_time}-second projection:")
        print(f"   • Set exposure to {max_working:,} μs ({max_working/1000000:.1f}s)")
        print(f"   • Use {cycles_needed} cycles")
        print(f"   • Total time: {cycles_needed * max_working/1000000:.1f}s ✓")
    
    print("\n" + "="*70)
    print("Testing complete! Save these values for your configuration.")
    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
