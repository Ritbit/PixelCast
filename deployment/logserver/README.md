# PixelCast log server setup

PixelCast devices auto-discover a log server on the local network via mDNS
and forward all logs to it (rsyslog, TCP). No hostname is hardcoded on the
device side — any host on the network advertising the right mDNS service
will be picked up automatically within ~5 minutes (or immediately on boot).

## To make a host receive PixelCast logs

1. **Install and configure rsyslog** to receive remote logs on TCP/UDP 514,
   writing to a per-host directory, e.g.:

   ```rsyslog
   module(load="imtcp")
   input(type="imtcp" port="514")

   template(name="RemoteHostLog" type="string"
            string="/var/log/remote/%HOSTNAME%/%PROGRAMNAME%.log")

   if ($fromhost-ip != '127.0.0.1') then {
       action(type="omfile" dynaFile="RemoteHostLog" createDirs="on")
       stop
   }
   ```

2. **Open the firewall** for port 514 (tcp, and udp if desired):

   ```bash
   firewall-cmd --permanent --add-port=514/tcp --add-port=514/udp
   firewall-cmd --reload
   ```

3. **Advertise the service via Avahi** so PixelCast devices can find it —
   copy `pixelcast-log.service` (in this directory) to
   `/etc/avahi/services/pixelcast-log.service` and restart `avahi-daemon`.

4. **Add log rotation** — copy `pixelcast-remote-logrotate.conf` to
   `/etc/logrotate.d/pixelcast-remote` so the forwarded logs don't grow
   unbounded (daily rotation, 14 days retention, compressed).

That's it — no PixelCast-side configuration needed. If the log server goes
away, PixelCast devices stop forwarding and fall back to local-only
journald logging automatically (visible in the web UI's Logs page and in
`journalctl -u PixelCast-logdiscovery`).
