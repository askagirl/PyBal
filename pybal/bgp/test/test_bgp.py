# -*- coding: utf-8 -*-
"""
  bgp.bgp unit tests
  ~~~~~~~~~~~~~~~~~~

  This module contains tests for `bgp.bgp`.

"""

from .. import ip, bgp

import unittest, mock

from twisted.test import proto_helpers
from twisted.python.failure import Failure
from twisted.internet.error import ConnectionLost
from twisted.internet.address import IPv4Address, IPv6Address

class AttributeTestCase(unittest.TestCase):

    def testOriginAttribute(self):
        attr = bgp.OriginAttribute()
        self.assertFalse(attr.optional)
        self.assertTrue(attr.transitive)
        self.assertEquals(attr.value, attr.ORIGIN_IGP)

    def testBaseASPathAttribute(self):
        attr = bgp.BaseASPathAttribute()
        self.assertEquals(attr.value, [(2, [])])

class BGPUpdateMessageTestCase(unittest.TestCase):

    def setUp(self):
        self.msg = bgp.BGPUpdateMessage()
        self.assertEquals(self.msg.msgLenOffset, 16)
        self.assertEquals(len(self.msg.msg), 4)
        self.assertEquals(len(self.msg), 23)
        self.assertIn("UPDATE", repr(self.msg))

        self.attrs = bgp.FrozenAttributeDict(
                    [bgp.OriginAttribute(),
                    bgp.ASPathAttribute([64600, 64601]),
                    bgp.NextHopAttribute("192.0.2.1"),
                    bgp.MEDAttribute(100)])

    def testAddSomeWithdrawals(self):
        self.assertEquals(self.msg.addSomeWithdrawals(set()), 0)

        prefixset = set([ip.IPv4IP('127.0.0.1'),])
        self.assertEquals(self.msg.addSomeWithdrawals(prefixset), 1)

        # The prefix should have been removed from the set
        self.assertEquals(len(prefixset), 0)

        prefixset = set([ ip.IPv4IP(idx) for idx in range(1024) ])
        # Not all prefixes will fit within maxLen
        self.assertEquals(self.msg.addSomeWithdrawals(prefixset), 813)
        self.assertEquals(len(prefixset), 211)

    def testAttributes(self):
        self.msg.addAttributes(bgp.FrozenAttributeDict({}))
        self.assertEqual(len(self.msg), 23)
        self.msg.addAttributes(self.attrs)
        self.assertEqual(len(self.msg), 50)
        self.msg.clearAttributes()
        self.assertEquals(len(self.msg), 23)

        prefixset = set([ ip.IPv4IP(idx) for idx in range(810) ])
        self.assertEquals(self.msg.addSomeWithdrawals(prefixset), 810)
        self.assertRaises(ValueError, self.msg.addAttributes, self.attrs)

    def testAddSomeNLRI(self):
        self.assertEquals(self.msg.addSomeNLRI(set()), 0)

        prefixset = set([ip.IPv6IP('::1'),])
        self.assertEquals(self.msg.addSomeNLRI(prefixset), 1)

        # The prefix should have been removed from the set
        self.assertEquals(len(prefixset), 0)

        prefixset = set([ ip.IPv6IP(hex(idx)) for idx in range(1024) ])
        # Not all prefixes will fit within maxLen
        self.assertEquals(self.msg.addSomeNLRI(prefixset), 238)
        self.assertEquals(len(prefixset), 1024-238)

    def testFreeSpace(self):
        self.assertEquals(self.msg.freeSpace(), bgp.MAX_LEN-len(self.msg))

class BGPTestCase(unittest.TestCase):
    def setUp(self):
        self.factory = bgp.BGPPeering(myASN=64600, peerAddr='127.0.0.1')
        # FIXME: Should configure this in a better way in bgp.FSM
        self.factory.fsm.allowAutomaticStart = False
        self.proto = self.factory.buildProtocol(IPv4Address('TCP', '127.0.0.1', 0))
        self.proto.fsm.allowAutomaticStart = False
        self.tr = proto_helpers.StringTransportWithDisconnection()
        self.tr.protocol = self.proto
        self.assertRaises(AttributeError, self.proto.makeConnection, self.tr)

    def tearDown(self):
        # The BGPPeering factory keeps its own separate FSM
        self.factory.fsm.idleHoldTimer.cancel()
        self.proto.fsm.idleHoldTimer.cancel()

    def testConnectionLost(self):
        failure = Failure(ConnectionLost("Unit test"))

        with mock.patch.object(self.proto.fsm, 'connectionFailed') as mock_method:
            self.proto.connectionLost(failure)
            mock_method.assert_called()

            mock_method.reset_mock()
            self.proto.disconnected = True
            self.proto.connectionLost(failure)
            mock_method.assert_not_called()

    def testDataReceived(self):
        d = b"Unit testing data"
        self.proto.dataReceived(d)
        self.assertIn(d, self.proto.receiveBuffer)

    def testCloseConnection(self):
        with mock.patch.object(self.proto.fsm, 'connectionFailed') as mock_method:
            self.tr.connected = True
            self.proto.closeConnection()
            self.assertTrue(self.proto.disconnected)
            self.assertTrue(self.tr.disconnecting or not self.tr.connected)
            mock_method.assert_called()