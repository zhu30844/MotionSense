#include <errno.h>
#include <fcntl.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#include <linux/watchdog.h>

#include "motionsense/config.h"
#include "motionsense/watchdog.h"

#include "log.h"

static int s_fd = -1;

void ms_watchdog_start(void)
{
    s_fd = open(CFG_WATCHDOG_DEV, O_WRONLY | O_CLOEXEC);
    if (s_fd < 0)
    {
        MS_LOG_WARN("no watchdog: %s: %s\n", CFG_WATCHDOG_DEV, strerror(errno));
        return;
    }

    /* The driver rounds up to a period it supports. */
    int timeout = CFG_WATCHDOG_TIMEOUT_S;
    if (ioctl(s_fd, WDIOC_SETTIMEOUT, &timeout) != 0)
        ioctl(s_fd, WDIOC_GETTIMEOUT, &timeout);
    MS_LOG_INFO("watchdog armed, resets after %d s unfed\n", timeout);
}

void ms_watchdog_feed(void)
{
    if (s_fd < 0) return;
    if (write(s_fd, "\0", 1) != 1)
        MS_LOG_WARN("watchdog feed failed: %s\n", strerror(errno));
}

void ms_watchdog_stop(void)
{
    if (s_fd < 0) return;
    /* The magic character: closing without it leaves the timer running. */
    if (write(s_fd, "V", 1) != 1)
        MS_LOG_WARN("watchdog disarm failed: %s\n", strerror(errno));
    close(s_fd);
    s_fd = -1;
}
