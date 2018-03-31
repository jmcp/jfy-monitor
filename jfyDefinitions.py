#! /usr/bin/python3

#
# Copyright (c) 2013, 2018 James C. McPherson.  All Rights Reserved
#
#

#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

#  ACKNOWLEDGEMENTS:
#
#  This utility builds upon the work known as Solarmonj,
#  <https://code.google.com/p/solarmonj/> by John Croucher
#  (<http://jcroucher.com>)
#
#  This utility depends on the JFY serial protocol document
#  found at http://www.fergo.net/JFY-REVISED.pdf, as noted
#  in http://forums.whirlpool.net.au/forum-replies.cfm?t=1899721.
#  An alternate location for this file is
#  https://github.com/johnf/jfy/blob/master/doc/JFY-REVISED.pdf
#

CtrlCodes = {
    'name': 'CtrlCodes',
    0x30: 'Register',
    0x31: 'Read',
    0x32: 'Write',
    0x33: 'Execute',
    'Register': 0x30,
    'Read': 0x31,
    'Write': 0x32,
    'Execute': 0x33
}

UnsupportedOpCodes = {
    'name': 'UnsupportedOpcodes'
}

RegisterCodes = {
    'name': 'RegisterCodes',
    0x40: 'OfflineQuery',
    0x41: 'SendRegisterAddress',
    0x42: 'RemoveRegister',
    0x43: 'ReconnectRemovedInverter',
    0x44: 'ReRegister',
    0xbb: 'ReRegisterResponse',
    0xbc: 'ReconnectRemovedInverterResponse',
    0xbd: 'RemoveRegisterResponse',
    0xbe: 'SendRegisterAddressResponse',
    0xbf: 'OfflineQueryResponse',
    'OfflineQuery': 0x40,
    'SendRegisterAddress': 0x41,
    'RemoveRegister': 0x42,
    'ReconnectRemovedInverter': 0x43,
    'ReRegister': 0x44,
    'ReRegisterResponseCode': 0xbb,
    'ReconnectRemovedInverterResponseCode': 0xbc,
    'RemoveRegisterResponseCode': 0xbd,
    'SendRegisterAddressResponseCode': 0xbe,
    'OfflineQueryResponseCode': 0xbf
}

ReadCodes = {
    'name': 'ReadCodes',
    0x40: 'ReadDescription',
    0x41: 'ReadWriteDescription',
    0x42: 'QueryNormalInfo',
    0x43: 'QueryInverterIdInfo',
    0x44: 'ReadSetInfo',
    0x45: 'ReadRtcTime',
    0x46: 'ReadModelInfo',
    0x47: 'RielloFixSize',
    0x48: 'Pv33SlaveAInfo',
    0x49: 'Pv33SlaveBInfo',
    0x4a: 'ReadDcCurrentInjection',
    0x4b: 'ReadMasterSlaveLoggerVersion',
    0xb4: 'ReadMasterSlaveLoggerVersionResponse',
    0xb5: 'ReadDcCurrentInjectionResponse',
    0xb6: 'Pv33SlaveBInfoResponse',
    0xb7: 'Pv33SlaveAInfoResponse',
    0xb8: 'RielloFixSizeResponse',
    0xb9: 'ReadModelInfoResponse',
    0xba: 'ReadRtcTimeResponse',
    0xbb: 'ReadSetInfoResponse',
    0xbc: 'QueryInverterIdInfoResponse',
    0xbd: 'QueryNormalInfoResponse',
    0xbe: 'ReadWriteDescriptionResponse',
    0xbf: 'ReadDescriptionResponse',
    'ReadDescription': 0x40,
    'ReadWriteDescription': 0x41,
    'QueryNormalInfo': 0x42,
    'QueryInverterIdInfo': 0x43,
    'ReadSetInfo': 0x44,
    'ReadRtcTime': 0x45,
    'ReadModelInfo': 0x46,
    'RielloFixSize': 0x47,
    'Pv33SlaveAInfo': 0x48,
    'Pv33SlaveBInfo': 0x49,
    'ReadDcCurrentInjection': 0x4a,
    'ReadMasterSlaveLoggerVersion': 0x4b,
    'ReadMasterSlaveLoggerVersionResponseCode': 0xb4,
    'ReadDcCurrentInjectionResponseCode': 0xb5,
    'Pv33SlaveBInfoResponseCode': 0xb6,
    'Pv33SlaveAInfoResponseCode': 0xb7,
    'RielloFixSizeResponseCode': 0xb8,
    'ReadModelInfoResponseCode': 0xb9,
    'ReadRtcTimeResponseCode': 0xba,
    'ReadSetInfoResponseCode': 0xbb,
    'QueryInverterIdInfoResponseCode': 0xbc,
    'QueryNormalInfoResponseCode': 0xbd,
    'ReadWriteDescriptionResponseCode': 0xbe,
    'ReadDescriptionResponseCode': 0xbf
}



jfyHeader = [0xa5, 0xa5]
jfyEnder = [0x0a, 0x0d]

jfyAck = 0x06
APid = 1
bcast = 0

#
# These names and the divisors below have been determined empirically,
# based on observing the output on the inverter front panel. Not ideal,
# but the spec (see level-0 comment above) is inaccurate and misleading.
#
JFYData = [
    "temperature",        #   0-1 deg C
    "powerGenerated",     #   2-3 watts
    "voltageDC",          #   4-5 volts
    "current",            #   6-7 amps
    #ignored,             #   8-9 ignored
    "energyGenerated",    # 10-11 watt-hours
    #ignored,             # 12-13 KW/Hr instantaneous energy
    "voltageAC",          # 14-15 volts
    #ignore2,             # 16-17 ignored
    #ignore3              # 18-19 ignored
    ]

JFYDivisors = [
    10.0,        # temperature
    10.0,        # powerGenerated
    10.0,        # voltageDC
    10.0,        # current
    0.1,         # energyGenerated
    10.0         # voltageAC
]


# We might receive garbage or null responses from the inverter,
# sending back a list of 0s allows us to continue without having
# to muck about with exceptions.
JFYEmpty = [0, 0, 0, 0, 0, 0]

RESOURCE_SSID_PREFIX = "//:class.app/solar/jfy//:res.inverter/"

STATS = [
    "temperature",
    "power-generated",
    "voltage-dc",
    "current",
    "energy-generated",
    "voltage-ac"
    ]

# Basic url to connect to for PVOutput.org
SERVICEURL = "http://pvoutput.org/service/r2/addstatus.jsp"


# sstored only accepts [-a-z]|[A-Z]|[0-9\\/] for class names, so
# we'll play things safe and use the same list list of acceptable
# characters for device serial numbers. These are the decimal values
# of the ASCII characters in the set.
charset = set([45, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 65, 66,
               67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79,
               80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 97, 98,
               99, 100, 101, 102, 103, 104, 105, 106, 107, 108,
               109, 110, 111, 112, 113, 114, 115, 116, 117, 118,
               119, 120, 121, 122])
