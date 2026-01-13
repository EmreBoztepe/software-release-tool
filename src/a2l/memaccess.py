#!/usr/bin/python
# -*- coding: latin-1 -*-
# --------------------------------------------------------------------------------
# @Title: Read & write memory via TRACE32 Remote API
# @Description: Example for accessing normal memory from a python script
# @Keywords: python
# @Author: HLG
# @Copyright: (C) 1989-2017 Lauterbach GmbH, licensed for use with TRACE32(R) only
# --------------------------------------------------------------------------------
# $Id: memaccess.py 116756 2020-01-27 07:42:44Z jvogl $
#

import platform
import ctypes

# Load library of the TRACE32 remote API
ostype = ctypes.sizeof(ctypes.c_voidp) * 8
if (platform.system()=='Windows') or (platform.system()[0:6]=='CYGWIN') :
  # WINDOWS
  t32api = ctypes.CDLL("./t32api64.dll" if ostype==64 else "./t32api.dll")
elif platform.system()=='Darwin' :
  # Mac OS X
  t32api = ctypes.CDLL("./t32api.dylib")
else :
  # Linux
  t32api = ctypes.CDLL("./t32api64.so" if ostype==64 else  "./t32api.so")

# Declare UDP/IP socket of the TRACE32 instance to access
t32api.T32_Config(b"NODE=",b"localhost")
t32api.T32_Config(b"PORT=",b"20000")
t32api.T32_Config(b"PACKLEN=",b"1024")

# Connect to TRACE32
error = t32api.T32_Init()
if error != 0 :
  sys.exit("Can't connect to TRACE32!")

# Select to debugger component of TRACE32 (B:: prompt)
t32api.T32_Attach(1)

# Declare argument types of T32_WriteMemory and T32_ReadMemory
t32api.T32_WriteMemory.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
t32api.T32_WriteMemory.restype  = ctypes.c_int
t32api.T32_ReadMemory.argtypes  = [ctypes.c_uint32, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
t32api.T32_ReadMemory.restype   = ctypes.c_int

# Set parameters for the memory access
byteAddress = 0x46c8  # ...or any other address
access      = 0x20  # access normal data memory, also when CPU is running (ED:)
byteSize    = 4 # amount of bytes to read or write (e.g. 4 bytes)

# Create buffer with the data to write in little endian byte order
wdata = 0x12345678  # ... or any other value
wbuffer = wdata.to_bytes(4, byteorder='little')

# Write data to memory via TRACE32
error = t32api.T32_WriteMemory(byteAddress, access, wbuffer, byteSize)
if error == 0 :
  print("wrote 0x%08X to   D:0x%08X successful" % (wdata, byteAddress))
else:
  print("write failed")

# Create a buffer for the result
rbuffer = ctypes.create_string_buffer(byteSize)

# Request memory content via TRACE32
error = t32api.T32_ReadMemory(byteAddress, access, rbuffer, byteSize)
if error == 0 :
  # Extract 32-bit value in little endian order from the buffer
  data32 = int.from_bytes(rbuffer[0:4], byteorder='little')
  print("read  0x%08X from D:0x%08X" % (data32, byteAddress))
else:
  print("read failed")


# Close connection to TRACE32
t32api.T32_Exit()

