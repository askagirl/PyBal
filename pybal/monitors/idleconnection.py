"""
idleconnection.py
Copyright (C) 2006 by Mark Bergsma <mark@nedworks.org>

Monitor class implementations for PyBal
"""

from pybal import monitor

from twisted.internet import reactor, protocol
import logging

import random
import socket


class IdleConnectionMonitoringProtocol(monitor.MonitoringProtocol, protocol.ReconnectingClientFactory):
    """
    Monitor that checks uptime by keeping an idle TCP connection open to the
    server. When the connection is closed in an unclean way, or when the connection
    is closed cleanly but a fast reconnect fails, the monitoring state is set to down.
    """

    protocol = protocol.Protocol

    TIMEOUT_CLEAN_RECONNECT = 3
    MAX_DELAY = 300

    __name__ = 'IdleConnection'

    def __init__(self, coordinator, server, configuration):
        """Constructor"""

        # Call ancestor constructor
        super(IdleConnectionMonitoringProtocol, self).__init__(coordinator, server, configuration)

        self.toCleanReconnect = self._getConfigInt('timeout-clean-reconnect', self.TIMEOUT_CLEAN_RECONNECT)
        self.maxDelay = self._getConfigInt('max-delay', self.MAX_DELAY)

    def run(self):
        """Start the monitoring"""

        super(IdleConnectionMonitoringProtocol, self).run()

        self._connect()

    def stop(self):

        super(IdleConnectionMonitoringProtocol, self).stop()

        self.stopTrying()

    def startedConnecting(self, connector):
        self.transport = getattr(connector, 'transport', None)
        super(IdleConnectionMonitoringProtocol, self).startedConnecting(connector)

    def clientConnectionFailed(self, connector, reason):
        """Called if the connection attempt failed"""

        if not self.active:
            return

        # Immediately set status to down
        self._resultDown(reason.getErrorMessage())

        self.report("Connection failed.", level=logging.WARN)

        # Slowly reconnect
        self.retry(connector)

    def clientConnectionLost(self, connector, reason):
        """Called if the connection was previously established, but lost at some point."""

        if not self.active:
            return

        from twisted.internet import error
        if reason.check(error.ConnectionDone):
            # Connection lost in a clean way. May be idle timeout - try a fast reconnect
            self._connect(timeout=self.toCleanReconnect)
        else:
            # Connection lost in a non clean way. Immediately set status to down
            self._resultDown(reason.getErrorMessage())

            self.report("Connection lost.", level=logging.INFO)

            # Slowly reconnect
            self.retry(connector)

    def clientConnectionMade(self):
        """Called by buildProtocol, to notify that the connection has been established."""

        if not self.active:
            return

        if self.transport is not None:
            sock = self.transport.getHandle()
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPIDLE, 1)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPCNT, 2)
            sock.setsockopt(socket.SOL_TCP, socket.TCP_KEEPINTVL, 1)

        # Set status to up
        self._resultUp()

        # Reset reconnection delay
        self.resetDelay()

        self.report("Connection established.")

    def buildProtocol(self, addr):
        """
        Called to build a new Protocol instance. Implies that the TCP connection
        has been established successfully.
        """

        self.clientConnectionMade()

        # Let the ancestor method do the real work
        return super(IdleConnectionMonitoringProtocol, self).buildProtocol(addr)

    def _connect(self, *args, **kwargs):
        """Starts a TCP connection attempt"""

        try:
            host = random.choice(self.server.ip4_addresses)
        except (TypeError, IndexError):
            host = self.server.host

        self.reactor.connectTCP(host, self.server.port, self, *args, **kwargs)
