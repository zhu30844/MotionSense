#!/bin/sh
# Run at boot by the SDK's /etc/init.d/S21appinit, which starts whatever the
# app installs under this name. Loads the kernel modules for the camera.

# The vendor's script: it knows the modules, their order and their parameters.
ko=/oem/usr/ko
[ -f $ko/insmod_ko.sh ] || ko=/ko
[ -f $ko/insmod_ko.sh ] && (cd $ko && sh insmod_ko.sh)

# As the vendor's start-up set it.
echo 1 > /proc/sys/vm/overcommit_memory

# dhcpcd gives the wired port its address once it has a link.
ifconfig eth0 up 2>/dev/null
