@echo off
windump -i1 -w - not port 4589 and not 2890 and not port 2872 and not arp and not rarp and not icmp and not broadcast | socat - TCP:192.168.56.0:4589,forever,retry,interval=1
