#!/bin/sh
# Run at boot by the SDK's /etc/init.d/S21appinit, which starts whatever the
# app installs under this name. Loads the kernel modules for the camera.

# The vendor's script: it knows the modules, their order and their parameters.
ko=/oem/usr/ko
[ -f $ko/insmod_ko.sh ] || ko=/ko
[ -f $ko/insmod_ko.sh ] && (cd $ko && sh insmod_ko.sh)

# As the vendor's start-up set it.
echo 1 > /proc/sys/vm/overcommit_memory

# The Ethernet addresses are worked out from the chip's serial number and kept
# in vendor storage, item 3, which U-Boot reads before the kernel starts.
VENDOR=/oem/usr/bin/ms-vendor
HWADDR=/oem/usr/bin/ms-hwaddr

set_ethaddr() {
    [ -x $VENDOR ] || return
    # The item holds two. There is no eth1: U-Boot rewrites the item if the second is empty.
    eth0=$($HWADDR eth0) && eth1=$($HWADDR eth1) || return
    # Item 200 is ours: 01 says someone chose the addresses in item 3.
    [ "$($VENDOR get 200 2>/dev/null)" = 01 ] && return
    have=$($VENDOR get 3 2>/dev/null)
    # A random address has the locally administered bit; one from a factory
    # does not, and is not ours to replace.
    case "$(echo "$have" | cut -c2)" in
        ''|[2367abef]) ;;
        *) return ;;
    esac
    want=$(echo "$eth0$eth1" | tr -d :)
    [ "$have" = "$want" ] && return
    $VENDOR set 3 "$want" || return
    # U-Boot had already given the kernel the old one for this boot.
    ifconfig eth0 down 2>/dev/null
    ifconfig eth0 hw ether "$eth0"
}
set_ethaddr

# dhcpcd gives the wired port its address once it has a link.
ifconfig eth0 up 2>/dev/null
