# Generalized version of test-eptri script

from os import environ

import cocotb
from cocotb.utils import get_sim_time
from cocotb_tb.harness import get_harness
from cocotb.result import TestFailure
from cocotb_usb.device import UsbDevice
from cocotb_usb.usb.endpoint import EndpointType
from cocotb_usb.usb.pid import PID
from cocotb_usb.descriptors import (Descriptor, getDescriptorRequest,
                                    FeatureSelector, USBDeviceRequest,
                                    setFeatureRequest)

descriptorFile = environ['TARGET_CONFIG']
model = UsbDevice(descriptorFile)


@cocotb.test()
def test_control_setup(dut):
    harness = get_harness(dut)
    harness.max_packet_size = model.deviceDescriptor.bMaxPacketSize0
    yield harness.reset()
    yield harness.wait(10, units="us")

    yield harness.port_reset(5)
    yield harness.connect()
    yield harness.wait(10, units="us")
    # After waiting (bus inactivity) let's start with SOF
    yield harness.host_send_sof(0x01)
    # Device is at address 0 after reset
    yield harness.transaction_setup(
        0,
        setFeatureRequest(FeatureSelector.ENDPOINT_HALT,
                          USBDeviceRequest.Type.ENDPOINT, 0))
    harness.packet_deadline = get_sim_time("us") + harness.MAX_PACKET_TIME
    yield harness.transaction_data_in(0, 0, [])


@cocotb.test()
def test_control_transfer_in(dut):
    harness = get_harness(dut)
    harness.max_packet_size = model.deviceDescriptor.bMaxPacketSize0
    yield harness.reset()
    yield harness.wait(10, units="us")

    yield harness.port_reset(5)
    yield harness.connect()
    yield harness.wait(10, units="us")
    # After waiting (bus inactivity) let's start with SOF
    yield harness.host_send_sof(0x01)
    DEVICE_ADDRESS = 20
    yield harness.set_device_address(DEVICE_ADDRESS, skip_recovery=True)
    yield harness.control_transfer_in(
        DEVICE_ADDRESS,
        getDescriptorRequest(descriptor_type=Descriptor.Types.DEVICE,
                             descriptor_index=0,
                             lang_id=0,
                             length=18), model.deviceDescriptor.get())


@cocotb.test(skip=True)  # Doesn't set STALL as expected
def test_control_setup_clears_stall(dut):
    harness = get_harness(dut)
    harness.max_packet_size = model.deviceDescriptor.bMaxPacketSize0
    yield harness.reset()
    yield harness.wait(10, units="us")

    yield harness.port_reset(5)
    yield harness.connect()
    yield harness.wait(10, units="us")
    # After waiting (bus inactivity) let's start with SOF
    yield harness.host_send_sof(0x01)

    addr = 13
    yield harness.set_device_address(addr)
    yield harness.set_configuration(1)
    yield harness.wait(10, units="us")

    epaddr_out = EndpointType.epaddr(0, EndpointType.OUT)

    d = [0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0, 0]

    # send the data -- just to ensure that things are working
    yield harness.transaction_data_out(addr, epaddr_out, d)

    # send it again to ensure we can re-queue things.
    yield harness.transaction_data_out(addr, epaddr_out, d)

    # Set endpoint HALT explicitly
    yield harness.transaction_setup(
        addr,
        setFeatureRequest(FeatureSelector.ENDPOINT_HALT,
                          USBDeviceRequest.Type.ENDPOINT, 0))
    harness.packet_deadline = get_sim_time("us") + harness.MAX_PACKET_TIME
    yield harness.transaction_data_in(addr, 0, [])
    # do another receive, which should fail
    harness.retry = True
    harness.packet_deadline = get_sim_time("us") + 1e3  # try for a ms
    while harness.retry:
        yield harness.host_send_token_packet(PID.IN, addr, 0)
        yield harness.host_expect_stall()
        if get_sim_time("us") > harness.packet_deadline:
            raise cocotb.result.TestFailure("Did not receive STALL token")

    # do a setup, which should pass
    yield harness.get_device_descriptor(response=model.deviceDescriptor.get())

    # finally, do one last transfer, which should succeed now
    # that the endpoint is unstalled.
    yield harness.get_device_descriptor(response=model.deviceDescriptor.get())



