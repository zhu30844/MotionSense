#ifndef MOTIONSENSE_WATCHDOG_H
#define MOTIONSENSE_WATCHDOG_H

/* Hardware watchdog: once started, the board resets unless it keeps being fed. */

/* Does nothing but log when the board has no watchdog device. */
void ms_watchdog_start(void);

void ms_watchdog_feed(void);

/* Disarm, for a clean exit. A crash skips this and the board resets. */
void ms_watchdog_stop(void);

#endif /* MOTIONSENSE_WATCHDOG_H */
