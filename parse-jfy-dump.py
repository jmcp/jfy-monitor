#!/usr/bin/python3.4

import os
import struct
import sys

pkthead = 0xA5A5
pktend = 0x0A0D

# packet format is
# header        0xa5a5
# src addr      1 byte
# dest addr     1 byte
# ctrl code     1 byte
# func code     1 byte
# data length   1 byte
# [Data0 to DataN-1]
# checksum      2 bytes
# tail          0x0a0d
#
# Minimum pkt length is 11 bytes
#
# Header  Source  Dest  Ctrl  Function  Datalen   Checksum  Tail
# a5a5     00      01    30    00        N         QQWW     0a0d

headerlen = 7   # includes byte for Datalen
taillen = 4

ctrlop = {
    0x30: "register",
    0x31: "read",
    0x32: "write",
    0x33: "execute"
}

register_funcs = {
    0x40: "Offline Query",
    0x41: "Send Register Address",
    0x42: "Remove Registration",
    0x43: "Reconnect Removed Inverter",
    0x44: "Re-register"  # not in the spec
}

register_resps = {
    0xbf: "Register Request",
    0xbe: "Address Confirmation",
    0xbd: "Remove Registration",
    0xbc: "Re-registration"
}


read_funcs = {
    0x40: "Read Description",
    0x41: "Read/Write Description",
    0x42: "Query normal information",
    0x43: "Query inverter invariant information",
    0x44: "Read fixed information",
    0x45: "Read RTC time",
    0x46: "Read Model info (10k)",
    0x47: "Riello Fixsize",
    0x48: "Pv33 SlaveA information",
    0x49: "Pv33 SlaveB informatin",
    0x4a: "Read DC Current Injection (10k)",
    0x4b: "Read Master-Slave-Logger version"
}


read_resps = {
    0xbf: "Read Description",
    0xbe: "Read/Write Description",
    0xbd: "Query normal information",
    0xbc: "Query inverter invariant information",
    0xbb: "Read fixed information",
    0xba: "Read RTC time",
    0xb9: "Read Model info (10k)",
    0xb8: "Riello Fixsize",
    0xb7: "Pv33 SlaveA information",
    0xb6: "Pv33 SlaveB informatin",
    0xb5: "Read DC Current Injection (10k)",
    0xb4: "Read Master-Slave-Logger version"
}