@cocotb.test(skip=True)
def test_enumeration(dut):
    harness = get_harness(dut)
    harness.max_packet_size = model.deviceDescriptor.bMaxPacketSize0
    yield harness.reset()
    yield harness.wait(10, units="us")

    yield harness.port_reset(5)
    yield harness.connect()
    yield harness.wait(10, units="us")
    # After waiting (bus inactivity) let's start with SOF
    yield harness.host_send_sof(0x01)
    yield harness.get_device_descriptor(response=model.deviceDescriptor.get())

    DEVICE_ADDRESS = 10

    yield harness.set_device_address(DEVICE_ADDRESS, skip_recovery=True)
    # There is a longish recovery period after setting address, so let's send
    # a SOF to make sure DUT doesn't suspend
    yield harness.host_send_sof(0x02)
    yield harness.get_configuration_descriptor(
        length=9,
        # Device must implement at least one configuration
        response=model.configDescriptor[1].get()[:9])

    total_config_len = model.configDescriptor[1].wTotalLength
    yield harness.get_configuration_descriptor(
        length=total_config_len,
        response=model.configDescriptor[1].get()[:total_config_len])

    # Does the device report any string descriptors?
    str_to_check = []
    for idx in (
                model.deviceDescriptor.iManufacturer,
                model.deviceDescriptor.iProduct,
                model.deviceDescriptor.iSerialNumber):
        if idx != 0:
            str_to_check.append(idx)

    # If the device implements string descriptors, let's try reading them
    if str_to_check != []:
        yield harness.get_string_descriptor(
          lang_id=Descriptor.LangId.UNSPECIFIED,
          idx=0,
          response=model.stringDescriptor[0].get())

        lang_id = model.stringDescriptor[0].wLangId[0]
        for idx in str_to_check:
            yield harness.get_string_descriptor(
                lang_id=lang_id,
                idx=idx,
                response=model.stringDescriptor[lang_id][idx].get())

    yield harness.set_configuration(1)
    # Device should now be in "Configured" state
    # TODO: Class-specific config


@cocotb.test(skip=True)
def test_transaction_out(dut):
    harness = get_harness(dut)
    harness.max_packet_size = model.deviceDescriptor.bMaxPacketSize0
    yield harness.reset()
    yield harness.connect()

    yield harness.wait(10, units="us")

    DEVICE_ADDRESS = 10

    yield harness.port_reset(5)
    yield harness.set_device_address(DEVICE_ADDRESS, skip_recovery=True)

    epaddr_in = EndpointType.epaddr(2, EndpointType.IN)
    data = [ord(i) for i in "ABCD"]
    epaddr_out = EndpointType.epaddr(1, EndpointType.OUT)

    
    dut._log.info("[Sending data]")
    yield harness.transaction_data_out(DEVICE_ADDRESS,
                                       2,
                                       data)

    
    dut._log.info("[Receiving data]")
    yield harness.transaction_data_in(DEVICE_ADDRESS,
                                       4,
                                       data)

@cocotb.test()
def test_csr_write(dut):
    harness = get_harness(dut)
    yield harness.reset()
    yield harness.connect()

    # Test that CSR is available, even though this doesn't do anything
    yield harness.write(harness.csrs['uart_tuning_word'], 10)
    
    

@cocotb.test()
def test_csr_read(dut):
    harness = get_harness(dut)
    yield harness.reset()
    yield harness.connect()

    # Test that CSR is available, even though this doesn't do anything
    yield harness.write(harness.csrs['uart_tuning_word'], 10)
    v = yield harness.read(harness.csrs['uart_tuning_word'])
    if v != 10:
        raise TestFailure("Failed to update tuning_word")
    

@cocotb.test()
def test_uart_tx_usb_rx(dut):
    harness = get_harness(dut)
    yield harness.reset()
    yield harness.connect()

    # Attempt a write to Transmit a byte out
    yield harness.write(harness.csrs['uart_rxtx'], 0x41)

    # Expect data comes into the PC
    #ut._log.info("[Receiving data]")
    #yield harness.transaction_data_in(0,4, [0x41])
    