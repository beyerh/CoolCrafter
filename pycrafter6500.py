#!/usr/bin/env python
# -*- coding: utf-8 -*-

## @package pycrafter6500
#  Python package for the lightcrafter 6500

import usb.core
import usb.util
import numpy

# DLPC900 Pattern On-The-Fly mode hardware limitation
# Test your hardware with determine_max_exposure.py to find your limits
MAX_SAFE_EXPOSURE_US = 5000000  # 5 seconds - hardware maximum (test your hardware!)
MAX_RECOMMENDED_EXPOSURE_US = 3000000  # 3 seconds - recommended safe limit
import sys
from erle import encode, encode_8bit


##function that converts a number into a bit string of given length

def convlen(a,l):
    b=bin(a)[2:]
    padding=l-len(b)
    b='0'*padding+b

    return b

##function that converts a bit string into a given number of bytes

def bitstobytes(a):
    bytelist=[]
    if len(a)%8!=0:
        padding=8-len(a)%8
        a='0'*padding+a
    for i in range(len(a)//8):
        bytelist.append(int(a[8*i:8*(i+1)],2))

    bytelist.reverse()

    return bytelist

##a dmd controller class

class dmd():
    def __init__(self):
        self.dev=usb.core.find(idVendor=0x0451 ,idProduct=0xc900 )

        self.dev.set_configuration()

        self.ans=[]
        
        # USB timeout in milliseconds (60 seconds for large 8-bit uploads)
        # Default is usually 1000ms (1 sec) which is too short for large patterns
        # 60s is needed because DMD needs time to process large compressed images
        self.usb_timeout = 60000

## standard usb command function

    def command(self,mode,sequencebyte,com1,com2,data=None):
        buffer = []

        flagstring=''
        if mode=='r':
            flagstring+='1'
        else:
            flagstring+='0'        
        flagstring+='1000000'
        buffer.append(bitstobytes(flagstring)[0])
        buffer.append(sequencebyte)
        temp=bitstobytes(convlen(len(data)+2,16))
        buffer.append(temp[0])
        buffer.append(temp[1])
        buffer.append(com2)
        buffer.append(com1)

        if len(buffer)+len(data)<65:
        
            for i in range(len(data)):
                buffer.append(data[i])

            for i in range(64-len(buffer)):
                buffer.append(0x00)


            self.dev.write(1, buffer, self.usb_timeout)

        else:
            for i in range(64-len(buffer)):
                buffer.append(data[i])

            self.dev.write(1, buffer, self.usb_timeout)

            buffer = []

            j=0
            while j<len(data)-58:
                buffer.append(data[j+58])
                j=j+1
                if j%64==0:
                    self.dev.write(1, buffer, self.usb_timeout)

                    buffer = []

            if j%64!=0:

                while j%64!=0:
                    buffer.append(0x00)
                    j=j+1


                self.dev.write(1, buffer, self.usb_timeout)                
                




        self.ans=self.dev.read(0x81, 64, self.usb_timeout)

## functions for checking error reports in the dlp answer

    def checkforerrors(self):
        self.command('r',0x22,0x01,0x00,[])
        if self.ans[6]!=0:
            error_code = self.ans[6]
            error_msg = f"DMD Error Code: {error_code} (0x{error_code:02X})"
            print(f"ERROR: {error_msg}")
            # Uncomment to raise exception on errors:
            # raise RuntimeError(error_msg)
            return error_code
        return 0    

## function printing all of the dlp answer

    def readreply(self):
        for i in self.ans:
            print (hex(i))

## functions for idle mode activation

    def idle_on(self):
        self.command('w',0x00,0x02,0x01,[int('00000001',2)])
        self.checkforerrors()

    def idle_off(self):
        self.command('w',0x00,0x02,0x01,[int('00000000',2)])
        self.checkforerrors()

## functions for power management

    def standby(self):
        self.command('w',0x00,0x02,0x00,[int('00000001',2)])
        self.checkforerrors()

    def wakeup(self):
        self.command('w',0x00,0x02,0x00,[int('00000000',2)])
        self.checkforerrors()

    def reset(self):
        self.command('w',0x00,0x02,0x00,[int('00000010',2)])
        self.checkforerrors()

## test write and read operations, as reported in the dlpc900 programmer's guide

    def testread(self):
        self.command('r',0xff,0x11,0x00,[])
        self.readreply()

    def testwrite(self):
        self.command('w',0x22,0x11,0x00,[0xff,0x01,0xff,0x01,0xff,0x01])
        self.checkforerrors()

## some self explaining functions

    def changemode(self,mode):
        self.command('w',0x00,0x1a,0x1b,[mode])
        self.checkforerrors()

    def startsequence(self):
        """Start DMD pattern sequence playback"""
        import time
        
        # Set Input Source to Streaming (required for Pattern OTF)
        self.command('w',0x00,0x1a,0x22,[0x00])
        self.checkforerrors()
        
        # Set Trigger Mode to Internal (patterns advance automatically)
        self.command('w',0x00,0x1a,0x23,[0x00])
        self.checkforerrors()
        
        # Start sequence playback
        self.command('w',0x00,0x1a,0x24,[2])
        self.checkforerrors()

    def pausesequence(self):
        self.command('w',0x00,0x1a,0x24,[1])
        self.checkforerrors()

    def stopsequence(self):
        """Stop DMD pattern sequence playback"""
        import time
        self.command('w',0x00,0x1a,0x24,[0])
        self.checkforerrors()
        time.sleep(0.15)  # Wait for DMD to clear buffers


    def configurelut(self,imgnum,repeatnum):
        img=convlen(imgnum,11)
        repeat=convlen(repeatnum,32)

        string=repeat+'00000'+img

        bytes=bitstobytes(string)

        # Configure LUT (no validation needed per DLPC900 reference implementations)
        self.command('w',0x00,0x1a,0x31,bytes)
        self.checkforerrors()
        

    def definepattern(self,index,exposure,bitdepth,color,triggerin,darktime,triggerout,patind,bitpos):
        payload=[]
        index=convlen(index,16)
        index=bitstobytes(index)
        for i in range(len(index)):
            payload.append(index[i])

        exposure=convlen(exposure,24)
        exposure=bitstobytes(exposure)
        for i in range(len(exposure)):
            payload.append(exposure[i])
        optionsbyte=''
        optionsbyte+='1'
        bitdepth=convlen(bitdepth-1,3)
        optionsbyte=bitdepth+optionsbyte
        optionsbyte=color+optionsbyte
        if triggerin:
            optionsbyte='1'+optionsbyte
        else:
            optionsbyte='0'+optionsbyte

        payload.append(bitstobytes(optionsbyte)[0])

        darktime=convlen(darktime,24)
        darktime=bitstobytes(darktime)
        for i in range(len(darktime)):
            payload.append(darktime[i])

        triggerout=convlen(triggerout,8)
        triggerout=bitstobytes(triggerout)
        payload.append(triggerout[0])

        patind=convlen(patind,11)
        bitpos=convlen(bitpos,5)
        lastbits=bitpos+patind
        lastbits=bitstobytes(lastbits)
        for i in range(len(lastbits)):
            payload.append(lastbits[i])



        self.command('w',0x00,0x1a,0x34,payload)
        self.checkforerrors()
        


    def setbmp(self,index,size):
        payload=[]

        index=convlen(index,5)
        index='0'*11+index
        index=bitstobytes(index)
        for i in range(len(index)):
            payload.append(index[i]) 


        total=convlen(size,32)
        total=bitstobytes(total)
        for i in range(len(total)):
            payload.append(total[i])         
        
        self.command('w',0x00,0x1a,0x2a,payload)
        self.checkforerrors()

## bmp loading function, divided in 56 bytes packages
## max  hid package size=64, flag bytes=4, usb command bytes=2
## size of package description bytes=2. 64-4-2-2=56

    def bmpload(self, image, size, progress_msg="", progress_callback=None):
        """Load compressed BMP data to DMD with progress feedback.
        
        Args:
            image: Compressed image data
            size: Size of compressed image
            progress_msg: Optional message prefix for progress updates
            progress_callback: Optional callback function(message) for GUI updates
        """
        packnum = size // 504 + 1
        counter = 0
        
        # Progress reporting every 10% or every 50 packets (whichever is more frequent)
        report_interval = max(1, min(50, packnum // 10))
        
        for i in range(packnum):
            # Progress feedback
            if i % report_interval == 0 or i == packnum - 1:
                percent = int((i + 1) * 100 / packnum)
                msg = f"  {progress_msg}Progress: {percent}% ({i+1}/{packnum} packets)"
                if progress_callback:
                    progress_callback(msg)
                else:
                    print(msg)
            
            payload = []
            if i < packnum - 1:
                leng = convlen(504, 16)
                bits = 504
            else:
                leng = convlen(size % 504, 16)
                bits = size % 504
            leng = bitstobytes(leng)
            for j in range(2):
                payload.append(leng[j])
            for j in range(bits):
                payload.append(image[counter])
                counter += 1
            
            try:
                self.command('w', 0x11, 0x1a, 0x2b, payload)
                
                # Skip error check on last packet - DMD is busy processing and won't respond
                if i < packnum - 1:
                    self.checkforerrors()
                else:
                    # Last packet - give DMD time to process without checking
                    import time
                    time.sleep(2.0)
                    
            except Exception as e:
                msg = f"  ERROR at packet {i+1}/{packnum}: {e}"
                if progress_callback:
                    progress_callback(msg)
                else:
                    print(msg)
                raise


    def defsequence(self, images, exp, ti, dt, to, rep, progress_callback=None):
        """
        Define a sequence for 1-bit patterns in Pattern On-The-Fly mode.
        
        Parameters:
        - images: List of 1-bit numpy arrays (values 0-1)
        - exp: List of exposure times in microseconds for each pattern
        - ti: List of trigger input flags (True/False)
        - dt: List of dark times in microseconds for each pattern
        - to: List of trigger output flags (0-3)
        - rep: Number of sequence repetitions (0xFFFFFFFF for infinite)
        
        Notes:
        - Maximum of 400 patterns in 1-bit mode
        - Patterns are processed in batches of 24
        - Each pattern can have individual timing and trigger settings
        """
        if len(images) > 400:
            raise ValueError("Maximum number of 1-bit patterns (400) exceeded")
        if not all(len(lst) == len(images) for lst in [exp, ti, dt, to]):
            raise ValueError("All input lists must have the same length as images list")
        
        import time
        
        # Required sequence for mode change (per DLPC900 reference implementations):
        # Stop → Set Pattern OTF mode → Stop again
        self.command('w',0x00,0x1a,0x24,[0])  # Stop before mode change
        self.checkforerrors()
        time.sleep(0.05)
        
        self.command('w',0x00,0x1a,0x1b,[3])  # Set Pattern On-The-Fly mode
        self.checkforerrors()
        time.sleep(0.05)
        
        self.command('w',0x00,0x1a,0x24,[0])  # Stop again after mode change
        self.checkforerrors()
        time.sleep(0.05)

        num = len(images)
        encodedimages = []
        sizes = []
        batch_size = 24  # Number of patterns per batch

        # Step 1: Encode all batches
        msg = f'Encoding {num} patterns into {(num-1)//batch_size + 1} batches...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for i in range(0, num, batch_size):
            batch = images[i:i+batch_size]
            batch_idx = i // batch_size
            msg = f'  Encoding batch {batch_idx + 1}...'
            if progress_callback:
                progress_callback(msg)
            else:
                print(msg)
            
            # Encode batch of 1-bit patterns
            imagedata, size = encode(batch)
            encodedimages.append(imagedata)
            sizes.append(size)
        
        # Step 2: Define all pattern parameters
        msg = f'Defining {num} patterns...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for i in range(0, num, batch_size):
            batch_idx = i // batch_size
            batch_len = min(batch_size, num - i)
            
            for j in range(batch_len):
                pattern_idx = i + j
                self.definepattern(
                    pattern_idx,         # Global pattern index
                    exp[pattern_idx],    # Exposure time
                    1,                   # 1-bit depth
                    '111',               # RGB color (white)
                    ti[pattern_idx],     # Trigger in
                    dt[pattern_idx],     # Dark time
                    to[pattern_idx],     # Trigger out
                    batch_idx,           # Batch index
                    j                    # Pattern index within batch
                )
        
        # Step 3: Configure LUT
        self.configurelut(num, rep)
        
        # Step 4: Upload images in reverse order (required by DLPC900)
        num_batches = len(encodedimages)
        msg = f'Uploading {num_batches} batches in reverse order...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for idx, batch_idx in enumerate(reversed(range(num_batches))):
            msg = f'  Batch {batch_idx} ({idx+1}/{num_batches})...'
            if progress_callback:
                progress_callback(msg)
            else:
                print(msg)
            self.setbmp(batch_idx, sizes[batch_idx])
            self.bmpload(encodedimages[batch_idx], sizes[batch_idx], 
                        progress_msg=f"Batch {batch_idx}: ",
                        progress_callback=progress_callback)


    def defsequence_8bit(self, images, exp, ti, dt, to, rep, progress_callback=None):
        """
        Define a sequence for 8-bit grayscale patterns in Pattern On-The-Fly mode.
        
        Parameters:
        - images: List of 8-bit grayscale numpy arrays (values 0-255)
        - exp: List of exposure times in microseconds for each pattern
        - ti: List of trigger input flags (True/False)
        - dt: List of dark times in microseconds for each pattern
        - to: List of trigger output flags (0-3)
        - rep: Number of sequence repetitions (0xFFFFFFFF for infinite)
        
        Notes:
        - Maximum of 25 patterns in 8-bit mode due to hardware buffer limitations
        - Each 8-bit pattern requires ~370KB compressed, ~9MB total for 25 patterns
        - Each pattern can have individual timing and trigger settings
        - For more patterns, consider using 1-bit mode (max 400 patterns)
        """
        max_patterns = 25
        if len(images) > max_patterns:
            raise ValueError(f"Maximum number of 8-bit patterns ({max_patterns}) exceeded")
        if not all(len(lst) == len(images) for lst in [exp, ti, dt, to]):
            raise ValueError("All input lists must have the same length as images list")
        
        import time
        
        # Required sequence for mode change (per DLPC900 reference implementations):
        # Stop → Set Pattern OTF mode → Stop again
        self.command('w',0x00,0x1a,0x24,[0])  # Stop before mode change
        self.checkforerrors()
        time.sleep(0.05)
        
        self.command('w',0x00,0x1a,0x1b,[3])  # Set Pattern On-The-Fly mode
        self.checkforerrors()
        time.sleep(0.05)
        
        self.command('w',0x00,0x1a,0x24,[0])  # Stop again after mode change
        self.checkforerrors()
        time.sleep(0.05)
        
        num = len(images)
        encodedimages = []
        sizes = []

        # Step 1: Encode all 8-bit patterns
        msg = f'Encoding {num} 8-bit patterns...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for i in range(num):
            msg = f'  Encoding 8-bit pattern {i+1}/{num}...'
            if progress_callback:
                progress_callback(msg)
            else:
                print(msg)
            
            # Encode the 8-bit pattern
            imagedata, size = encode_8bit([images[i]])
            encodedimages.append(imagedata)
            sizes.append(size)
        
        # Step 2: Define all pattern parameters
        msg = f'Defining {num} 8-bit patterns...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for i in range(num):
            # Define pattern with 8-bit depth
            # patind = i (each image gets its own index)
            # bitpos = 0 (for 8-bit mode, DMD handles bit planes internally)
            self.definepattern(
                i,             # Pattern index
                exp[i],        # Exposure time
                8,             # 8-bit depth
                '111',         # RGB color (white)
                ti[i],         # Trigger in
                dt[i],         # Dark time
                to[i],         # Trigger out
                i,             # Pattern set index (one per pattern for 8-bit)
                0              # Bit position (0 for 8-bit)
            )
        
        # Step 3: Configure LUT
        self.configurelut(num, rep)
        
        # Step 4: Upload images in reverse order (required by DLPC900)
        msg = f'Uploading {num} 8-bit patterns in reverse order...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        msg = f'  Note: 8-bit uploads are large and may take several minutes...'
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)
        for idx, i in enumerate(reversed(range(num))):
            msg = f'  Pattern {i} ({idx+1}/{num}) - {sizes[i]} bytes...'
            if progress_callback:
                progress_callback(msg)
            else:
                print(msg)
            self.setbmp(i, sizes[i])
            self.bmpload(encodedimages[i], sizes[i], 
                        progress_msg=f"Pattern {i}: ",
                        progress_callback=progress_callback)
