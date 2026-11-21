#ifndef MOTIONSENSE_BOARD_H
#define MOTIONSENSE_BOARD_H

#include <stdbool.h>
#include <stddef.h>

#define MS_PATH_MAX 256

/* What this board has. Read once from the board file; see docs/BUILD.md. */
typedef struct {
    char storage_root[MS_PATH_MAX];
    bool storage_removable;   /* a mount point that may be absent */

    /* Derived from storage_root. */
    char dcim_root[MS_PATH_MAX + 32];     /* ends in '/' */
    char meta_db[MS_PATH_MAX + 64];
    char data_dir[MS_PATH_MAX + 32];      /* "<root>/MotionSense", config and logs */
    char config_path[MS_PATH_MAX + 32];
} ms_board_t;

extern ms_board_t g_board;

/* $MS_BOARD_FILE, else CFG_BOARD_FILE. Missing file or key: Pro Max values. */
void ms_board_load(void);

/* False while removable storage is not mounted: writing would land in flash. */
bool ms_storage_present(void);

/* "<directory of this binary>/<rel>", for files installed next to it. */
int ms_install_path(char *out, size_t size, const char *rel);

#endif /* MOTIONSENSE_BOARD_H */