# Data byte types and multipliers. Each element is two bytes long.
databytes = {
    0x00: ["Inverter internal temperature", 0.1, "degrees C"],
    0x01: ["PV1 voltage", 0.1, "Volts"],
    0x02: ["PV2 voltage", 0.1, "Volts"],
    0x03: ["PV3 voltage", 0.1, "Volts"],
    0x04: ["PV1 current", 0.1, "Amps"],
    0x05: ["PV2 current", 0.1, "Amps"],
    0x06: ["PV3 current", 0.1, "Amps"],
    0x07: ["Total energy to grid (H)", 0.1, "KW/hr"],
    0x08: ["Total energy to grid (L)", 0.1, "KW/hr"],
    0x09: ["Total operating hours (H)", 1, "Hours"],
    0x0a: ["Total operating hours (H)", 1, "Hours"],
    0x0b: ["Total power to grid", 1, "Watts"],
    0x0c: ["Operating mode", 1, ""],
    0x0d: ["Energy generated today", 0.01, "KW/hr"],
    0x0e: ["PV4 voltage", 0.1, "Volts"],
    0x0f: ["PV5 voltage", 0.1, "Volts"],
    0x10: ["PV6 voltage", 0.1, "Volts"],
    0x11: ["PV4 current", 0.1, "Amps"],
    0x12: ["PV5 current", 0.1, "Amps"],
    0x13: ["PV6 current", 0.1, "Amps"],
    0x14: ["PV7 voltage", 0.1, "Volts"],
    0x15: ["PV8 voltage", 0.1, "Volts"],
    0x16: ["PV9 voltage", 0.1, "Volts"],
    0x17: ["PV7 current", 0.1, "Amps"],
    0x18: ["PV8 current", 0.1, "Amps"],
    0x19: ["PV9 current", 0.1, "Amps"],
    0x1a: ["0x1a currently unknown", 1, "nerds"],
    0x1b: ["0x1b currently unknown", 1, "nerds"],
    0x1c: ["0x1c currently unknown", 1, "nerds"],
    0x1d: ["0x1d currently unknown", 1, "nerds"],
    0x1e: ["0x1e currently unknown", 1, "nerds"],
    0x1f: ["0x1f currently unknown", 1, "nerds"],
    0x20: ["0x20 currently unknown", 1, "nerds"],
    0x21: ["0x21 currently unknown", 1, "nerds"],
    0x22: ["0x22 currently unknown", 1, "nerds"],
    0x23: ["0x23 currently unknown", 1, "nerds"],
    0x24: ["0x24 currently unknown", 1, "nerds"],
    0x25: ["0x25 currently unknown", 1, "nerds"],
    0x26: ["0x26 currently unknown", 1, "nerds"],
    0x27: ["0x27 currently unknown", 1, "nerds"],
    0x28: ["0x28 currently unknown", 1, "nerds"],
    0x29: ["0x29 currently unknown", 1, "nerds"],
    0x2a: ["0x2a currently unknown", 1, "nerds"],
    0x2b: ["0x2b currently unknown", 1, "nerds"],
    0x2c: ["0x2c currently unknown", 1, "nerds"],
    0x2d: ["0x2d currently unknown", 1, "nerds"],
    0x2e: ["0x2e currently unknown", 1, "nerds"],
    0x2f: ["0x2f currently unknown", 1, "nerds"],
    0x30: ["0x30 currently unknown", 1, "nerds"],
    0x31: ["0x31 currently unknown", 1, "nerds"],
    #
    0x39: ["Temperature fault value", 0.1, "degrees C"],
    0x3a: ["PV1 voltage fault value", 0.1, "Volts"],
    0x3b: ["PV2 voltage fault value", 0.1, "Volts"],
    0x3c: ["PV3 voltage fault value", 0.1, "Volts"],
    0x3d: ["Grid fault current value", 0.001, "Amps"],
    0x3e: ["Error message (H)", 1, ""],
    0x3f: ["Error message (L)", 1, ""],
    #
    # Single phase, or the R phase for 3phase system
    0x40: ["RPhase PV voltage", 0.1, "Volts"],
    0x41: ["RPhase Current to grid", 0.1, "Amps"],
    0x42: ["RPhase Grid voltage", 0.1, "Volts"],
    0x43: ["RPhase Grid frequency", 0.01, "Hertz"],
    0x44: ["RPhase Power to grid", 1, "Watts"],
    0x45: ["RPhase Grid impedance", 0.001, "Ohm"],
    0x46: ["RPhase PV current", 0.1, "Amps"],
    0x47: ["RPhase Energy to grid (H)", 0.1, "KW/hr"],
    0x48: ["RPhase Energy to grid (L)", 0.1, "KW/hr"],
    0x49: ["RPhase Total operating hours (H)", 1, "Hours"],
    0x4a: ["RPhase Total operating hours (L)", 1, "Hours"],
    0x4b: ["RPhase Power on time", 1, ""],
    0x4c: ["RPhase Operating mode", 1, ""],
    0x4d: ["0x4d currently unknown", 1, "nerds"],    
    0x4e: ["0x4d currently unknown", 1, "nerds"],    
    0x4f: ["0x4d currently unknown", 1, "nerds"],    
    0x50: ["0x4d currently unknown", 1, "nerds"],    
    0x51: ["0x4d currently unknown", 1, "nerds"],    
    0x52: ["0x4d currently unknown", 1, "nerds"],    
    0x53: ["0x4d currently unknown", 1, "nerds"],    
    0x54: ["0x4d currently unknown", 1, "nerds"],    
    0x55: ["0x4d currently unknown", 1, "nerds"],    
    0x56: ["0x4d currently unknown", 1, "nerds"],    
    0x57: ["0x4d currently unknown", 1, "nerds"],    
    0x58: ["0x4d currently unknown", 1, "nerds"],    
    0x59: ["0x4d currently unknown", 1, "nerds"],    
    0x5a: ["0x4d currently unknown", 1, "nerds"],    
    0x5b: ["0x4d currently unknown", 1, "nerds"],    
    0x5c: ["0x4d currently unknown", 1, "nerds"],    
    0x5d: ["0x4d currently unknown", 1, "nerds"],    
    0x5e: ["0x4d currently unknown", 1, "nerds"],    
    0x5f: ["0x4d currently unknown", 1, "nerds"],    
    0x60: ["0x4d currently unknown", 1, "nerds"],    
    0x61: ["0x4d currently unknown", 1, "nerds"],    
    0x62: ["0x4d currently unknown", 1, "nerds"],    
    0x63: ["0x4d currently unknown", 1, "nerds"],    
    0x64: ["0x4d currently unknown", 1, "nerds"],    
    0x65: ["0x4d currently unknown", 1, "nerds"],    
    0x66: ["0x4d currently unknown", 1, "nerds"],    
    0x67: ["0x4d currently unknown", 1, "nerds"],    
    0x68: ["0x4d currently unknown", 1, "nerds"],    
    0x69: ["0x4d currently unknown", 1, "nerds"],    
    0x6a: ["0x4d currently unknown", 1, "nerds"],    
    0x6b: ["0x4d currently unknown", 1, "nerds"],    
    0x6c: ["0x4d currently unknown", 1, "nerds"],    
    0x6d: ["0x4d currently unknown", 1, "nerds"],    
    0x6e: ["0x4d currently unknown", 1, "nerds"],    
    0x6f: ["0x4d currently unknown", 1, "nerds"],    
    
    #
    0x78: ["Grid voltage fault value", 0.1, "Volts"],
    0x79: ["Grid frequency fault value", 0.01, "Hertz"],
    0x7a: ["Grid impedance fault value", 0.001, "Ohm"],
    0x7b: ["Temperature fault value", 0.1, "degrees C"],
    0x7c: ["PV1 voltage fault value", 0.1, "Volts"],
    0x7d: ["Grid fault current value", 0.001, "Amps"],
    0x7e: ["Error message H", 1, ""],
    0x7f: ["Error message L", 1, ""]
    # We're ignoring the S and T phases for now
}


opmodes = {
    0x0000: "Waiting",
    0x0001: "Normal",
    0x0002: "Fault (transient)",
    0x0003: "Fault (permanent)"
}
    


def DecodeStringData(vals=None):
    """Translates bytes to ascii"""
    rstr = ""
    for n in range(0, len(vals)):
        if vals[n] < 0x20 or vals[n] > 0x7f:
            rstr = rstr + "{:02x}".format(vals[n])
        elif vals[n] is 0x20:
            rstr = rstr + "."
        else:
            rstr = rstr + "{:s}".format(chr(int(vals[n])))
    return rstr

def DecodeData(vals=None, raw=False):
    """Decoding function for func 0xbd"""
    rstr = ""
    bformat = "{0:04x} {1:34s} {2:<8f} {3:8s}\n"
    raws = ""
    cooked = ""
    for n in range(2, len(vals) - 1):
        if raw:
            raws = raws + "{0:<02x}".format(vals[n])
        else:
            bval = (vals[n] << 8) | vals[n+1]
            cooked = cooked + bformat.format(
                bval,
                databytes[n + 0x3f][0],
                float(bval * databytes[n + 0x3f][1]),
                databytes[n + 0x3f][2])
        n = n + 1
    if raw:
        return raws
    else:
        return cooked

    
def checksum(vals=None):
    """calculates the checksum of the data values provided"""
    csum = 0
    for i in range(0, len(vals)):
        csum = csum + vals[i]
    csum ^= 0xffff
    return csum + 1


def parsepkt(pkt=None):
    """parses the packet and produces formatted output"""
    desc = {}
    plen = len(pkt)
    rcsum = hex(struct.unpack("!H", bytearray(pkt[plen-4:plen-2]))[0])
    calcsum = hex(checksum(bytearray(pkt[0:plen - 4])))
    if calcsum != rcsum:
        # Whoa ... error on the wire
        print("Calculated checksum ({0}) does not match read value ({1})".
              format(calcsum, rcsum))
        print("{0}".format([hex(n) for n in pkt]))
        return

    hmsg = "{0} {1:=02X} {2} {3:=02X} {4} {5:=02X} ({6})".format(
        "Source", pkt[2], "Destination", pkt[3], "Control Op",
        pkt[4], ctrlop[pkt[4]])
    if pkt[4] is 0x30:
        if pkt[5] < 0x50:
            # horrible hack
            desc = register_funcs
        else:
            desc = register_resps
    elif pkt[4] is 0x31:
        if pkt[5] < 0x50:
            # horrible hack
            desc = read_funcs
        else:
            desc = read_resps
    else:
        # not supported
        print("Control op is {0}, which this utility doesn't support\n".
              format(ctrlop[pkt3]))
        return
    if pkt[5] < 0x50:
        hmsg = hmsg + " (ap->inverter) {0} (0x{1:=02x})".format(
            desc[pkt[5]], pkt[5])
    else:
        hmsg = hmsg + " (inverter->ap) {0} (0x{1:=02x})".format(
            desc[pkt[5]], pkt[5])

    print(hmsg)
    print("{0}\n".format(DecodeData(pkt, True)))

    tpkt = bytearray(pkt[7:plen - 5])
    print("Packet data: ({0} bytes)\n".format(pkt[6]))
    if pkt[5] is 0xbd:
        print("{0}\n".format(DecodeData(tpkt, True)))
        print("{0}\n".format(DecodeData(tpkt, False)))
    else:
        print("{0}\n".format(DecodeStringData(tpkt)))
        # for now...


if __name__ == "__main__":
    inf = open(sys.argv[1], "rb")
    binf = bytearray(inf.read())
    # basic loop:
    i = 0
    while i < len(binf):
        if binf[i] == 0xa5 and binf[i+1] == 0xa5:
            pkt = list()
            dlen = binf[i+6]
            tlen = headerlen + taillen + dlen
            for j in range(0, tlen):
                pkt.append(binf[i + j])
                
            #while binf[i] != 0x0a and binf[i+1] != 0x0d:
            #    pkt.append(binf[i])
            #    i = i + 1
                # don't forget the end bytes
            parsepkt(pkt)
            del pkt
        i = i + 1
